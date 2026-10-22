"""
fix_whisky_duplicati_formato.py
---------------------------------
Seconda passata di pulizia sul database whisky, dopo il fix della
distilleria SexyWhisky. Sistema due cose distinte, trovate durante il
check richiesto da Andrea:

1. DUPLICATI DI GRAFIA sul campo `distilleria` (9 gruppi, 1.644 righe):
   - Apostrofo + maiuscola sbagliata: "Jack Daniel'S" -> "Jack Daniel's",
     stesso schema per Blanton's, Ichiro's Malt, Maker's Mark.
   - CamelCase vs minuscolo: qui la forma CORRETTA (il marchio ufficiale)
     e' quella con la maiuscola in mezzo, quindi si unisce nella direzione
     opposta al punto precedente -> "BenRiach", "GlenAllachie".
   - "Various Scotch whisky" -> "Various Scotch Whisky" (maiuscola).
   - Due righe con lo stesso problema di SexyWhisky (nome del prodotto al
     posto del vero produttore): "Big Peat ... Gold Edition/edition" (id
     481, 592) -> il vero imbottigliatore e' "Douglas Laing"; "Dimple 12
     years old & De Luxe / De Luxe" (id 5760, 5594) -> il vero produttore
     e' "John Haig & Co.".

2. FORMATO scritto in due modi per la stessa cosa: "70cl"/"0.70",
   "75cl"/"0.75", "1.5L"/"Magnum 1.5 L". Si unifica sulla forma gia' usata
   dal parser per i nuovi lotti (0.70 / 0.75 / Magnum 1.5 L).

USO: identico agli script precedenti. Ferma backend e scheduler whisky
prima di lanciarlo, backup automatico.
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime

DEFAULT_DB = "Whisky SQLite.db"

DISTILLERIA_MAPPING = {
    "Jack Daniel'S": "Jack Daniel's",
    "Blanton'S": "Blanton's",
    "Benriach": "BenRiach",
    "Glenallachie": "GlenAllachie",
    "Ichiro'S Malt": "Ichiro's Malt",
    "Various Scotch whisky": "Various Scotch Whisky",
    "Maker'S Mark": "Maker's Mark",
}

# Casi puntuali: nome prodotto finito nel campo distilleria invece del vero
# produttore (stesso pattern gia' visto per SexyWhisky), identificati per id
# per essere sicuri di correggere solo queste righe specifiche.
ID_FIXES = [
    (481, "Big Peat 1992 25 years old The Gold Edition", "Douglas Laing"),
    (592, "Big Peat 1992 25 years old The Gold edition", "Douglas Laing"),
    (5760, "Dimple 12 years old & De Luxe", "John Haig & Co."),
    (5594, "Dimple 12 years old De Luxe", "John Haig & Co."),
]

FORMATO_MAPPING = {
    "70cl": "0.70",
    "75cl": "0.75",
    "1.5L": "Magnum 1.5 L",
}


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    if not os.path.exists(db_path):
        print(f"ERRORE: non trovo il file '{db_path}'.")
        return

    backup_path = f"{db_path}.bak_dup_formato_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup creato: {backup_path}")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    before_total = cur.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
    before_distinct = cur.execute("SELECT COUNT(DISTINCT distilleria) FROM lots").fetchone()[0]

    print("\n--- Duplicati di grafia (distilleria) ---")
    total_dup = 0
    for old, new in DISTILLERIA_MAPPING.items():
        cur.execute("UPDATE lots SET distilleria = ? WHERE distilleria = ?", (new, old))
        print(f"  '{old}' -> '{new}'  ({cur.rowcount} righe)")
        total_dup += cur.rowcount

    print("\n--- Casi puntuali (nome prodotto al posto del produttore) ---")
    for lot_id, old, new in ID_FIXES:
        cur.execute("UPDATE lots SET distilleria = ? WHERE id = ? AND distilleria = ?", (new, lot_id, old))
        print(f"  id {lot_id}: '{old}' -> '{new}'  ({cur.rowcount} righe)")
        total_dup += cur.rowcount

    print("\n--- Formato ---")
    total_formato = 0
    for old, new in FORMATO_MAPPING.items():
        cur.execute("UPDATE lots SET formato = ? WHERE formato = ?", (new, old))
        print(f"  '{old}' -> '{new}'  ({cur.rowcount} righe)")
        total_formato += cur.rowcount

    con.commit()
    after_total = cur.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
    after_distinct = cur.execute("SELECT COUNT(DISTINCT distilleria) FROM lots").fetchone()[0]

    print(f"\nRighe distilleria corrette: {total_dup}")
    print(f"Righe formato corrette: {total_formato}")
    print(f"Distilleria distinte: {before_distinct} -> {after_distinct}")
    print(f"Righe totali: {before_total} -> {after_total} (deve essere invariato)")

    if before_total != after_total:
        print("\n!!! ATTENZIONE: il numero di righe e' cambiato, ripristina il backup e segnalalo.")
    else:
        print("\nFatto.")

    con.close()


if __name__ == "__main__":
    main()
