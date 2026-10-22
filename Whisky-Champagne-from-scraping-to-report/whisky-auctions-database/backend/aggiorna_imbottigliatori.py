"""
aggiorna_imbottigliatori.py - calcola l'imbottigliatore per TUTTI i lotti whisky.

Aggiunge (se manca) la colonna `imbottigliatore` alla tabella lots e la compila
per ogni lotto con parsers.detect_bottler: imbottigliatore indipendente
riconosciuto (Signatory Vintage, Gordon & MacPhail, Dun Eideann...) oppure
"Original bottling". Non modifica nessun altro campo.

Uso (dalla cartella whisky-auctions-database):
    backend\\venv\\Scripts\\python backend\\aggiorna_imbottigliatori.py            # anteprima
    backend\\venv\\Scripts\\python backend\\aggiorna_imbottigliatori.py --applica  # applica

Con --applica fa prima una copia di sicurezza del database.
"""

import argparse
import collections
import os
import shutil
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from parsers import detect_bottler, ORIGINAL_BOTTLING  # noqa: E402

DB_PATH = os.path.join(HERE, "Whisky SQLite.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--applica", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB_PATH, timeout=60)
    cols = {r[1] for r in con.execute("PRAGMA table_info(lots)")}
    ha_colonna = "imbottigliatore" in cols
    sel = "SELECT id, title, distilleria" + (", imbottigliatore" if ha_colonna else ", NULL") + " FROM lots"
    rows = con.execute(sel).fetchall()
    nuovi = [(lot_id, detect_bottler(title or "", None, dist), prima) for lot_id, title, dist, prima in rows]
    cambi = [(i, b) for i, b, prima in nuovi if b != prima]

    cnt = collections.Counter(b for _, b, _ in nuovi)
    indip = sum(n for b, n in cnt.items() if b != ORIGINAL_BOTTLING)
    print(f"Database: {DB_PATH}")
    print(f"Lotti: {len(rows)}  -  indipendenti: {indip}  -  original bottling: {cnt[ORIGINAL_BOTTLING]}")
    print(f"Lotti da aggiornare: {len(cambi)}")
    print("\nImbottigliatori indipendenti piu' frequenti:")
    for b, n in cnt.most_common(30):
        if b != ORIGINAL_BOTTLING:
            print(f"  {n:5d}  {b}")

    if not a.applica:
        print("\nAnteprima: nessuna modifica. Per applicare: aggiungere --applica")
        return

    con.close()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB_PATH, f"{DB_PATH}.bak_imbottigliatori_{stamp}")
    con = sqlite3.connect(DB_PATH, timeout=60)
    with con:
        if not ha_colonna:
            con.execute("ALTER TABLE lots ADD COLUMN imbottigliatore VARCHAR")
        con.executemany("UPDATE lots SET imbottigliatore = ? WHERE id = ?", [(b, i) for i, b in cambi])
    con.close()
    print(f"\nAggiornati {len(cambi)} lotti (copia di sicurezza: .bak_imbottigliatori_{stamp}).")


if __name__ == "__main__":
    main()
