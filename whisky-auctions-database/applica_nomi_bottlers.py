"""
applica_nomi_bottlers.py - aggiorna il backend whisky con i nomi estesi degli
imbottigliatori ("The Scotch Malt Whisky Society" al posto di "SMWS", ecc.) e
l'elenco /api/analysis/bottlers in ordine alfabetico.

I file nuovi sono in aggiornamenti_backend/. Copiarli in backend/ fa ripartire
il backend (uvicorn --reload): se lo fa durante uno scraping il frontend resta
bloccato fino alla fine. Per questo lo script ASPETTA che finisca la sessione di
scraping del backend (file .scraping-backend.lock), poi:
  1. copia i file in backend/
  2. rinomina nel database gli imbottigliatori abbreviati (con copia di sicurezza)

Si avvia con applica_nomi_bottlers.bat; la finestra puo' restare aperta in attesa.
"""

import os
import shutil
import sqlite3
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "aggiornamenti_backend")
BACKEND = os.path.join(HERE, "backend")
DB_PATH = os.path.join(BACKEND, "Whisky SQLite.db")
LOCK = os.path.join(HERE, ".scraping-backend.lock")
STALE_HOURS = 12  # come backend/scrape_lock.py

NOMI_ESTESI = {
    "SMWS": "The Scotch Malt Whisky Society",
    "Thompson Bros.": "Thompson Brothers",
    "Berry Bros. & Rudd": "Berry Brothers & Rudd",
}


def scraping_backend_in_corso():
    try:
        return time.time() - os.path.getmtime(LOCK) < STALE_HOURS * 3600
    except OSError:
        return False


def main():
    if not os.path.isdir(SRC):
        print("Niente da applicare: la cartella aggiornamenti_backend non c'e'.")
        return
    if scraping_backend_in_corso():
        print(f"{datetime.now():%H:%M} Scraping del backend in corso: aspetto che finisca (controllo ogni minuto)...")
        while scraping_backend_in_corso():
            time.sleep(60)
        print(f"{datetime.now():%H:%M} Scraping terminato.")
        time.sleep(10)

    for root, _dirs, files in os.walk(SRC):
        for name in files:
            src = os.path.join(root, name)
            rel = os.path.relpath(src, SRC)
            shutil.copy2(src, os.path.join(BACKEND, rel))
            print(f"Aggiornato backend\\{rel}")
    shutil.rmtree(SRC, ignore_errors=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB_PATH, f"{DB_PATH}.bak_nomi_bottlers_{stamp}")
    con = sqlite3.connect(DB_PATH, timeout=60)
    with con:
        for vecchio, nuovo in NOMI_ESTESI.items():
            n = con.execute("UPDATE lots SET imbottigliatore = ? WHERE imbottigliatore = ?", (nuovo, vecchio)).rowcount
            print(f"  {vecchio} -> {nuovo}: {n} lotti")
    con.close()
    print(f"Fatto (copia di sicurezza del database: .bak_nomi_bottlers_{stamp}).")


if __name__ == "__main__":
    main()
