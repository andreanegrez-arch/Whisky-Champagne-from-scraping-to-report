"""
Catawiki Champagne Scraper
==========================
Scarica i lotti champagne da Catawiki, li normalizza e salva in Excel
con analisi aggregate e dashboard prezzi.

Struttura pubblica (invariata rispetto alla versione precedente):
- Classe: CatawikiScraper
- Costanti: DATA_PATH, SUMMARY_PATH, CATEGORY_URL
- Metodo entry: main()

Fix vs versione precedente:
- Parser HTML condiviso backend/html_compat.py (BeautifulSoup, niente DLL)
- bids_count calcolato PRIMA della logica di status (fix NameError)
- Status CLOSED più robusto (non richiede più AND rigido con is_past)
- Storico prezzi preservato: deduplica per (url, timestamp) invece che url puro
- Cutoff lotti OPEN vecchi (>45 giorni marcati EXPIRED, no ri-scraping infinito)
- Retry base su 429/503 con backoff
- Sleep randomizzato per ridurre rischio ban
- Doppia esecuzione all'avvio evitata
"""

import os
import sys
import re
import json
import time
import random
import logging
from datetime import datetime, timedelta

import pandas as pd
import schedule
from curl_cffi import requests

# =============================================================================
# PARSER
# =============================================================================
# Parser HTML in Python puro (BeautifulSoup) con la stessa API di selectolax,
# condiviso con il backend (backend/html_compat.py). selectolax veniva bloccato
# da Windows Smart App Control.
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from html_compat import HTMLParser  # noqa: E402
import scrape_lock  # noqa: E402
import lotti_ritirati  # noqa: E402

# Ultimo codice HTTP ricevuto per ogni URL di lotto (serve a riconoscere i 404)
LAST_HTTP_STATUS = {}
import bidding_api  # noqa: E402
from lot_status import detect_lot_status, urls_still_open, closed_too_early_mask, extract_winner, closing_date_str  # noqa: E402


# =============================================================================
# CONFIGURAZIONE
# =============================================================================

CATEGORY_URL = "https://www.catawiki.com/en/c/961-champagne"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS_ITA = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}


def get_monthly_paths():
    now = datetime.now()
    mese_nome = MONTHS_ITA[now.month]
    excel_name = f"database champagne {mese_nome}.xlsx"
    summary_name = f"auctions_summary_{mese_nome}.xlsx"
    excel_path = os.path.join(ROOT_DIR, "data", excel_name)
    summary_path = os.path.join(ROOT_DIR, "data", summary_name)
    return excel_path, summary_path


DATA_PATH, SUMMARY_PATH = get_monthly_paths()
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "scraper_historic.log")

MAX_PAGES_SAFETY = 100
EXPIRE_OPEN_LOTS_DAYS = 45  # dopo quanti giorni un lotto OPEN diventa EXPIRED
MAX_RETRIES = 3
BACKOFF_BASE = 5  # secondi

# Setup cartelle
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


# =============================================================================
# SCRAPER
# =============================================================================

class CatawikiScraper:
    """Scraper Catawiki per la categoria Champagne."""

    COLUMNS = [
        "Maison", "Tipologia", "Numero Bottiglie", "Formato", "Vintage",
        "Data Chiusura", "Prezzo Riserva", "Numero Offerte", "Nazionalita",
        "Prezzo Finale", "Costi Spedizione", "title", "currency", "status", "url",
        "timestamp", "winner_username", "winner_id",
    ]

    def __init__(self):
        self.db_path = DATA_PATH

    # -------------------------------------------------------------------------
    # Persistenza
    # -------------------------------------------------------------------------

    def load_data(self):
        """Carica lo storico dal file Excel, unendo i fogli Dati e Lotti non chiusi."""
        if not os.path.exists(DATA_PATH):
            return pd.DataFrame(columns=self.COLUMNS)

        try:
            xls = pd.ExcelFile(DATA_PATH)
            dfs = []
            for sname in ["Dati", "Lotti non chiusi"]:
                if sname in xls.sheet_names:
                    dfs.append(pd.read_excel(xls, sheet_name=sname))
            df = pd.concat(dfs, ignore_index=True) if dfs else pd.read_excel(DATA_PATH)
            if "Maison" in df.columns:
                df["Maison"] = df["Maison"].apply(self.clean_maison_name)
            return df
        except Exception as e:
            logging.warning(f"Errore caricamento Excel: {e}. Restituisco DataFrame vuoto.")
            return pd.DataFrame(columns=self.COLUMNS)

    # -------------------------------------------------------------------------
    # Utility di pulizia
    # -------------------------------------------------------------------------

    @staticmethod
    def clean_price(price_str):
        if not price_str:
            return None, None
        currency = "".join(c for c in price_str if not c.isdigit() and c not in ".,").strip()
        price_num = "".join(c for c in price_str if c.isdigit() or c in ".,").replace(",", ".").strip()
        return price_num, currency

    @staticmethod
    def normalize_url(url):
        """Rimuove parametri query e slash finali per evitare duplicati."""
        if not url:
            return url
        url = url.split("?")[0]
        if url.endswith("/"):
            url = url[:-1]
        return url

    @staticmethod
    def clean_maison_name(name):
        """Rimuove annata iniziale dal nome della Maison (es. '1990 Dom Perignon' → 'Dom Perignon')."""
        if not name or not isinstance(name, str):
            return name
        return re.sub(r"^\d{4}\s+", "", name).strip()

    # -------------------------------------------------------------------------
    # Rete
    # -------------------------------------------------------------------------

    @staticmethod
    def _fetch_with_retry(session, url, timeout=30):
        """GET con retry esponenziale su 429/503."""
        for attempt in range(MAX_RETRIES):
            try:
                r = session.get(url, timeout=timeout)
                LAST_HTTP_STATUS[url] = r.status_code
                if r.status_code == 200:
                    return r
                if r.status_code in (429, 503):
                    wait = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 2)
                    logging.warning(f"Status {r.status_code} su {url}. Attendo {wait:.1f}s (tentativo {attempt+1}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                logging.error(f"Status {r.status_code} su {url}")
                return None
            except Exception as e:
                wait = BACKOFF_BASE * (2 ** attempt)
                logging.warning(f"Errore rete su {url}: {e}. Retry in {wait}s")
                time.sleep(wait)
        return None

    # -------------------------------------------------------------------------
    # Parsing lotto
    # -------------------------------------------------------------------------

    def get_lot_details(self, session, url):
        """Estrae tutti i dettagli di un singolo lotto."""
        try:
            r = self._fetch_with_retry(session, url)
            if r is None:
                return None

            # Lotto vecchio reindirizzato alla categoria o a un NUOVO lotto (bottiglia
            # rimessa all'asta): i dati della pagina non sono di questo lotto.
            if not bidding_api.stesso_lotto(url, r.text, str(getattr(r, 'url', '') or '')):
                logging.info(f"Pagina di un altro lotto (reindirizzamento), ignorata: {url}")
                return None

            tree = HTMLParser(r.text)

            # --- Titolo ---
            title_el = tree.css_first("h1")
            title = title_el.text().strip() if title_el else "Unknown"

            # --- Prezzo ---
            # Prezzo ed esito dal blocco offerte della pagina (vedi backend/bidding_api.py).
            # Prima si prendeva il PRIMO numero del riquadro offerte: sui lotti chiusi e
            # non venduti era la STIMA del perito, e clean_price trasformava '1,250' in 1.25.
            _esito = bidding_api.da_pagina(tree)
            if _esito is None:
                logging.warning(f"Blocco offerte assente, lotto saltato: {url}")
                return None
            price, currency = _esito['prezzo_finale'], 'EUR'
            bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')

            # --- Maison (JSON-LD prima, fallback titolo) ---
            maison = "Unknown"
            for s in tree.css("script[type='application/ld+json']"):
                try:
                    data = json.loads(s.text())
                    if data.get("@type") == "Product":
                        maison = data.get("brand", {}).get("name", "Unknown")
                        break
                except Exception:
                    continue
            if maison in ("Unknown", "NV", "", None):
                # Fallback dal titolo, con protezione contro maison vuota
                parts = [p.strip() for p in title.split(",") if p.strip()]
                for p in parts:
                    candidate = self.clean_maison_name(p)
                    if candidate and len(candidate) >= 2 and not candidate.isdigit():
                        maison = candidate
                        break
            maison = self.clean_maison_name(maison) or "Unknown"

            # --- Vintage ---
            vintage = "NV"
            year_match = re.search(r"\b(19|20)\d{2}\b", title)
            if year_match:
                vintage = year_match.group(0)

            # --- Count (bottiglie) ---
            count = "1"
            # Pattern 1: "N bottles/bottiglie/magnums"
            count_match = re.search(
                r"(?:\s|^|\-)\s*([1-9]\d{0,1})\s*(?:bottles|bottiglie|magnums|magnum|bottiglia|bottle)\b",
                title, re.I,
            )
            if count_match:
                count = count_match.group(1)
            else:
                # Pattern 2: "N x 0.75L" o "N × 750ml" (formato Catawiki comune)
                m2 = re.search(r"\b([1-9]\d{0,1})\s*[x×]\s*\d", title, re.I)
                if m2:
                    count = m2.group(1)
                else:
                    # Pattern 3: "case of N"
                    m3 = re.search(r"case of\s+([1-9]\d{0,1})", title, re.I)
                    if m3:
                        count = m3.group(1)

            # --- Formato ---
            format_val = "0.75"
            tlow = title.lower()
            if re.search(r"\bmagnum\b|\b1[.,]5\s*l\b", tlow):
                format_val = "Magnum 1.5 L"
            elif re.search(r"\bjeroboam\b|\b3\s*l\b", tlow):
                format_val = "Jeroboam 3 L"
            elif re.search(r"\brehoboam\b|\b4[.,]5\s*l\b", tlow):
                format_val = "Rehoboam 4.5 L"
            elif re.search(r"\bmethuselah\b|\b6\s*l\b", tlow):
                format_val = "Methuselah 6 L"
            elif re.search(r"\b0[.,]375\s*l\b|\b37[.,]?5\s*cl\b|\bhalf\b", tlow):
                format_val = "Half 0.375 L"
            elif re.search(r"\b0[.,]75\s*l\b|\b75\s*cl\b", tlow):
                format_val = "0.75"

            # --- Tipologia ---
            champagne_type = "Brut"
            if re.search(r"oenoth[eèé]que|œnoth[eèé]que", tlow):
                champagne_type = "Oenotheque Rosé" if "ros" in tlow else "Oenotheque"
            elif "p2" in tlow:
                champagne_type = "P2 Rosé" if "ros" in tlow else "P2"
            elif "p3" in tlow:
                champagne_type = "P3 Rosé" if "ros" in tlow else "P3"
            elif "blanc de blancs" in tlow:
                champagne_type = "Blanc de Blancs"
            elif "extra brut" in tlow:
                champagne_type = "Extra Brut"
            elif "rosé" in tlow or "rose" in tlow:
                champagne_type = "Brut Rosé"

            # Orario di chiusura reale del lotto (UTC), vedi backend/lot_status.py
            closing_date = closing_date_str(tree)

            # --- Numero offerte (CALCOLATO PRIMA DELLO STATUS - fix del NameError) ---
            bids_count = "0"
            for node in tree.css("span, div, button"):
                node_text = node.text().lower()
                if "all bids" in node_text:
                    m = re.search(r"\((\d+)\)", node.text())
                    if m:
                        bids_count = m.group(1)
                        break

            # --- Status (CLOSED / OPEN) ---
            # Logica in backend/lot_status.py: lot_state ufficiale, scadenza vs ora
            # attuale (in UTC), timer del conto alla rovescia. La vecchia ricerca di
            # "final bid" su tutta la pagina segnava CHIUSE anche le aste aperte.
            bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
            status, status_reason = detect_lot_status(tree, url=url)
            logging.debug(f"Stato {status} ({status_reason})")

            # --- Prezzo di riserva ---
            reserve_price = "N"
            if bid_section:
                bs_text = bid_section.text().lower()
                if "reserve price" in bs_text and "no reserve" not in bs_text:
                    reserve_price = "Y"

            # --- Bidder info (da __NEXT_DATA__) ---
            # Vincitore e nazionalita' dal blocco offerte della pagina (vedi
            # backend/lot_status.py). Valorizzati solo per lotti chiusi E venduti:
            # prima si leggeva la prima bandierina della pagina, cioe' chi guidava
            # l'asta in quel momento, e sui lotti chiusi il risultato era "Unknown".
            winner = extract_winner(tree)
            bidder_nationality = winner["nazionalita"]
            winner_username = winner["winner_username"]
            winner_id = winner["winner_id"]

            # --- Spedizione (best effort semplificato) ---
            shipping = "N/A"
            ship_node = tree.css_first('[data-testid*="shipping"], [class*="shipping"]')
            if ship_node:
                ship_text = ship_node.text().strip()
                if re.search(r"\d", ship_text):
                    shipping = ship_text[:40]

            return {
                "Maison": maison,
                "Tipologia": champagne_type,
                "Numero Bottiglie": count,
                "Formato": format_val,
                "Vintage": vintage,
                "Data Chiusura": closing_date,
                "Prezzo Riserva": reserve_price,
                "Numero Offerte": bids_count,
                "Nazionalita": bidder_nationality,
                "Prezzo Finale": price,
                "Esito": _esito['esito'],
                "Offerta Massima": _esito['offerta_massima'],
                "Costi Spedizione": shipping,
                "title": title,
                "currency": currency,
                "status": status,
                "url": self.normalize_url(url),
                "winner_username": winner_username,
                "winner_id": winner_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        except Exception as e:
            logging.error(f"Errore scraping lotto {url}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Sessione completa
    # -------------------------------------------------------------------------

    def _collect_category_urls(self, session):
        """Scansiona le pagine categoria e raccoglie tutti gli URL dei lotti."""
        urls = set()
        for p_idx in range(1, MAX_PAGES_SAFETY + 1):
            p_url = f"{CATEGORY_URL}?page={p_idx}" if p_idx > 1 else CATEGORY_URL
            logging.info(f"Scansione categoria pagina {p_idx}")
            resp = self._fetch_with_retry(session, p_url)
            if resp is None:
                logging.warning(f"Pagina {p_idx} non raggiungibile. Fine scansione.")
                break

            parser = HTMLParser(resp.text)
            page_urls = []
            for a in parser.css("a.c-lot-card"):
                href = a.attributes.get("href")
                if href and "/l/" in href:
                    if href.startswith("/"):
                        href = "https://www.catawiki.com" + href
                    page_urls.append(self.normalize_url(href))

            if not page_urls:
                logging.info(f"Nessun lotto trovato alla pagina {p_idx}. Fine scansione.")
                break

            logging.info(f"Trovati {len(page_urls)} link nella pagina {p_idx}")
            urls.update(page_urls)
            time.sleep(random.uniform(1.5, 3.0))
        return list(urls)

    def _expire_old_open_lots(self, df_historic):
        """Marca come EXPIRED i lotti OPEN più vecchi di EXPIRE_OPEN_LOTS_DAYS."""
        if df_historic.empty or "Data Chiusura" not in df_historic.columns:
            return df_historic
        try:
            cutoff = datetime.now() - timedelta(days=EXPIRE_OPEN_LOTS_DAYS)
            df = df_historic.copy()
            dates = pd.to_datetime(df["Data Chiusura"], errors="coerce")
            mask = (df["status"] == "OPEN") & dates.notna() & (dates < cutoff)
            expired_n = int(mask.sum())
            if expired_n > 0:
                df.loc[mask, "status"] = "EXPIRED"
                logging.info(f"Marcati {expired_n} lotti OPEN vecchi come EXPIRED.")
            return df
        except Exception as e:
            logging.warning(f"Errore expire OPEN lots: {e}")
            return df_historic

    def run_session(self):
        """Sessione di scraping, segnalata con un file di lock (vedi backend/scrape_lock.py)."""
        scrape_lock.acquire("scheduler")
        try:
            self._run_session_unlocked()
        finally:
            scrape_lock.release("scheduler")

    def _run_session_unlocked(self):
        """Esegue una singola sessione di scraping."""
        global DATA_PATH, SUMMARY_PATH
        DATA_PATH, SUMMARY_PATH = get_monthly_paths()

        df_historic = self.load_data()
        df_historic = self._expire_old_open_lots(df_historic)

        logging.info("=== INIZIO SESSIONE SCRAPING ===")
        new_entries = []
        session_id = "scheduler-" + datetime.now().isoformat(timespec="seconds")
        ritirati = []
        retry_5xx = []  # lotti con errore del server: ritentati solo a fine scraping
        try:
            marked_404 = lotti_ritirati.marked_urls()
        except Exception as e:
            logging.warning(f"Tabella 404 non leggibile: {e}")
            marked_404 = set()

        try:
            session = requests.Session(impersonate="chrome120")
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": CATEGORY_URL,
                "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
            })

            urls = self._collect_category_urls(session)

            # Ri-scraping dei lotti ancora aperti: solo quelli la cui rilevazione PIU'
            # RECENTE e' OPEN, piu' quelli segnati CLOSED prima della scadenza dalla
            # vecchia logica (il loro prezzo non era quello finale).
            if not df_historic.empty and "status" in df_historic.columns:
                open_lots = urls_still_open(df_historic)
                n_early = int(closed_too_early_mask(df_historic).sum())
                if n_early:
                    logging.info(f"{n_early} rilevazioni CLOSED fatte prima della scadenza: lotti da ricontrollare.")
                for ou in open_lots:
                    nu = self.normalize_url(ou)
                    if nu and nu not in urls:
                        urls.append(nu)

            logging.info(f"Totale lotti da analizzare (nuovi + OPEN precedenti): {len(urls)}")

            for i, url in enumerate(urls, 1):
                logging.info(f"[{i}/{len(urls)}] Analisi: {url}")
                details = self.get_lot_details(session, url)
                if details:
                    new_entries.append(details)
                    if url in marked_404:
                        lotti_ritirati.clear_404(url)
                elif LAST_HTTP_STATUS.get(url) == 404:
                    # Doppio controllo: primo 404 = segnato; secondo 404 sullo stesso
                    # URL in una sessione successiva = ritirato (vedi lotti_ritirati.py)
                    try:
                        esito = lotti_ritirati.register_404(
                            url, session_id, "scheduler",
                            lot_info=lotti_ritirati.lot_info_from_excel(df_historic, url))
                        logging.info(f"404 lotto ({esito}): {url}")
                        if esito == lotti_ritirati.RITIRATO:
                            ritirati.append(url)
                    except Exception as e:
                        logging.warning(f"Registrazione 404 fallita per {url}: {e}")
                elif LAST_HTTP_STATUS.get(url) in (500, 502, 503, 504):
                    retry_5xx.append(url)
                    logging.warning(f"Errore {LAST_HTTP_STATUS[url]} (ritento a fine scraping): {url}")
                time.sleep(random.uniform(1.5, 3.5))

            # Secondo passaggio, SOLO a fine scraping: i lotti con errore del server di
            # Catawiki (5xx) vengono riprovati una volta. Se falliscono ancora restano
            # come sono e vengono ripresi alla sessione successiva.
            if retry_5xx:
                logging.info(f"Ritento {len(retry_5xx)} lotti con errore del server (5xx) a fine scraping")
                time.sleep(30)
                recovered = 0
                for url in dict.fromkeys(retry_5xx):
                    details = self.get_lot_details(session, url)
                    if details:
                        new_entries.append(details)
                        recovered += 1
                    time.sleep(2)
                logging.info(f"Secondo tentativo: {recovered} recuperati, {len(retry_5xx) - recovered} ancora in errore (ripresi alla prossima sessione)")

        except Exception as e:
            logging.error(f"Errore di rete/scraping: {e}")

        # Lotti ritirati da Catawiki (404 confermato due volte): tolti dallo storico
        # e archiviati nel report "Lotti 404_Ritirati_Da_Catawiki.xlsx"
        if ritirati and not df_historic.empty and "url" in df_historic.columns:
            df_historic = df_historic[~df_historic["url"].isin(ritirati)]
            logging.info(f"{len(ritirati)} lotti ritirati da Catawiki rimossi dallo storico e archiviati.")
        try:
            n_rit = lotti_ritirati.export_excel()
            logging.info(f"Report lotti ritirati aggiornato ({n_rit} lotti)")
        except Exception as e:
            logging.warning(f"Report lotti ritirati non aggiornato: {e}")

        # Merge storico + nuove rilevazioni
        if new_entries:
            df_new = pd.DataFrame(new_entries)
            df_historic = pd.concat([df_historic, df_new], ignore_index=True)

            # Storico prezzi preservato: dedup su (url, timestamp) invece che solo url
            df_historic.drop_duplicates(subset=["url", "timestamp"], keep="last", inplace=True)

            if "timestamp" in df_historic.columns:
                df_historic["timestamp"] = pd.to_datetime(df_historic["timestamp"], errors="coerce")
                df_historic.sort_values("timestamp", inplace=True)

            if "Maison" in df_historic.columns:
                df_historic = df_historic.sort_values(by="Maison", kind="stable")

            logging.info(f"Aggiunte {len(new_entries)} nuove rilevazioni.")

        self.save_advanced_excel(df_historic, DATA_PATH)
        self.run_analysis(df_historic)
        logging.info("=== SESSIONE COMPLETATA ===")

    def run(self):
        """Avvia lo scheduler con sessioni giornaliere alle 03:00 e 17:00."""
        schedule.every().day.at("03:00").do(self.run_session)
        schedule.every().day.at("17:00").do(self.run_session)

        # Un lock "scheduler" rimasto da una sessione interrotta (finestra chiusa,
        # PC spento) non e' piu' valido: questo processo non ha sessioni in corso.
        scrape_lock.release("scheduler")
        logging.info("=== SCHEDULER AVVIATO ===")
        logging.info("Sessioni programmate: ogni giorno alle 03:00 e 17:00.")

        # Sessione immediata solo se non è imminente uno slot schedulato
        now = datetime.now()
        skip_startup = any(
            0 <= (target - now).total_seconds() < 300
            for target in [now.replace(hour=3, minute=0, second=0, microsecond=0),
                           now.replace(hour=17, minute=0, second=0, microsecond=0)]
        )
        # Se il backend sta gia' facendo scraping, niente sessione di avvio:
        # due scraping insieme raddoppiano le richieste verso Catawiki.
        attive = [s for s in scrape_lock.running_sessions() if s != "scheduler"]
        if attive and not skip_startup:
            logging.info(f"Scraping gia' in corso ({', '.join(attive)}): salto la sessione di avvio, "
                         f"la prossima parte all'orario programmato.")
            skip_startup = True
        elif not skip_startup:
            logging.info("Eseguo sessione immediata all'avvio.")
            self.run_session()
        else:
            logging.info("Slot schedulato imminente: salto la sessione di avvio.")

        while True:
            schedule.run_pending()
            time.sleep(60)

    # -------------------------------------------------------------------------
    # Excel avanzato (mantenuto dalla versione precedente, con piccoli fix)
    # -------------------------------------------------------------------------

    def save_advanced_excel(self, df, path):
        """Salva Excel con fogli, grafici, pivot e dashboard prezzi dinamica."""
        if df.empty:
            logging.warning("DataFrame vuoto: skip generazione Excel.")
            return

        try:
            df = df.copy()
            df["Numero Bottiglie"] = pd.to_numeric(df["Numero Bottiglie"], errors="coerce").fillna(1)
            df["Numero Offerte"] = pd.to_numeric(df["Numero Offerte"], errors="coerce").fillna(0)

            df_active = df[(df["Numero Offerte"] > 0) & (df["Nazionalita"] != "Unknown")].copy()
            df_inactive = df[(df["Numero Offerte"] == 0) | (df["Nazionalita"] == "Unknown")].copy()

            if "Maison" in df_active.columns:
                df_active.sort_values(by="Maison", inplace=True)
            if "Maison" in df_inactive.columns:
                df_inactive.sort_values(by="Maison", inplace=True)

            with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
                df_active.to_excel(writer, sheet_name="Dati", index=False)
                df_inactive.to_excel(writer, sheet_name="Lotti non chiusi", index=False)
                workbook = writer.book

                # --- Analisi Nazionalità ---
                # Ogni lotto conta UNA volta (rilevazione più recente), solo se CHIUSO e
                # con la nazionalità del vincitore nota: "Unknown" è escluso. Prima si
                # contavano tutte le rilevazioni, anche quelle fatte ad asta aperta.
                if {"Nazionalita", "status"} <= set(df.columns):
                    nat_src = df.copy()
                    if "timestamp" in nat_src.columns:
                        nat_src["_ts"] = pd.to_datetime(nat_src["timestamp"], errors="coerce")
                        nat_src = nat_src.sort_values("_ts", kind="stable").drop(columns="_ts")
                    if "url" in nat_src.columns:
                        nat_src = nat_src.drop_duplicates(subset=["url"], keep="last")
                    nat_src = nat_src[
                        (nat_src["status"] == "CLOSED")
                        & nat_src["Nazionalita"].notna()
                        & ~nat_src["Nazionalita"].astype(str).str.strip().isin(["Unknown", "Sconosciuto", "NV", "", "nan"])
                    ].copy()
                    nat_src["Prezzo Finale"] = pd.to_numeric(nat_src["Prezzo Finale"], errors="coerce")
                else:
                    nat_src = pd.DataFrame()

                if not nat_src.empty:
                    df_nat = (nat_src.groupby("Nazionalita")
                              .agg(Lotti=("Nazionalita", "size"), **{"Spesa Totale": ("Prezzo Finale", "sum")})
                              .reset_index()
                              .sort_values("Lotti", ascending=False))
                    df_nat["Spesa Totale"] = df_nat["Spesa Totale"].round(2)
                    df_nat["Prezzo Medio"] = (df_nat["Spesa Totale"] / df_nat["Lotti"]).round(2)
                    df_nat.to_excel(writer, sheet_name="Analisi Nazionalita", index=False)
                    sh_nat = writer.sheets["Analisi Nazionalita"]
                    chart_nat = workbook.add_chart({"type": "pie"})
                    chart_nat.add_series({
                        "name": "Nazionalità vincitori",
                        "categories": ["Analisi Nazionalita", 1, 0, len(df_nat), 0],
                        "values": ["Analisi Nazionalita", 1, 1, len(df_nat), 1],
                        "data_labels": {"percentage": True, "category": True, "position": "outside_end"},
                    })
                    chart_nat.set_title({"name": "Distribuzione % nazionalità dei vincitori (lotti venduti)"})
                    sh_nat.insert_chart("F2", chart_nat)

                    # Dettaglio (drill-through): i lotti di ogni nazionalità, filtrabili
                    det_cols = [c for c in ["Nazionalita", "Maison", "Tipologia", "Vintage", "Formato", "Numero Bottiglie",
                                            "Prezzo Finale", "Data Chiusura", "Numero Offerte",
                                            "winner_username", "title", "url"] if c in nat_src.columns]
                    det = nat_src.sort_values(["Nazionalita", "Data Chiusura"], ascending=[True, False])[det_cols]
                    det.to_excel(writer, sheet_name="Dettaglio Nazionalita", index=False)
                    sh_det = writer.sheets["Dettaglio Nazionalita"]
                    sh_det.autofilter(0, 0, len(det), len(det_cols) - 1)
                    sh_det.freeze_panes(1, 0)

                # --- Analisi Volume Maison ---
                if "Maison" in df.columns:
                    df_vol = df.groupby(["Maison", "Tipologia"])["Numero Bottiglie"].sum() \
                                .sort_values(ascending=False).reset_index()
                    df_vol["Etichetta"] = df_vol["Maison"] + " (" + df_vol["Tipologia"].astype(str) + ")"
                    df_vol.to_excel(writer, sheet_name="Analisi Volume Maison", index=False)
                    sh_vol = writer.sheets["Analisi Volume Maison"]
                    chart_vol = workbook.add_chart({"type": "column"})
                    chart_vol.add_series({
                        "name": "Bottiglie Totali",
                        "categories": ["Analisi Volume Maison", 1, 3, len(df_vol), 3],
                        "values": ["Analisi Volume Maison", 1, 2, len(df_vol), 2],
                        "data_labels": {"value": True, "font": {"size": 8, "bold": True}},
                    })
                    chart_vol.set_title({"name": "Volume Vendite (Maison & Tipologia)"})
                    chart_vol.set_x_axis({"name": "Maison (Tipologia)"})
                    chart_vol.set_y_axis({"name": "Q.tà Bottiglie"})
                    chart_vol.set_size({"width": 1000, "height": 500})
                    sh_vol.insert_chart("F2", chart_vol)

                # --- Analisi Rendimento (Success rate) ---
                sh_perf = workbook.add_worksheet("Analisi Rendimento")
                perf_data = [
                    ["Categoria", "Lotti"],
                    ["Con Offerte", len(df_active)],
                    ["Senza Offerte/Unknown", len(df_inactive)],
                ]
                for r_idx, row in enumerate(perf_data):
                    sh_perf.write_row(r_idx, 0, row)
                chart_perf = workbook.add_chart({"type": "pie"})
                chart_perf.add_series({
                    "name": "Rendimento Aste",
                    "categories": ["Analisi Rendimento", 1, 0, 2, 0],
                    "values": ["Analisi Rendimento", 1, 1, 2, 1],
                    "data_labels": {"percentage": True, "category": True, "position": "outside_end"},
                })
                chart_perf.set_title({"name": f"Success Rate - Totale {len(df)} Lotti"})
                sh_perf.insert_chart("D2", chart_perf)

                # --- Analisi Prezzi Maison (media + mediana per requisito improvement.txt) ---
                if not df_active.empty:
                    df_active["Prezzo Finale"] = pd.to_numeric(df_active["Prezzo Finale"], errors="coerce").fillna(0)
                    df_active["Prezzo Unitario"] = df_active["Prezzo Finale"] / df_active["Numero Bottiglie"].replace(0, 1)

                    df_stats = df_active.groupby(["Maison", "Tipologia", "Vintage"]).agg(
                        Min_Unitario=("Prezzo Unitario", "min"),
                        Media_Unitaria=("Prezzo Unitario", "mean"),
                        Mediana_Unitaria=("Prezzo Unitario", "median"),
                        Max_Unitario=("Prezzo Unitario", "max"),
                        Lotti=("Prezzo Unitario", "count"),
                    ).reset_index()
                    df_stats.sort_values(by=["Maison", "Lotti"], ascending=[True, False], inplace=True)
                    df_stats.to_excel(writer, sheet_name="Analisi Prezzi Maison", index=False)

                # --- Analisi Strategica (Riserva vs Successo) ---
                if "Prezzo Riserva" in df.columns:
                    df_strat = df.copy()
                    df_strat["Con_Offerte"] = df_strat["Numero Offerte"] > 0
                    res = df_strat.groupby("Prezzo Riserva").agg(
                        Totale=("url", "count"),
                        Venduti=("Con_Offerte", "sum"),
                        Media_Offerte=("Numero Offerte", "mean"),
                    ).reset_index()
                    res["Tasso_Successo_Perc"] = (res["Venduti"] / res["Totale"]) * 100
                    res.to_excel(writer, sheet_name="Analisi Strategica", index=False)

                logging.info(f"File Excel salvato: {path} (Attivi: {len(df_active)}, Non chiusi: {len(df_inactive)})")

        except Exception as e:
            logging.error(f"Errore generazione Excel: {e}")

    def run_analysis(self, df):
        """Genera il file di riepilogo (summary) per Maison."""
        if df.empty:
            return
        try:
            df = df.copy()
            df["Prezzo Finale"] = pd.to_numeric(df["Prezzo Finale"], errors="coerce")
            summary = df.groupby("Maison").agg(
                prezzo_min=("Prezzo Finale", "min"),
                prezzo_max=("Prezzo Finale", "max"),
                prezzo_medio=("Prezzo Finale", "mean"),
                prezzo_mediano=("Prezzo Finale", "median"),
                lotti_totali=("url", "count"),
                ultimo_stato=("status", "last"),
            ).reset_index()
            summary.to_excel(SUMMARY_PATH, index=False)
            logging.info("Analisi riassuntiva aggiornata.")
        except Exception as e:
            logging.error(f"Errore analisi riassuntiva: {e}")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    scraper = CatawikiScraper()
    try:
        scraper.run()
    except KeyboardInterrupt:
        logging.info("Interrotto manualmente. Uscita pulita.")
    except Exception as e:
        logging.critical(f"Errore fatale nello scheduler: {e}")


if __name__ == "__main__":
    main()