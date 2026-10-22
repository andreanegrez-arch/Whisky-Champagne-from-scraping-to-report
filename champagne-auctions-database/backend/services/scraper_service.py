import asyncio
import logging
import re
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

import pandas as pd
from curl_cffi.requests import AsyncSession
# Parser HTML in Python puro (BeautifulSoup) con la stessa API di selectolax:
# selectolax veniva bloccato da Windows Smart App Control e impediva l'avvio
# dell'intero backend. Vedi html_compat.py.
from html_compat import HTMLParser
import scrape_lock
import lotti_ritirati
import bidding_api
from lot_status import detect_lot_status, urls_still_open, extract_winner, closing_date_str
from sqlalchemy.ext.asyncio import AsyncSession as SqlAsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from database import LotORM, engine, async_session
from models import Lot
from parsers import detect_box

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from scraper.check_bargains import check_bargains
except Exception as e:
    check_bargains = None
    print(f"Bargains alert script not loaded: {e}")

# --- CONFIG ---
CATEGORY_URL = "https://www.catawiki.com/en/c/961-champagne"
MAX_PAGES_SAFETY = 100
MAX_CONCURRENT_PAGES = 8

logger = logging.getLogger(__name__)

class ScraperService:
    def __init__(self):
        self.is_running = False
        self.progress = 0.0
        self.last_run = None
        self.message = "Idle"

    def _normalize_url(self, url: str) -> str:
        if not url: return url
        url = url.split("?")[0]
        if url.endswith("/"):
            url = url[:-1]
        return url

    def _clean_maison_name(self, name: str) -> str:
        if not name or not isinstance(name, str):
            return name
        return re.sub(r'^\d{4}\s+', '', name).strip()

    def _extract_price(self, tree: HTMLParser) -> Optional[str]:
        selectors = [
            '[data-testid="lot-price"]',
            '[data-test="final-price"]',
            '[data-test="current-bid"]',
            '.be-lot-bid-status-section__bid-amount',
            'span.price-amount'
        ]
        for sel in selectors:
            node = tree.css_first(sel)
            if node:
                return node.text().strip()
        
        bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
        if bid_section:
            text = bid_section.text().strip()
            matches = re.findall(r'(\d+[\d.,]*)', text)
            if matches:
                return matches[0]
        return None

    def _detect_status(self, tree: HTMLParser, url: str = "") -> str:
        # Logica in backend/lot_status.py: stato ufficiale del lotto (lot_state),
        # scadenza dell'asta confrontata con l'ora attuale e timer del conto alla
        # rovescia. Niente piu' ricerca di "final bid" nel testo di tutta la pagina:
        # quella frase c'e' sempre (dizionario traduzioni) anche nelle aste aperte.
        status, reason = detect_lot_status(tree, url=url)
        logger.debug(f"Stato {status} ({reason}) per {url}")
        return status

    async def _process_lotto(self, url: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        try:
            r = await session.get(url, timeout=30)
            if r.status_code == 404:
                # Primo 404: il lotto viene solo segnato. Secondo 404 sullo stesso
                # identico URL in una sessione successiva: archiviato come ritirato
                # da Catawiki e tolto da `lots` (vedi lotti_ritirati.py).
                esito = lotti_ritirati.register_404(url, getattr(self, "session_id", ""), "backend")
                logger.info(f"404 lotto ({esito}): {url}")
                return None
            if r.status_code in (500, 502, 503, 504) and getattr(self, "retry_5xx", None) is not None:
                # Errore del server di Catawiki: si ritenta una volta, a fine scraping
                self.retry_5xx.append(url)
                logger.warning(f"Errore {r.status_code} lotto (ritento a fine scraping): {url}")
                return None
            if r.status_code != 200:
                logger.error(f"Errore {r.status_code} lotto {url}")
                return None
            if url in getattr(self, "marked_404", ()):
                lotti_ritirati.clear_404(url)

            # Lotti vecchi: Catawiki reindirizza alla categoria o al NUOVO lotto con
            # cui la bottiglia e' stata rimessa all'asta. I dati di quella pagina non
            # sono di questo lotto: prezzo/esito arrivano comunque dall'API offerte.
            if not bidding_api.stesso_lotto(url, r.text, str(getattr(r, "url", "") or "")):
                logger.info(f"Pagina di un altro lotto (reindirizzamento), ignorata: {url}")
                return None

            tree = HTMLParser(r.text)
            title_node = tree.css_first("h1")
            title = title_node.text().strip() if title_node else "Unknown"
            
            maison = "NV"
            scripts = tree.css("script[type='application/ld+json']")
            for s in scripts:
                try:
                    data = json.loads(s.text())
                    if data.get("@type") == "Product":
                        maison = data.get("brand", {}).get("name", "Unknown")
                        break
                except: pass
            if maison == "Unknown" or maison == "NV":
                maison = title.split(",")[0].strip()
            
            maison = self._clean_maison_name(maison)

            vintage = "NV"
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            if year_match:
                vintage = year_match.group(0)
                
            count = 1
            count_match = re.search(r'(?:\s|^|\-)\s*([1-9]\d{0,1})\s*(?:bottles|bottiglie|magnums|magnum|bottiglia|bottle)\b', title, re.I)
            if count_match:
                try: count = int(count_match.group(1))
                except: pass
                
            format_val = "0.75"
            if "Magnum" in title or "1.5L" in title or "1,5L" in title:
                format_val = "Magnum 1.5 L"
            elif "Jeroboam" in title or "3L" in title or "3.0L" in title:
                format_val = "Jeroboam 3 L"
            elif "0.75" in title or "75cl" in title:
                format_val = "0.75"
                
            champagne_type = "Brut"
            title_lower = title.lower()
            if re.search(r'(oenoth[eèé]que|œnoth[eèé]que)', title_lower):
                champagne_type = "Oenotheque Rosé" if "ros" in title_lower else "Oenotheque"
            elif "p2" in title_lower:
                champagne_type = "P2 Rosé" if "ros" in title_lower else "P2"
            elif "p3" in title_lower:
                champagne_type = "P3 Rosé" if "ros" in title_lower else "P3"
            elif "rosé" in title_lower or "rose" in title_lower:
                champagne_type = "Brut Rosé"
            elif "extra brut" in title_lower:
                champagne_type = "Extra Brut"
            elif "blanc de blancs" in title_lower:
                champagne_type = "Blanc de Blancs"

            # Detect Items (Gadget/Ice buckets)
            item_keywords = ["bucket", "ice", "glass", "cestello", "secchiello", "glacière", "seau", "verre", "oggetti", "item", "gadget", "accessorio", "accessory"]
            if any(k in title.lower() for k in item_keywords):
                champagne_type = "Items"

            # Prezzo ed esito dal blocco offerte della pagina (vedi bidding_api.py).
            # Prima si prendeva il PRIMO numero del riquadro offerte: sui lotti chiusi
            # e non venduti era la STIMA del perito (es. 1000 invece di 140).
            # Dopo lo scraping prezzo/esito vengono comunque sovrascritti con l'API.
            esito_pag = bidding_api.da_pagina(tree)
            if esito_pag is None:
                logger.warning(f"Blocco offerte assente, lotto saltato: {url}")
                return None
            price = esito_pag["prezzo_finale"]
            currency = "EUR"

            status = self._detect_status(tree, url)
            
            # Extra Check for is_mixed (Multiple Producers)
            # Look for multiple names or keywords in title
            is_mixed = False
            if any(x in title.lower() for x in [" & ", " and ", " + ", " e ", " con ", " plus "]):
                # Heuristic: if titles contains multiple known maison-like names or just the separators
                is_mixed = True
            
            # If maison name itself contains separators
            if any(x in maison.lower() for x in [" & ", " and ", " + ", " e ", " / "]):
                is_mixed = True

            bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
            reserve = "N"
            if bid_section and "reserve price" in bid_section.text().lower():
                if "no reserve" not in bid_section.text().lower():
                    reserve = "Y"
            
            bid_count = 0
            for node in tree.css("span, div, button"):
                if "all bids" in node.text().lower():
                    m = re.search(r'\((\d+)\)', node.text())
                    if m:
                        try: bid_count = int(m.group(1))
                        except: pass
                        break
                        
            # Vincitore e nazionalita' dal blocco offerte della pagina (vedi
            # backend/lot_status.py). Valorizzati solo per lotti chiusi E venduti:
            # prima si leggeva la prima bandierina della pagina, cioe' chi guidava
            # l'asta in quel momento, e sui lotti chiusi il risultato era "Unknown".
            winner = extract_winner(tree)
            nationality = winner["nazionalita"]
            winner_username = winner["winner_username"]
            winner_id = winner["winner_id"]

            shipping = "N/A"
            for node in tree.css("div"):
                if "shipping" in node.text().lower()[:20] and re.search(r'\d+', node.text()):
                    shipping = node.text().strip()[:30]
                    break

            # Orario di chiusura reale del lotto (UTC), vedi lot_status.py
            closing_date = closing_date_str(tree)

            return {
                "maison": maison,
                "tipologia": champagne_type,
                "numero_bottiglie": count,
                "formato": format_val,
                "vintage": vintage,
                "data_chiusura": closing_date,
                "prezzo_riserva": reserve,
                "numero_offerte": bid_count,
                "nazionalita": nationality,
                "prezzo_finale": price,
                "offerta_massima": esito_pag["offerta_massima"],
                "esito": esito_pag["esito"],
                "costi_spedizione": shipping,
                "title": title,
                "currency": currency,
                "status": status,
                "url": url,
                "has_box": detect_box(title),
                "is_mixed": is_mixed,
                "winner_username": winner_username,
                "winner_id": winner_id,
                "timestamp": datetime.now()
            }

        except Exception as e:
            logger.error(f"Errore lotto {url}: {e}")
            return None

    async def run_scrape(self):
        if self.is_running:
            return
        
        self.is_running = True
        self.progress = 0.0
        self.message = "Starting scrape session..."
        # Segnala la sessione in corso: lo script di recupero si mette in pausa
        scrape_lock.acquire("backend")
        self.session_id = "backend-" + datetime.now().isoformat(timespec="seconds")
        self.retry_5xx = []
        try:
            self.marked_404 = lotti_ritirati.marked_urls()
        except Exception as e:
            logger.warning(f"Tabella 404 non leggibile: {e}")
            self.marked_404 = set()
        
        try:
            urls = []
            p_idx = 1
            
            async with AsyncSession(impersonate="chrome120") as session:
                while p_idx <= MAX_PAGES_SAFETY:
                    self.message = f"Scanning category page {p_idx}..."
                    url = f"{CATEGORY_URL}?page={p_idx}" if p_idx > 1 else CATEGORY_URL
                    try:
                        r = await session.get(url, timeout=30)
                        if r.status_code != 200: break
                        
                        tree = HTMLParser(r.text)
                        item_links = []
                        for a in tree.css("a.c-lot-card"):
                            href = a.attributes.get("href")
                            if href and "/l/" in href:
                                if not href.startswith("http"):
                                    href = "https://www.catawiki.com" + href
                                item_links.append(self._normalize_url(href))
                        
                        if not item_links: break
                        urls.extend(list(dict.fromkeys(item_links)))
                        p_idx += 1
                        await asyncio.sleep(1)
                    except: break

            urls = list(dict.fromkeys(urls))
            
            # NEW LOGIC: Fetch all OPEN lots from DB to ensure we get their final closing price
            try:
                async with async_session() as db:
                    # Lotti OPEN + lotti segnati CLOSED prima della scadenza dalla
                    # vecchia logica di stato (prezzo non finale): vanno ricontrollati.
                    q = select(LotORM.url, LotORM.status, LotORM.data_chiusura, LotORM.timestamp)
                    rows = (await db.execute(q)).all()
                    df_db = pd.DataFrame(rows, columns=["url", "status", "data_chiusura", "timestamp"])
                    open_urls = urls_still_open(df_db, end_col="data_chiusura")
                    logger.info(f"{len(open_urls)} lotti gia' in archivio da ricontrollare")
                    for ou in open_urls:
                        if ou not in urls:
                            urls.append(ou)
            except Exception as e:
                logger.error(f"Failed to fetch OPEN lots from DB: {e}")
                
            total_urls = len(urls)
            self.message = f"Found {total_urls} lots. Starting detailed extraction..."
            
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

            async def sem_task(u, sess):
                async with semaphore:
                    res = await self._process_lotto(u, sess)
                    self.progress = (len(results) / total_urls) * 100
                    return res

            results = []
            async with AsyncSession(impersonate="chrome120") as session:
                for i, url in enumerate(urls):
                    res = await sem_task(url, session)
                    if res: results.append(res)
                    self.progress = ((i + 1) / total_urls) * 100
                    self.message = f"Scraped {i+1}/{total_urls} lots..."

            # Secondo passaggio, SOLO a fine scraping: i lotti che hanno risposto con
            # un errore del server di Catawiki (5xx) vengono riprovati una volta.
            # Se falliscono ancora restano come sono e vengono ripresi alla sessione dopo.
            retry_urls = list(dict.fromkeys(self.retry_5xx))
            if retry_urls:
                logger.info(f"Ritento {len(retry_urls)} lotti con errore del server (5xx) a fine scraping")
                self.message = f"Retrying {len(retry_urls)} lots with server errors..."
                self.retry_5xx = []
                await asyncio.sleep(30)
                recovered = 0
                async with AsyncSession(impersonate="chrome120") as session:
                    for url in retry_urls:
                        res = await self._process_lotto(url, session)
                        if res:
                            results.append(res)
                            recovered += 1
                        await asyncio.sleep(2)
                logger.info(f"Secondo tentativo: {recovered} recuperati, {len(retry_urls) - recovered} ancora in errore (ripresi alla prossima sessione)")
            self.retry_5xx = None

            # Esito ufficiale dall'API offerte di Catawiki, per id del lotto: vale
            # anche per i lotti archiviati o reindirizzati (pagina non utilizzabile).
            self.message = "Checking final bids (Catawiki API)..."
            api_updates = {}
            try:
                ids = [bidding_api.lot_id(u) for u in urls]
                async with AsyncSession(impersonate="chrome120", headers=DEFAULT_HEADERS) as session:
                    api = await bidding_api.fetch_async(session, [i for i in ids if i])
                for u in urls:
                    info = api.get(bidding_api.lot_id(u))
                    if info:
                        d = bidding_api.interpreta(info)
                        d.pop("reserve_price_met", None)
                        if not d.get("data_chiusura"):
                            d.pop("data_chiusura", None)
                        api_updates[u] = d
                for res in results:
                    res.update(api_updates.get(res["url"], {}))
                logger.info(f"API offerte: {len(api_updates)}/{len(urls)} lotti aggiornati")
            except Exception as e:
                logger.error(f"API offerte non disponibile, resta il dato della pagina: {e}")

            # Persistence
            if results:
                async with async_session() as db:
                    for res in results:
                        # Check existance by URL
                        q = select(LotORM).where(LotORM.url == res["url"])
                        existing = (await db.execute(q)).scalar_one_or_none()
                        
                        if existing:
                            # Update existing
                            for key, value in res.items():
                                setattr(existing, key, value)
                        else:
                            # Create new
                            new_lot = LotORM(**res)
                            db.add(new_lot)
                    
                    # Lotti gia' in archivio la cui pagina non era utilizzabile
                    # (reindirizzata/archiviata): solo i dati d'asta dall'API.
                    visti = {res["url"] for res in results}
                    for u, d in api_updates.items():
                        if u in visti:
                            continue
                        q = select(LotORM).where(LotORM.url == u)
                        existing = (await db.execute(q)).scalar_one_or_none()
                        if existing:
                            for key, value in d.items():
                                setattr(existing, key, value)
                    await db.commit()
                self.message = f"Scrape complete. {len(results)} lots processed."
                self.message = "No results found."

            if check_bargains:
                self.message = "Scrape complete. Checking for bargains..."
                await asyncio.to_thread(check_bargains)
                self.message = "Scrape and alerts complete."

        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            self.message = f"Error: {e}"
        finally:
            try:
                n = await asyncio.to_thread(lotti_ritirati.export_excel)
                logger.info(f"Report lotti ritirati aggiornato ({n} lotti)")
            except Exception as e:
                logger.warning(f"Report lotti ritirati non aggiornato: {e}")
            scrape_lock.release("backend")
            self.is_running = False
            self.last_run = datetime.now()
            self.progress = 100.0

scraper_instance = ScraperService()
