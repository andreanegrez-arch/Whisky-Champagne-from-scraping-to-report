"""
fix_prezzi_virgola_migliaia.py
--------------------------------
Recupera i prezzi rovinati dal bug della virgola delle migliaia (vedi
scraper_service.py corretto in parallelo). Quando Catawiki mostra un
prezzo tipo "€1,025", il vecchio codice scambiava la virgola per un
separatore decimale e salvava 1.025 invece di 1025 -- una divisione per
mille, che colpiva sempre le bottiglie piu' rare e costose.

Come si riconosce con certezza: un prezzo genuino non ha mai piu' di 2
cifre decimali (i centesimi di euro). Se un valore ha ESATTAMENTE 3 cifre
decimali per tornare esatto (es. 1.025, 2.621), non puo' essere un prezzo
vero -- e' la firma inequivocabile del bug. In quel caso il prezzo vero
si ottiene moltiplicando per 1000 e arrotondando all'euro.

Questo script corregge SOLO questi casi inequivocabili. Ci sono
probabilmente altri prezzi colpiti dallo stesso bug ma "nascosti" (es. un
prezzo originale come "€1,250" diventa 1.25, indistinguibile da un
genuino "€1,25" con solo 2 decimali) -- questi non vengono toccati perche'
non c'e' modo sicuro di distinguerli dal dato reale senza rischiare di
correggere un prezzo che invece era gia' giusto.

USO: identico agli script precedenti (funziona sia sul db champagne che
whisky, basta passare il percorso giusto). Ferma backend/scheduler prima
di lanciarlo, backup automatico.
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime

DEFAULT_DB = "Data SQLite Marzo.db"


def decimals_needed(p, max_d=4):
    for d in range(0, max_d):
        if abs(round(p, d) - p) < 1e-9:
            return d
    return max_d


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not os.path.exists(db_path):
        print(f"ERRORE: non trovo il file '{db_path}'.")
        return

    backup_path = f"{db_path}.bak_prezzi_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup creato: {backup_path}")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    before_total = cur.execute("SELECT COUNT(*) FROM lots").fetchone()[0]

    rows = cur.execute("SELECT id, prezzo_finale FROM lots WHERE prezzo_finale IS NOT NULL").fetchall()
    affected = [(i, p) for i, p in rows if decimals_needed(p) == 3]

    print(f"Righe con la firma del bug (esattamente 3 decimali): {len(affected)}")

    for lot_id, old_price in affected:
        new_price = round(old_price * 1000)
        cur.execute("UPDATE lots SET prezzo_finale = ? WHERE id = ?", (float(new_price), lot_id))
        print(f"  id {lot_id}: {old_price} -> {new_price}")

    con.commit()
    after_total = cur.execute("SELECT COUNT(*) FROM lots").fetchone()[0]

    print(f"\nRighe corrette: {len(affected)}")
    print(f"Righe totali: {before_total} -> {after_total} (deve essere invariato)")

    if before_total != after_total:
        print("\n!!! ATTENZIONE: il numero di righe e' cambiato, ripristina il backup e segnalalo.")
    else:
        print("\nFatto.")

    con.close()


if __name__ == "__main__":
    main()
