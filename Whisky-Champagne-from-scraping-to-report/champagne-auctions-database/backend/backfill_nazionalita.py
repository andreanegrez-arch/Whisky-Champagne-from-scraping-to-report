"""
backfill_nazionalita.py - recupera vincitore e nazionalita' dei lotti CHIUSI
gia' in archivio, rileggendo la loro pagina su Catawiki.

Perche'
-------
Fino al 30/09/2026 la nazionalita' veniva letta da un percorso sbagliato:
quasi tutti i lotti chiusi risultano "Unknown", e quelli con un paese hanno
spesso quello di chi guidava l'asta mentre era aperta, non del vincitore.

Cosa fa
-------
- Prende i lotti CLOSED non ancora elaborati con la logica nuova, dai piu'
  recenti ai piu' vecchi.
- Aggiorna SOLO nazionalita, winner_username, winner_id. Non tocca maison,
  distilleria, prezzi o altri campi (e quindi nemmeno le pulizie fatte a mano).
- Lotto non venduto (riserva non raggiunta): nazionalita' "Unknown".
- Va piano (una pagina ogni ~3-5 s) e si mette in PAUSA da solo quando e' in
  corso una sessione di scraping del backend o dello scheduler.
- Pagina 404: il lotto viene SEGNATO; se al riavvio successivo risponde di nuovo
  404 viene archiviato come ritirato da Catawiki (vedi lotti_ritirati.py).
- Si puo' interrompere in qualsiasi momento (Ctrl+C o chiudendo la finestra):
  i lotti gia' fatti sono salvati e al riavvio riparte da dove era rimasto.

Uso (dalla cartella backend, con il Python del progetto)
--------------------------------------------------------
    python backfill_nazionalita.py                 # tutto lo storico
    python backfill_nazionalita.py --mesi 3        # solo lotti chiusi negli ultimi 3 mesi
    python backfill_nazionalita.py --prova 10      # prova su 10 lotti, senza scrivere
"""

import argparse
import logging
import os
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from curl_cffi import requests  # noqa: E402

from database import DB_PATH  # noqa: E402
from html_compat import HTMLParser  # noqa: E402
from lot_status import detect_lot_status, extract_winner, get_bidding_block, CLOSED  # noqa: E402
import scrape_lock  # noqa: E402
import lotti_ritirati  # noqa: E402

LOG_DIR = os.path.join(os.path.dirname(HERE), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "backfill_nazionalita.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("backfill")
logging.getLogger("lot_status").setLevel(logging.ERROR)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}
# Esiti definitivi: questi lotti non vengono ripresi ai riavvii successivi.
DONE_RESULTS = ("ok", "invenduto", "ritirato")
TOKEN_RE = re.compile(r"^[0-9a-f]{40}$")


def connect():
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute(
        """CREATE TABLE IF NOT EXISTS backfill_nazionalita (
               url TEXT PRIMARY KEY,
               checked_at TEXT,
               esito TEXT,
               nazionalita_prima TEXT,
               nazionalita_dopo TEXT
           )"""
    )
    con.commit()
    return con


def lots_to_process(con, mesi=None):
    q = """SELECT l.url, l.nazionalita, l.winner_id, l.data_chiusura
           FROM lots l
           LEFT JOIN backfill_nazionalita b ON b.url = l.url AND b.esito IN (?, ?, ?)
           WHERE l.status = 'CLOSED' AND l.url IS NOT NULL AND b.url IS NULL"""
    params = list(DONE_RESULTS)
    if mesi:
        q += " AND l.data_chiusura >= ?"
        params.append((datetime.now() - timedelta(days=30 * mesi)).strftime("%Y-%m-%d"))
    q += " ORDER BY l.data_chiusura DESC"
    rows = con.execute(q, params).fetchall()
    # Gia' elaborati dalla logica nuova (winner_id = token Catawiki): si saltano
    return [r for r in rows if not TOKEN_RE.match(str(r[2] or ""))]


def wait_if_scraping():
    announced = False
    while True:
        active = scrape_lock.running_sessions()
        if not active:
            if announced:
                log.info("Sessione di scraping terminata: riprendo.")
            return
        if not announced:
            log.info(f"Pausa: sessione di scraping in corso ({', '.join(active)}). Ricontrollo ogni minuto.")
            announced = True
        time.sleep(60)


def fetch(session, url):
    """Restituisce (html | None, esito_errore | None)."""
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
        except Exception as e:
            log.warning(f"Errore di rete ({e}); riprovo tra 30 s")
            time.sleep(30)
            continue
        if r.status_code == 200:
            return r.text, None
        if r.status_code == 404:
            return None, "non_disponibile"
        if r.status_code in (403, 429, 503):
            wait = 15 * 60 * (attempt + 1)
            log.warning(f"Catawiki risponde {r.status_code}: rallento, pausa di {wait // 60} minuti")
            time.sleep(wait)
            continue
        return None, f"http_{r.status_code}"
    return None, "errore"


def save(con, url, esito, prima, dopo, winner=None, dry=False):
    if dry:
        return
    for attempt in range(5):
        try:
            if winner is not None:
                con.execute(
                    "UPDATE lots SET nazionalita = ?, winner_username = ?, winner_id = ? WHERE url = ?",
                    (winner["nazionalita"], winner["winner_username"], winner["winner_id"], url),
                )
            con.execute(
                "INSERT OR REPLACE INTO backfill_nazionalita VALUES (?, ?, ?, ?, ?)",
                (url, datetime.now().isoformat(timespec="seconds"), esito, prima, dopo),
            )
            con.commit()
            return
        except sqlite3.OperationalError as e:
            log.warning(f"Database occupato ({e}); riprovo")
            time.sleep(5 * (attempt + 1))
    log.error(f"Impossibile salvare {url}: lo riprendero' al prossimo avvio")


def main():
    ap = argparse.ArgumentParser(description="Recupera vincitore e nazionalita' dei lotti chiusi.")
    ap.add_argument("--mesi", type=int, help="solo lotti chiusi negli ultimi N mesi")
    ap.add_argument("--pausa", type=float, default=3.5, help="secondi medi tra una pagina e l'altra (default 3.5)")
    ap.add_argument("--prova", type=int, metavar="N", help="elabora N lotti senza scrivere nel database")
    args = ap.parse_args()
    dry = args.prova is not None

    con = connect()
    todo = lots_to_process(con, args.mesi)
    if dry:
        todo = todo[: args.prova]
    total = len(todo)
    log.info(f"Database: {DB_PATH}")
    log.info(f"Lotti da elaborare: {total}" + (" (PROVA: nessuna scrittura)" if dry else ""))
    if not total:
        return

    counts = {}
    session_id = "backfill-" + datetime.now().isoformat(timespec="seconds")
    session = requests.Session(impersonate="chrome120")
    session.headers.update(HEADERS)
    t0 = time.time()
    try:
        for i, (url, naz_prima, _wid, _dc) in enumerate(todo, 1):
            wait_if_scraping()
            html, err = fetch(session, url)
            if err == "non_disponibile":
                if dry:
                    esito = "404"
                else:
                    r404 = lotti_ritirati.register_404(url, session_id, "backfill")
                    esito = "ritirato" if r404 == lotti_ritirati.RITIRATO else "404_segnato"
                winner, naz_dopo = None, naz_prima
            elif err:
                esito, winner, naz_dopo = err, None, naz_prima
            else:
                tree = HTMLParser(html)
                status, _ = detect_lot_status(tree, url=url)
                if not get_bidding_block(tree):
                    esito, winner, naz_dopo = "dati_assenti", None, naz_prima
                elif status != CLOSED:
                    # Non dovrebbe succedere: se ne occupa lo scraper principale
                    esito, winner, naz_dopo = "aperto", None, naz_prima
                else:
                    winner = extract_winner(tree)
                    esito = "ok" if winner["sold"] else "invenduto"
                    naz_dopo = winner["nazionalita"]
            save(con, url, esito, naz_prima, naz_dopo, winner, dry)
            counts[esito] = counts.get(esito, 0) + 1
            if dry:
                log.info(f"[{i}/{total}] {esito:15s} {naz_prima} -> {naz_dopo}  {url}")
            elif i % 25 == 0 or i == total:
                rate = (time.time() - t0) / i
                eta = timedelta(seconds=int(rate * (total - i)))
                log.info(f"[{i}/{total}] {counts} - tempo stimato rimanente {eta}")
            time.sleep(max(1.0, random.uniform(args.pausa - 1.5, args.pausa + 1.5)))
    except KeyboardInterrupt:
        log.info("Interrotto: i lotti gia' elaborati sono salvati, al prossimo avvio riparte da qui.")
    finally:
        con.close()
        log.info(f"Riepilogo: {counts}")
        if not dry and (counts.get("ritirato") or counts.get("404_segnato")):
            try:
                n = lotti_ritirati.export_excel()
                log.info(f"Report '{lotti_ritirati.EXCEL_NAME}' aggiornato ({n} lotti ritirati)")
            except Exception as e:
                log.warning(f"Report lotti ritirati non aggiornato: {e}")


if __name__ == "__main__":
    main()
