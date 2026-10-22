import pandas as pd
from curl_cffi import requests
import time
import os
import logging
import sys
import re
import json
from datetime import datetime
import schedule

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
from lot_status import detect_lot_status, urls_still_open, closed_too_early_mask, extract_winner, closing_date_str, get_specifications  # noqa: E402
import importlib  # noqa: E402
import parsers as _parsers  # noqa: E402  (backend/parsers.py)
from parsers import parse_lot_title  # noqa: E402


def ricarica_parsers():
    """Rilegge backend/parsers.py a ogni sessione: le correzioni al parser
    (distillerie, imbottigliatori) valgono senza riavviare lo scheduler."""
    global parse_lot_title
    try:
        importlib.reload(_parsers)
        parse_lot_title = _parsers.parse_lot_title
    except Exception as e:
        logging.warning(f"parsers.py non ricaricato, uso la versione gia' in memoria: {e}")


def normalizza_imbottigliatori(df):
    """Colonna Imbottigliatore sempre compilata e con il nome esteso
    (es. "SMWS" -> "The Scotch Malt Whisky Society"). Le righe salvate prima che
    esistesse la colonna vengono calcolate dal titolo."""
    if df is None or df.empty:
        return df
    if "Imbottigliatore" not in df.columns:
        df["Imbottigliatore"] = None
    vuoti = df["Imbottigliatore"].isna() | (df["Imbottigliatore"].astype(str).str.strip() == "")
    if vuoti.any() and "title" in df.columns:
        dist = df["Distilleria"] if "Distilleria" in df.columns else pd.Series(None, index=df.index)
        df.loc[vuoti, "Imbottigliatore"] = [
            _parsers.detect_bottler(str(t or ""), None, str(d) if isinstance(d, str) else None)
            for t, d in zip(df.loc[vuoti, "title"].fillna(""), dist[vuoti])
        ]
    df["Imbottigliatore"] = df["Imbottigliatore"].map(
        lambda v: (_parsers.canonical_bottler(v) or v) if isinstance(v, str) else v)
    return df


def ordina_per_rilevazione(df):
    """Ordine dei fogli Excel: prima il giorno della rilevazione (colonna
    "timestamp", piu' recente in alto), poi alfabetico per Distilleria e
    Imbottigliatore. La colonna timestamp e' la prima del foglio."""
    if df is None or df.empty:
        return df
    df = df.copy()
    chiavi, asc = [], []
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        df["timestamp"] = ts
        df["_giorno"] = ts.dt.normalize()
        chiavi.append("_giorno"); asc.append(False)
    for col in ("Distilleria", "Imbottigliatore"):
        if col in df.columns:
            df["_k_" + col] = df[col].fillna("").astype(str).str.casefold()
            chiavi.append("_k_" + col); asc.append(True)
    if "timestamp" in df.columns:
        chiavi.append("timestamp"); asc.append(False)
    if chiavi:
        df = df.sort_values(chiavi, ascending=asc, kind="stable", na_position="last")
    df = df.drop(columns=[c for c in df.columns if c == "_giorno" or c.startswith("_k_")])
    if "timestamp" in df.columns:
        df = df[["timestamp"] + [c for c in df.columns if c != "timestamp"]]
    return df

# --- CONFIGURAZIONE ---
CATEGORY_URL = "https://www.catawiki.com/en/c/437-whisky"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS_ITA = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}

def get_monthly_paths():
    now = datetime.now()
    mese_nome = MONTHS_ITA[now.month]
    excel_name = f"database whisky {mese_nome}.xlsx"
    summary_name = f"auctions_summary_{mese_nome}.xlsx"
    
    excel_path = os.path.join(ROOT_DIR, "data", excel_name)
    summary_path = os.path.join(ROOT_DIR, "data", summary_name)
    return excel_path, summary_path

DATA_PATH, SUMMARY_PATH = get_monthly_paths()
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "scraper_historic.log")

# SCRAPE_INTERVAL = 600  # Rimosso: ora basato su orari fissi (12:00, 21:30)
MAX_PAGES_SAFETY = 100  # Limite di sicurezza per la scansione totale

# Setup cartelle
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True)
os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)

class CatawikiScraper:

    def __init__(self):
        self.db_path = DATA_PATH

    def load_data(self):

        if os.path.exists(DATA_PATH):
            try:
                # Tenta caricamento da più fogli per preservare tutto lo storico
                xls = pd.ExcelFile(DATA_PATH)
                dfs = []
                for sname in ['Dati', 'Lotti non chiusi']:
                    if sname in xls.sheet_names:
                        dfs.append(pd.read_excel(xls, sheet_name=sname))
                
                if not dfs:
                    df = pd.read_excel(DATA_PATH)
                else:
                    df = pd.concat(dfs, ignore_index=True)

                if 'Distilleria' in df.columns:
                    df['Distilleria'] = df['Distilleria'].apply(self.clean_distilleria_name)
                return df
            except Exception as e:
                logging.warning(f"Errore caricamento Excel: {e}. Fallback standard.")
                try:
                    df = pd.read_excel(DATA_PATH)
                    if 'Distilleria' in df.columns:
                        df['Distilleria'] = df['Distilleria'].apply(self.clean_distilleria_name)
                    return df
                except: pass

        return pd.DataFrame(columns=[
            "Distilleria", "Imbottigliatore", "Stile", "Numero Bottiglie", "Formato", "Eta",
            "Data Chiusura", "Prezzo Riserva", "Numero Offerte", "Nazionalita",
            "Prezzo Finale", "Costi Spedizione", "title", "currency", "status", "url", "timestamp",
            "winner_username", "winner_id"
        ])

    def clean_price(self, price_str):
        if not price_str:
            return None, None

        currency = "".join([c for c in price_str if not c.isdigit() and c not in "., "]).strip()
        num_part = "".join([c for c in price_str if c.isdigit() or c in ".,"]).strip()

        if not num_part:
            return None, currency

        # Avanzata: gestisce migliaia (punto) e decimali (virgola)
        if "," in num_part and "." in num_part:
            last_dot = num_part.rfind(".")
            last_comma = num_part.rfind(",")
            if last_comma > last_dot: # 2.400,00
                num_part = num_part.replace(".", "").replace(",", ".")
            else: # 2,400.00
                num_part = num_part.replace(",", "").replace(".", ".")
        elif "," in num_part: # 2400,00
            num_part = num_part.replace(",", ".")
        elif "." in num_part: # 2.400 (migliaia) vs 2.40 (decimale)
            parts = num_part.split(".")
            # Se il blocco dopo il punto è di 3 cifre, sono quasi certamente migliaia
            if len(parts) == 2 and len(parts[1]) == 3:
                num_part = num_part.replace(".", "")
            # Se ha più di un punto (es. 1.200.000)
            elif len(parts) > 2:
                num_part = num_part.replace(".", "")
        
        return num_part, currency

    def normalize_url(self, url):
        """Rimuove parametri query e slash finali per evitare duplicati"""
        if not url: return url
        # Rimuove tutto ciò che segue '?' (parametri come utm_source, ecc.)
        url = url.split("?")[0]
        # Rimuove lo slash finale se presente
        if url.endswith("/"):
            url = url[:-1]
        return url

    def clean_distilleria_name(self, name):
        """Rimuove l'annata iniziale dal nome della Distilleria (es. 1990 Dom Perignon -> Dom Perignon)"""
        if not name or not isinstance(name, str):
            return name
        # Rimuove 4 cifre seguite da spazio all'inizio della stringa
        return re.sub(r'^\d{4}\s+', '', name).strip()

    def get_lot_details(self, session, url):

        try:
            r = session.get(url, timeout=30)
            LAST_HTTP_STATUS[url] = r.status_code
            if r.status_code != 200:
                logging.error(f"Errore status code {r.status_code} su {url}")
                return None

            # Lotto vecchio reindirizzato alla categoria o a un NUOVO lotto (bottiglia
            # rimessa all'asta): i dati della pagina non sono di questo lotto.
            if not bidding_api.stesso_lotto(url, r.text, str(getattr(r, 'url', '') or '')):
                logging.info(f"Pagina di un altro lotto (reindirizzamento), ignorata: {url}")
                return None

            tree = HTMLParser(r.text)
            title = "Unknown"

            title_el = tree.css_first("h1")

            if title_el:
                title = title_el.text().strip()

            # Prezzo ed esito dal blocco offerte della pagina (vedi backend/bidding_api.py).
            # Prima si prendeva il PRIMO numero del riquadro offerte: sui lotti chiusi e
            # non venduti era la STIMA del perito, e clean_price trasformava '1,250' in 1.25.
            _esito = bidding_api.da_pagina(tree)
            if _esito is None:
                logging.warning(f"Blocco offerte assente, lotto saltato: {url}")
                return None
            price, currency = _esito['prezzo_finale'], 'EUR'
            bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
            # 1. Distilleria: scheda del lotto su Catawiki ("Distillery"), poi titolo.
            # Stessa logica del backend (backend/parsers.py). Prima si usava il
            # "brand" del ld+json o la prima parte del titolo prima della virgola.
            _parsed = parse_lot_title(title, specs=get_specifications(tree))
            distilleria = _parsed["distilleria"]
            imbottigliatore = _parsed.get("imbottigliatore")
            distilleria = self.clean_distilleria_name(distilleria) # <-- Pulizia Distilleria

            # 2. Analisi Titolo (Eta, Count, Format, Type)
            eta = "NV"
            age_match = re.search(r'\b(\d{1,2})\s*(?:Years?|Y\.?O\.?|Year Old)\b', title, re.I)
            year_match = re.search(r'\b(18|19|20)\d{2}\b', title)
            
            if age_match and year_match:
                eta = f"{age_match.group(1)} Years ({year_match.group(0)})"
            elif age_match:
                eta = f"{age_match.group(1)} Years"
            elif year_match:
                eta = year_match.group(0)
                
            count = "1"
            count_match = re.search(r'(?:\s|^|\-)\s*([1-9]\d{0,1})\s*(?:bottles|bottiglie|magnums|magnum|bottiglia|bottle)\b', title, re.I)
            if count_match:
                count = count_match.group(1)
                
            format_val = "0.70" # Default europeo standard per i superalcolici (70cl)
            if re.search(r'\b(1\s?[Ll]itri?|100\s?[Cc]l|1000\s?[Mm][Ll])\b', title, re.I):
                format_val = "1.0"
            elif re.search(r'\b(75\s?[Cc]l|750\s?[Mm][Ll])\b', title, re.I):
                format_val = "0.75"
            elif re.search(r'\b(50\s?[Cc]l|500\s?[Mm][Ll]|Half\s?[Ll]itre)\b', title, re.I):
                format_val = "0.50"
            elif re.search(r'\b(1\.5\s?[Ll]|150\s?[Cc]l|Magnum)\b', title, re.I):
                format_val = "Magnum 1.5 L"
                
            whisky_type = "Single Malt" # Assunzione base standard su Catawiki
            title_lower = title.lower()
            if "blended" in title_lower:
                whisky_type = "Blended"
            elif "bourbon" in title_lower:
                whisky_type = "Bourbon"
            elif "rye" in title_lower:
                whisky_type = "Rye"
            elif "single cask" in title_lower:
                whisky_type = "Single Cask"
            elif "grain" in title_lower:
                whisky_type = "Single Grain"
            # 3. Asta

            # Orario di chiusura reale del lotto (UTC), vedi backend/lot_status.py
            closing_date = closing_date_str(tree)

            # Identifica lo status
            # Logica in backend/lot_status.py: lot_state ufficiale, scadenza vs ora
            # attuale (in UTC), timer del conto alla rovescia. La vecchia ricerca di
            # "final bid" su tutta la pagina segnava CHIUSE anche le aste aperte.
            bid_section = tree.css_first('[data-testid="lot-bid-status-section"]')
            status, status_reason = detect_lot_status(tree, url=url)
            logging.debug(f"Stato {status} ({status_reason})")

            bids_count = "0"
            for node in tree.css("span, div, button"):
                if "all bids" in node.text().lower():
                    m = re.search(r'\((\d+)\)', node.text())
                    if m:
                        bids_count = m.group(1)
                        break
                    
            reserve_price = "N"
            if bid_section and "reserve price" in bid_section.text().lower():
                if "no reserve" not in bid_section.text().lower():
                    reserve_price = "Y"
                
            # Vincitore e nazionalita' dal blocco offerte della pagina (vedi
            # backend/lot_status.py). Valorizzati solo per lotti chiusi E venduti:
            # prima si leggeva la prima bandierina della pagina, cioe' chi guidava
            # l'asta in quel momento, e sui lotti chiusi il risultato era "Unknown".
            winner = extract_winner(tree)
            bidder_nationality = winner["nazionalita"]
            winner_username = winner["winner_username"]
            winner_id = winner["winner_id"]

            # 4. Spedizione (Best effort)
            shipping = "N/A"
            for node in tree.css("div"):
                if "shipping" in node.text().lower()[:20] and re.search(r'\d+', node.text()):
                    shipping = node.text().strip()[:30]
                    break

            return {
                "Distilleria": distilleria,
                "Imbottigliatore": imbottigliatore,
                "Stile": whisky_type,
                "Numero Bottiglie": count,
                "Formato": format_val,
                "Eta": eta,
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
                "url": url,
                "winner_username": winner_username,
                "winner_id": winner_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }


        except Exception as e:

            logging.error(f"Errore scraping lotto {url}: {e}")
            return None
    def run_session(self):
        """Sessione di scraping, segnalata con un file di lock (vedi backend/scrape_lock.py)."""
        scrape_lock.acquire("scheduler")
        try:
            self._run_session_unlocked()
        finally:
            scrape_lock.release("scheduler")

    def _run_session_unlocked(self):
        """Esegue una singola sessione di scraping e salva i risultati"""
        global DATA_PATH, SUMMARY_PATH
        DATA_PATH, SUMMARY_PATH = get_monthly_paths()
        ricarica_parsers()
        
        df_historic = self.load_data()
        
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
                "Referer": "https://www.catawiki.com/en/c/437-whisky"
            })

            logging.info(f"Accesso alla categoria: {CATEGORY_URL}")
            
            p_idx = 1
            urls = set()
            while p_idx <= MAX_PAGES_SAFETY:
                try:
                    p_url = f"{CATEGORY_URL}?page={p_idx}" if p_idx > 1 else CATEGORY_URL
                    logging.info(f"Scansione categoria pagina {p_idx}: {p_url}")
                    
                    resp = session.get(p_url, timeout=30)
                    if resp.status_code != 200:
                        logging.warning(f"Pagina {p_idx} non raggiungibile: {resp.status_code}")
                        break
                        
                    parser = HTMLParser(resp.text)
                    page_urls = [
                        a.attributes.get('href') 
                        for a in parser.css('a.c-lot-card') 
                        if a.attributes.get('href') and '/l/' in a.attributes.get('href')
                    ]
                    
                    if not page_urls:
                        logging.info(f"Nessun lotto trovato alla pagina {p_idx}. Fine scansione.")
                        break
                        
                    logging.info(f"Trovati {len(page_urls)} link potenziali nella pagina {p_idx}")
                    urls.update(page_urls)
                    
                    p_idx += 1
                    time.sleep(1) # Delay tra le pagine
                except Exception as e:
                    logging.error(f"Errore durante scansione pagina {p_idx}: {e}")
                    break
            
            urls = list(urls)
            logging.info(f"Totale lotti unici trovati: {len(urls)}.")

            # Ri-scraping dei lotti ancora aperti nello storico: quando un'asta
            # chiude sparisce dalla categoria, e senza questo passaggio il prezzo
            # finale non verrebbe mai registrato. Include i lotti segnati CLOSED
            # prima della scadenza dalla vecchia logica.
            if not df_historic.empty and "status" in df_historic.columns:
                n_early = int(closed_too_early_mask(df_historic).sum())
                if n_early:
                    logging.info(f"{n_early} rilevazioni CLOSED fatte prima della scadenza: lotti da ricontrollare.")
                known = {self.normalize_url(u) for u in urls}
                for ou in urls_still_open(df_historic):
                    nu = self.normalize_url(ou)
                    if nu and nu not in known:
                        urls.append(nu)
                        known.add(nu)
                logging.info(f"Totale lotti da analizzare (nuovi + aperti precedenti): {len(urls)}")

            new_entries = []

            for i, url in enumerate(urls):
                logging.info(f"[{i+1}/{len(urls)}] Analisi: {url}")
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
                time.sleep(1) # delay per evitare rate limit

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

        if new_entries:
            df_new = pd.DataFrame(new_entries)
            df_historic = pd.concat([df_historic, df_new], ignore_index=True)

            if "timestamp" in df_historic.columns:
                df_historic["timestamp"] = pd.to_datetime(df_historic["timestamp"])
                df_historic.sort_values("timestamp", inplace=True)

            df_historic.drop_duplicates(
                subset=["url"],
                keep="last",
                inplace=True
            )
            
            if "Distilleria" in df_historic.columns:
                df_historic = df_historic.sort_values(by="Distilleria")

            logging.info(f"Aggiunte {len(new_entries)} nuove rilevazioni.")

        self.save_advanced_excel(df_historic, DATA_PATH)
        self.run_analysis(df_historic)
        logging.info("=== SESSIONE COMPLETATA ===")

    def run(self):
        """Configura e avvia lo scheduler per le sessioni giornaliere"""
        schedule.every().day.at("03:00").do(self.run_session)
        schedule.every().day.at("17:00").do(self.run_session)
        
        # Un lock "scheduler" rimasto da una sessione interrotta (finestra chiusa,
        # PC spento) non e' piu' valido: questo processo non ha sessioni in corso.
        scrape_lock.release("scheduler")
        logging.info("=== SCHEDULER AVVIATO ===")
        logging.info("Sessioni programmate giornalmente alle 03:00 e 17:00.")
        
        # Sessione subito all'avvio, tranne se il backend sta gia' facendo scraping:
        # due scraping insieme raddoppiano le richieste verso Catawiki.
        attive = [s for s in scrape_lock.running_sessions() if s != "scheduler"]
        if attive:
            logging.info(f"Scraping gia' in corso ({', '.join(attive)}): salto la sessione di avvio, "
                         f"la prossima parte all'orario programmato.")
        else:
            self.run_session()

        while True:
            schedule.run_pending()
            time.sleep(60) # Controllo ogni minuto

    def save_advanced_excel(self, df, path):
        """Salva Excel con fogli separati per bidders, grafici e pivot automatici"""
        try:
            # Assicurati che Numero Bottiglie e Prezzo Finale siano numerici per i calcoli
            df['Numero Bottiglie'] = pd.to_numeric(df['Numero Bottiglie'], errors='coerce').fillna(0)
            df['Numero Offerte'] = pd.to_numeric(df['Numero Offerte'], errors='coerce').fillna(0)
            # Imbottigliatore compilato e con il nome esteso in tutti i fogli
            df = normalizza_imbottigliatori(df)
            
            # Split dei dati: 
            # Dati (Almeno 1 offerta E Nazionalità conosciuta)
            # Lotti non chiusi (0 offerte O Nazionalità Unknown)
            df_active = df[(df['Numero Offerte'] > 0) & (df['Nazionalita'] != "Unknown")].copy()
            df_inactive = df[(df['Numero Offerte'] == 0) | (df['Nazionalita'] == "Unknown")].copy()
            
            # Imbottigliatore compilato con il nome esteso; ordine: giorno della
            # rilevazione (timestamp) e poi alfabetico per Distilleria / Imbottigliatore
            df_active = ordina_per_rilevazione(df_active)
            df_inactive = ordina_per_rilevazione(df_inactive)

            # nan_inf_to_errors: una cella vuota/NaN nei calcoli non deve far fallire
            # l'intero salvataggio (prima l'Excel usciva troncato con errore NAN/INF).
            with pd.ExcelWriter(path, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}}) as writer:
                # 1. Foglio Dati (Solo con bidders)
                df_active.to_excel(writer, sheet_name='Dati', index=False)
                
                # 2. Foglio Lotti non chiusi (0 bidders)
                df_inactive.to_excel(writer, sheet_name='Lotti non chiusi', index=False)
                
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
                    det_cols = [c for c in ["Nazionalita", "Distilleria", "Imbottigliatore", "Stile", "Eta", "Formato", "Numero Bottiglie",
                                            "Prezzo Finale", "Data Chiusura", "Numero Offerte",
                                            "winner_username", "title", "url"] if c in nat_src.columns]
                    det = nat_src.sort_values(["Nazionalita", "Data Chiusura"], ascending=[True, False])[det_cols]
                    det.to_excel(writer, sheet_name="Dettaglio Nazionalita", index=False)
                    sh_det = writer.sheets["Dettaglio Nazionalita"]
                    sh_det.autofilter(0, 0, len(det), len(det_cols) - 1)
                    sh_det.freeze_panes(1, 0)

                # 3. Analisi Volume Distilleria (Bar Chart)
                if 'Distilleria' in df.columns and 'Numero Bottiglie' in df.columns:
                    # Assicuriamoci che Numero Bottiglie sia numerico
                    df_copy = df.copy()
                    df_copy['Numero Bottiglie'] = pd.to_numeric(df_copy['Numero Bottiglie'], errors='coerce').fillna(1)
                    
                    # Raggruppiamo per Distilleria + Stile per maggiore dettaglio richiesto
                    group_cols = ['Distilleria']
                    if 'Stile' in df.columns:
                        group_cols.append('Stile')
                    
                    df_vol = df_copy.groupby(group_cols)['Numero Bottiglie'].sum().sort_values(ascending=False).reset_index()
                    df_vol.to_excel(writer, sheet_name='Analisi Volume Distilleria', index=False)
                    
                    sh_vol = writer.sheets['Analisi Volume Distilleria']
                    chart_vol = workbook.add_chart({'type': 'column'})
                    
                    # Nome categoria è Distilleria + Stile
                    if 'Stile' in df.columns:
                        # Creiamo una colonna combinata per l'asse X del grafico
                        df_vol['Etichetta'] = df_vol['Distilleria'] + " (" + df_vol['Stile'].astype(str) + ")"
                        # Scriviamo la colonna etichetta per usarla nel grafico
                        df_vol[['Etichetta']].to_excel(writer, sheet_name='Analisi Volume Distilleria', startcol=len(group_cols)+1, index=False)
                        cat_col = len(group_cols)+1
                    else:
                        cat_col = 0

                    chart_vol.add_series({
                        'name': 'Bottiglie Totali',
                        'categories': ['Analisi Volume Distilleria', 1, cat_col, len(df_vol), cat_col],
                        'values':     ['Analisi Volume Distilleria', 1, len(group_cols), len(df_vol), len(group_cols)],
                        'data_labels': {'value': True, 'font': {'size': 8, 'bold': True}},
                    })
                    chart_vol.set_title({'name': 'Volume Vendite (Distilleria & Stile) - Solo Lotti con Bidders'})
                    chart_vol.set_x_axis({'name': 'Distilleria (Stile)', 'label_position': 'low'})
                    chart_vol.set_y_axis({'name': 'Q.tà Bottiglie'})
                    chart_vol.set_size({'width': 1000, 'height': 500})
                    sh_vol.insert_chart('E2', chart_vol)

                # 5. Analisi Rendimento (Performance Chart)
                sh_perf = workbook.add_worksheet('Analisi Rendimento')
                total_lots = len(df)
                active_count = len(df_active)
                inactive_count = len(df_inactive)
                
                perf_data = [
                    ['Categoria', 'Lotti'],
                    ['Con Offerte', active_count],
                    ['Senza Offerte/Unknown', inactive_count]
                ]
                for r_idx, row in enumerate(perf_data):
                    sh_perf.write_row(r_idx, 0, row)
                
                chart_perf = workbook.add_chart({'type': 'pie'})
                chart_perf.add_series({
                    'name': 'Rendimento Aste del Mese',
                    'categories': ['Analisi Rendimento', 1, 0, 2, 0],
                    'values':     ['Analisi Rendimento', 1, 1, 2, 1],
                    'data_labels': {'percentage': True, 'category': True, 'position': 'outside_end'},
                })
                chart_perf.set_title({'name': f'Success Rate Whisky - Totale {total_lots} Lotti'})
                sh_perf.insert_chart('D2', chart_perf)

                # 6. Analisi Prezzi Distilleria (Prezzo Unitario & Trend)
                if not df_active.empty:
                    sh_price = workbook.add_worksheet('Analisi Prezzi Distilleria')
                    
                    # Calcolo Prezzo Unitario
                    df_active['Prezzo Finale'] = pd.to_numeric(df_active['Prezzo Finale'], errors='coerce').fillna(0)
                    df_active['Numero Bottiglie'] = pd.to_numeric(df_active['Numero Bottiglie'], errors='coerce').fillna(1)
                    df_active['Prezzo Unitario'] = df_active['Prezzo Finale'] / df_active['Numero Bottiglie']
                    
                    # Tabella Riassuntiva: Gruppo per Distilleria-Stile-Eta
                    df_stats = df_active.groupby(['Distilleria', 'Stile', 'Eta']).agg(
                        Min_Unitario=('Prezzo Unitario', 'min'),
                        Media_Unitaria=('Prezzo Unitario', 'mean'),
                        Max_Unitario=('Prezzo Unitario', 'max'),
                        Lotti=('Prezzo Unitario', 'count')
                    ).reset_index()
                    df_stats.sort_values(by=['Distilleria', 'Lotti'], ascending=[True, False], inplace=True)
                    
                    # Scrivi Tabella Riassuntiva
                    headers_stats = list(df_stats.columns)
                    sh_price.write_row(0, 0, headers_stats)
                    for r_idx, row_data in enumerate(df_stats.values):
                        sh_price.write_row(r_idx + 1, 0, row_data)
                        
                    # Tabella per Grafico Temporale (Top 5 combinazioni più frequenti per leggibilità)
                    top_combos = df_stats.head(5)[['Distilleria', 'Stile', 'Eta']]
                    
                    # Log temporale filtrato per il grafico
                    df_trend = df_active.copy()
                    df_trend['Data'] = pd.to_datetime(df_trend['Data Chiusura'], errors='coerce').dt.date
                    df_trend = df_trend.sort_values('Data')
                    
                    # Scrittura log temporale per riferimento grafico
                    start_col_trend = 8
                    sh_price.write(0, start_col_trend, "Log Temporale (Top Combinazioni)")
                    sh_price.write_row(1, start_col_trend, ["Data", "Identificativo", "Prezzo Unitario"])
                    
                    row_ptr = 2
                    for _, combo in top_combos.iterrows():
                        m, t, v = combo['Distilleria'], combo['Stile'], combo['Eta']
                        label = f"{m} {t} {v}"
                        subset = df_trend[(df_trend['Distilleria'] == m) & (df_trend['Stile'] == t) & (df_trend['Eta'] == v)]
                        for _, r in subset.iterrows():
                            sh_price.write_row(row_ptr, start_col_trend, [str(r['Data']), label, r['Prezzo Unitario']])
                            row_ptr += 1
                    
                    # Inserimento Grafico Temporale
                    if row_ptr > 2:
                        chart_trend = workbook.add_chart({'type': 'column'})
                        chart_trend.add_series({
                            'name': 'Andamento Prezzo Unitario',
                            'categories': ['Analisi Prezzi Distilleria', 2, start_col_trend, row_ptr-1, start_col_trend],
                            'values':     ['Analisi Prezzi Distilleria', 2, start_col_trend+2, row_ptr-1, start_col_trend+2],
                        })
                        chart_trend.set_title({'name': 'Andamento Prezz Unitario (Top 5 Prodotti)'})
                        chart_trend.set_x_axis({'name': 'Data di Chiusura'})
                        chart_trend.set_y_axis({'name': 'Prezzo per Bottiglia (€)'})
                        chart_trend.set_size({'width': 900, 'height': 500})
                        sh_price.insert_chart('N2', chart_trend)
                        
                # 7. Analisi Strategica (Riserva vs Successo)
                sh_strat = workbook.add_worksheet('Analisi Strategica')
                
                # Filtriamo i dati per l'analisi
                # Successo = Numero Offerte > 0
                df_strat = df.copy()
                df_strat['Numero Offerte'] = pd.to_numeric(df_strat['Numero Offerte'], errors='coerce').fillna(0)
                df_strat['Con_Offerte'] = df_strat['Numero Offerte'] > 0
                
                # Raggruppamento per Prezzo Riserva (Y/N)
                if 'Prezzo Riserva' in df_strat.columns:
                    res_analysis = df_strat.groupby('Prezzo Riserva').agg(
                        Totale=('url', 'count'),
                        Venduti=('Con_Offerte', 'sum'),
                        Media_Offerte=('Numero Offerte', 'mean')
                    ).reset_index()
                    
                    res_analysis['Tasso_Successo_Perc'] = (res_analysis['Venduti'] / res_analysis['Totale']) * 100
                    
                    # Scrittura dati
                    sh_strat.write(0, 0, "Analisi Impatto Prezzo di Riserva")
                    res_headers = ["Prezzo Riserva", "Lotti Totali", "Lotti con Offerte", "Media Offerte", "Tasso Successo %"]
                    sh_strat.write_row(1, 0, res_headers)
                    for r_idx, row_data in enumerate(res_analysis.values):
                        sh_strat.write_row(r_idx + 2, 0, row_data)
                    
                    # Grafico 1: Tasso di Successo
                    chart_succ = workbook.add_chart({'type': 'column'})
                    chart_succ.add_series({
                        'name': 'Tasso di Successo %',
                        'categories': ['Analisi Strategica', 2, 0, 1 + len(res_analysis), 0],
                        'values':     ['Analisi Strategica', 2, 4, 1 + len(res_analysis), 4],
                    })
                    chart_succ.set_title({'name': 'Impatto Riserva su Tasso di Successo (Aste con Offerte)'})
                    chart_succ.set_y_axis({'name': '% Successo'})
                    sh_strat.insert_chart('G2', chart_succ)
                    
                    # Grafico 2: Numero Medio Offerte
                    chart_bids = workbook.add_chart({'type': 'column'})
                    chart_bids.add_series({
                        'name': 'Media Offerte per Lotto',
                        'categories': ['Analisi Strategica', 2, 0, 1 + len(res_analysis), 0],
                        'values':     ['Analisi Strategica', 2, 3, 1 + len(res_analysis), 3],
                    })
                    chart_bids.set_title({'name': 'Impatto Riserva su Numero Medio di Offerte'})
                    chart_bids.set_y_axis({'name': 'Media Offerte'})
                    sh_strat.insert_chart('G18', chart_bids)

                # 8. Dashboard Prezzi (Dinamica)
                sh_dash = workbook.add_worksheet('Dashboard Prezzi')
                sh_hidden = workbook.add_worksheet('Data_Trend_Hidden')
                
                # Prepariamo i dati per il foglio nascosto (Garantendo stringhe per ID_Prodotto)
                df_trend_all = df.copy()
                df_trend_all['Distilleria'] = df_trend_all['Distilleria'].fillna('Unknown')
                df_trend_all['Stile'] = df_trend_all['Stile'].fillna('NV')
                df_trend_all['Eta'] = df_trend_all['Eta'].fillna('NV')
                
                df_trend_all['ID_Prodotto'] = df_trend_all['Distilleria'].astype(str) + " " + \
                                              df_trend_all['Stile'].astype(str) + " " + \
                                              df_trend_all['Eta'].astype(str)
                
                df_trend_all['Data_Chiusura'] = pd.to_datetime(df_trend_all['Data Chiusura'], errors='coerce').dt.strftime('%Y-%m-%d')
                df_trend_all['Prezzo_Unitario'] = pd.to_numeric(df_trend_all['Prezzo Finale'], errors='coerce').fillna(0) / \
                                                  pd.to_numeric(df_trend_all['Numero Bottiglie'], errors='coerce').fillna(1)
                
                # Scrittura dati nel foglio nascosto
                sh_hidden.write_row(0, 0, ["Data", "ID_Prodotto", "Prezzo_Unitario"])
                for i, row in enumerate(df_trend_all[['Data_Chiusura', 'ID_Prodotto', 'Prezzo_Unitario']].values):
                    sh_hidden.write_row(i + 1, 0, row)
                
                # Lista unica prodotti per dropdown
                unique_ids = sorted(df_trend_all['ID_Prodotto'].unique())
                sh_hidden.write_column(0, 5, ["LISTA_PRODOTTI"] + unique_ids)
                
                # Configurazione Dashboard
                sh_dash.set_column('A:A', 20)
                sh_dash.set_column('B:B', 40)
                sh_dash.write('A2', 'Seleziona Prodotto:', workbook.add_format({'bold': True}))
                
                # Dropdown in B2
                sh_dash.data_validation('B2', {
                    'validate': 'list',
                    'source': f'=Data_Trend_Hidden!$F$2:$F${1+len(unique_ids)}',
                    'input_message': 'Scegli una Distilleria e Annata',
                })
                sh_dash.write('B2', unique_ids[0] if unique_ids else "")
                
                # Formule dinamiche per estrarre i dati del grafico (E5:F100)
                sh_dash.write('E4', 'Data', workbook.add_format({'bold': True}))
                sh_dash.write('F4', 'Prezzo', workbook.add_format({'bold': True}))
                
                for r in range(5, 105):
                    # Formula dinamica (utilizza AGGREGATE per Excel desktop)
                    formula_date = f'=IFERROR(INDEX(Data_Trend_Hidden!$A$2:$A$5000, AGGREGATE(15, 6, (ROW(Data_Trend_Hidden!$B$2:$B$5000)-ROW(Data_Trend_Hidden!$B$1))/(Data_Trend_Hidden!$B$2:$B$5000=$B$2), ROW(A{r-4}))), "")'
                    formula_price = f'=IFERROR(INDEX(Data_Trend_Hidden!$C$2:$C$5000, AGGREGATE(15, 6, (ROW(Data_Trend_Hidden!$B$2:$B$5000)-ROW(Data_Trend_Hidden!$B$1))/(Data_Trend_Hidden!$B$2:$B$5000=$B$2), ROW(A{r-4}))), "")'
                    sh_dash.write_formula(r-1, 4, formula_date)
                    sh_dash.write_formula(r-1, 5, formula_price)

                # Fallback: Scriviamo i dati del PRIMO prodotto in chiaro come valori statici nelle prime righe
                # per garantire che Google Sheets/Edge mostrino qualcosa subito.
                if unique_ids:
                    first_prod = unique_ids[0]
                    subset = df_trend_all[df_trend_all['ID_Prodotto'] == first_prod].head(100)
                    for i, row in enumerate(subset[['Data_Chiusura', 'Prezzo_Unitario']].values):
                        # Scriviamo sopra le formule (Excel le ricalcolerà se aperto in desktop, 
                        # ma online vedremo questi valori)
                        sh_dash.write(i + 4, 4, row[0])
                        sh_dash.write(i + 4, 5, row[1])
                
                # Grafico dinamico
                chart_dash = workbook.add_chart({'type': 'column'})
                chart_dash.add_series({
                    'name': 'Andamento Valore Unitario (€)',
                    'categories': ['Dashboard Prezzi', 4, 4, 104, 4],
                    'values':     ['Dashboard Prezzi', 4, 5, 104, 5],
                    'data_labels': {'value': True, 'position': 'outside_end'},  # 'top' non esiste per i grafici a colonne
                })
                chart_dash.set_title({'name': '= "Andamento Prezzi: " & B2'})
                chart_dash.set_x_axis({'name': 'Data di Chiusura'})
                chart_dash.set_y_axis({'name': 'Prezzo per Bottiglia (€)'})
                chart_dash.set_size({'width': 800, 'height': 450})
                chart_dash.show_hidden_data()
                sh_dash.insert_chart('A4', chart_dash)
                
                # Nascondiamo le colonne di appoggio E:F per estetica
                sh_dash.set_column('E:F', None, None, {'hidden': True})
                # Nascondiamo il foglio dei dati trend
                sh_hidden.hide()

                logging.info(f"File Excel avanzato salvato in: {path} (Dati: {len(df_active)}, Non chiusi: {len(df_inactive)})")
        except Exception as e:
            logging.error(f"Errore generazione Excel avanzato: {e}")

    def run_analysis(self, df):

        try:

            df["Prezzo Finale"] = pd.to_numeric(df["Prezzo Finale"], errors="coerce")

            summary = df.groupby("Distilleria").agg(
                prezzo_min=("Prezzo Finale", "min"),
                prezzo_max=("Prezzo Finale", "max"),
                prezzo_medio=("Prezzo Finale", "mean"),
                lotti_totali=("url", "count"),
                ultimo_stato=("status", "last")
            ).reset_index()

            summary.to_excel(SUMMARY_PATH, index=False)

            logging.info("Analisi riassuntiva aggiornata.")

        except Exception as e:

            logging.error(f"Errore analisi: {e}")


def main():
    scraper = CatawikiScraper()
    try:
        scraper.run()
    except Exception as e:
        logging.critical(f"Errore fatale nello scheduler: {e}")


if __name__ == "__main__":
    main()