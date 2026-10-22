"""
fix_distillerie_unknown.py - ricalcola la distilleria dei lotti whisky rimasti "Unknown".

Il parser precedente riconosceva solo ~80 distillerie scritte a mano: 4.980 lotti
su 21.661 (al 30/09/2026) erano finiti in "Unknown". Questo script li
ricalcola dal titolo con il parser nuovo (parsers.py + distillerie_vocabolario.json).

Tocca SOLO le righe con distilleria "Unknown" / vuota: le etichette gia'
assegnate (anche quelle corrette a mano) non vengono modificate.
Per i lotti riconosciuti come "Mixed Lot" imposta anche is_mixed = 1.

Uso (dalla cartella whisky-auctions-database):
    backend\\venv\\Scripts\\python backend\\fix_distillerie_unknown.py            # anteprima, non scrive
    backend\\venv\\Scripts\\python backend\\fix_distillerie_unknown.py --applica  # applica

Con --applica: prima copia il database in "<nome>.bak_distillerie_<data>",
poi aggiorna e salva l'elenco delle modifiche in logs/fix_distillerie_<data>.csv.
"""

import argparse
import collections
import csv
import os
import shutil
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from parsers import detect_distilleria  # noqa: E402

DB_PATH = os.path.join(HERE, "Whisky SQLite.db")
UNKNOWN = ("Unknown", "", "Sconosciuto", "NV")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--applica", action="store_true", help="scrive nel database (altrimenti solo anteprima)")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH, timeout=60)
    rows = con.execute(
        "SELECT id, title, distilleria FROM lots WHERE distilleria IS NULL OR distilleria IN (?, ?, ?, ?)",
        UNKNOWN,
    ).fetchall()
    changes = []
    for lot_id, title, prima in rows:
        dopo = detect_distilleria(title or "")
        if dopo and dopo != "Unknown":
            changes.append((lot_id, title, prima, dopo))

    print(f"Database: {DB_PATH}")
    print(f"Lotti con distilleria sconosciuta: {len(rows)}")
    print(f"Riconosciuti dal parser nuovo:     {len(changes)}  (restano sconosciuti: {len(rows) - len(changes)})")
    top = collections.Counter(c[3] for c in changes).most_common(25)
    print("\nDistillerie piu' frequenti tra i lotti recuperati:")
    for name, n in top:
        print(f"  {n:5d}  {name}")
    print("\nEsempi:")
    for c in changes[:15]:
        print(f"  {c[3]:30s} <- {c[1][:80]}")

    if not args.applica:
        print("\nAnteprima: nessuna modifica. Per applicare: aggiungere --applica")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{DB_PATH}.bak_distillerie_{stamp}"
    con.close()
    shutil.copy2(DB_PATH, backup)
    print(f"\nCopia di sicurezza: {backup}")

    con = sqlite3.connect(DB_PATH, timeout=60)
    with con:
        for lot_id, _title, _prima, dopo in changes:
            if dopo == "Mixed Lot":
                con.execute("UPDATE lots SET distilleria = ?, is_mixed = 1 WHERE id = ?", (dopo, lot_id))
            else:
                con.execute("UPDATE lots SET distilleria = ? WHERE id = ?", (dopo, lot_id))
    con.close()

    log_dir = os.path.join(os.path.dirname(HERE), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"fix_distillerie_{stamp}.csv")
    with open(log_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "titolo", "distilleria_prima", "distilleria_dopo"])
        w.writerows(changes)
    print(f"Aggiornati {len(changes)} lotti. Elenco modifiche: {log_path}")


if __name__ == "__main__":
    main()
