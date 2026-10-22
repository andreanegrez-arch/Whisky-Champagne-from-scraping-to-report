r"""
correggi_prezzi.py - corregge prezzi ed esiti gia' salvati nei database (11/10/2026).

Cosa era sbagliato (vedi backend/bidding_api.py per i dettagli):
  1. Lotti chiusi NON venduti: salvato come prezzo finale la STIMA del perito
     (es. Macallan chiuso a 140 EUR di offerta massima, nel database 1000 EUR).
  2. Lotti vecchi reindirizzati da Catawiki al nuovo lotto con cui la bottiglia
     e' stata rimessa all'asta: il lotto vecchio ha preso i dati di quello nuovo.
  3. Lotti rimasti OPEN dopo la chiusura: prezzo = offerta di quando erano stati
     visti l'ultima volta (es. 100 EUR invece dei 140 finali).
  4. Dati vecchi dello scraper pianificato: "1,250" salvato come 1.25.

Come corregge:
  - Per OGNI lotto chiede l'esito ufficiale all'API offerte di Catawiki (per id,
    100 lotti a richiesta, funziona anche per i lotti archiviati) e riscrive
    prezzo_finale, offerta_massima, esito, status e data_chiusura.
  - Se l'API non ha il lotto applica regole prudenti:
      chiuso con 0 offerte registrate -> invenduto, prezzo vuoto (era la stima)
      prezzo con decimali (le offerte Catawiki sono in euro interi) -> x1000
      OPEN con chiusura passata -> "non verificabile"

Sicurezza:
  - copia di backup del database prima di modificarlo (stessa cartella,
    nome .bak_prezzi_DATA)
  - ogni modifica viene registrata nella tabella correzioni_prezzi del database
    e nel file correzioni_prezzi_<progetto>.csv accanto a questo script
  - --prova: fa tutti i controlli e scrive il report, ma NON modifica il database

Uso (dalla cartella Elite-Dashboard, con backend e scheduler FERMI):
    correggi_prezzi.bat            (whisky e champagne)
    correggi_prezzi.bat --prova    (solo report)
"""

import argparse
import csv
import glob
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROGETTI = {
    "whisky": BASE / "whisky-auctions-database" / "backend" / "Whisky SQLite.db",
    "champagne": BASE / "champagne-auctions-database" / "backend" / "Data SQLite Marzo.db",
}

sys.path.insert(0, str(BASE / "whisky-auctions-database" / "backend"))
import bidding_api  # noqa: E402

CAMPI = ["prezzo_finale", "offerta_massima", "esito", "status", "data_chiusura"]


def sessione():
    try:
        from curl_cffi import requests
        s = requests.Session(impersonate="chrome120")
    except Exception:
        import requests  # type: ignore
        s = requests.Session()
    s.headers.update({"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9",
                      "Referer": "https://www.catawiki.com/en/c/437-whisky"})
    return s


def _processo_attivo(pid):
    """True se il processo con questo pid e' ancora in esecuzione."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True  # non si sa: prudenza
    if os.name == "nt":
        import subprocess
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=15).stdout
        except Exception:
            return True
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def scraping_in_corso(db_path):
    """
    File .scraping-*.lock di una sessione davvero in corso. Un lock lasciato da una
    finestra chiusa di colpo (processo non piu' attivo) viene ignorato.
    """
    import json
    progetto = db_path.parent.parent
    for f in glob.glob(str(progetto / ".scraping-*.lock")):
        if time.time() - os.path.getmtime(f) >= 12 * 3600:
            continue
        try:
            pid = json.load(open(f, encoding="utf-8")).get("pid")
        except Exception:
            pid = None
        if pid is not None and not _processo_attivo(pid):
            print(f"  ({Path(f).name}: rimasto da una sessione chiusa, processo {pid} non attivo -> ignorato)")
            continue
        return f
    return None


def decimali(p):
    return p is not None and abs(p - round(p)) > 1e-9


def correggi(nome, db_path, prova, usa_api):
    print(f"\n=== {nome}: {db_path.name}")
    if not db_path.exists():
        print("  database non trovato, salto")
        return
    lock = scraping_in_corso(db_path)
    if lock and not prova:
        print(f"  ATTENZIONE: c'e' una sessione di scraping in corso ({Path(lock).name}).")
        print("  Ferma backend e scheduler e rilancia. Nessuna modifica fatta.")
        return

    if not prova:
        bak = db_path.with_name(db_path.name + ".bak_prezzi_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(db_path, bak)
        print(f"  backup: {bak.name}")

    con = sqlite3.connect(db_path, timeout=30)
    cur = con.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(lots)")}
    if not prova:
        if "esito" not in cols:
            cur.execute("ALTER TABLE lots ADD COLUMN esito VARCHAR")
        if "offerta_massima" not in cols:
            cur.execute("ALTER TABLE lots ADD COLUMN offerta_massima FLOAT")
        cur.execute("""CREATE TABLE IF NOT EXISTS correzioni_prezzi (
            url TEXT, campo TEXT, prima TEXT, dopo TEXT, motivo TEXT, data TEXT)""")
        # lotti chiusi gia' confermati dall'API: alle esecuzioni successive non si richiedono
        cur.execute("""CREATE TABLE IF NOT EXISTS verifiche_api (
            url TEXT PRIMARY KEY, esito TEXT, data TEXT)""")
        cols |= {"esito", "offerta_massima"}

    sel = ["id", "url", "status", "prezzo_finale", "numero_offerte", "data_chiusura"]
    sel += [c for c in ("esito", "offerta_massima") if c in cols]
    righe = [dict(zip(sel, r)) for r in cur.execute(f"SELECT {', '.join(sel)} FROM lots")]
    print(f"  {len(righe)} lotti nel database")

    # --- 1. check del database: cosa va chiesto a Catawiki e cosa no
    try:
        gia_verificati = {u for (u,) in cur.execute(
            "SELECT url FROM verifiche_api WHERE esito IN ('venduto', 'invenduto')")}
    except sqlite3.OperationalError:
        gia_verificati = set()
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    gruppi = {}
    for r in righe:
        if r["url"] in gia_verificati:
            g = "gia' verificati dall'API (chiusi): non si richiedono"
        elif r["status"] == "CLOSED" and (r["numero_offerte"] or 0) == 0:
            g = "chiusi senza offerte registrate (prezzo = stima?)"
        elif r["status"] == "CLOSED":
            g = "chiusi con offerte (controllo reindirizzamenti/virgola)"
        elif (r["data_chiusura"] or "") not in ("", "N/A") and r["data_chiusura"] < ora:
            g = "OPEN con chiusura gia' passata (prezzo non finale)"
        else:
            g = "aste in corso"
        gruppi.setdefault(g, []).append(r)
    print("  check del database:")
    for g, rr in gruppi.items():
        print(f"    {len(rr):6d}  {g}")
    da_chiedere = [r for r in righe if r["url"] not in gia_verificati]
    righe = da_chiedere

    api = {}
    if usa_api and righe:
        ids = [bidding_api.lot_id(r["url"]) for r in righe]
        ids = [i for i in ids if i]
        n_lotti, n_rich = bidding_api.piano(ids)
        print(f"  richieste a Catawiki: {n_lotti} lotti in {n_rich} richieste da {bidding_api.CHUNK} lotti l'una...")
        t0 = time.time()
        api = bidding_api.fetch_sync(sessione(), ids)
        print(f"  risposte API: {len(api)} lotti in {time.time() - t0:.0f} s")
        if len(api) < 0.5 * len(set(ids)):
            print("  ATTENZIONE: l'API ha risposto per meno della meta' dei lotti.")
            print("  Controlla la connessione e rilancia. Nessuna modifica fatta.")
            con.close()
            return

    adesso = datetime.now().isoformat(timespec="seconds")
    modifiche, conteggi = [], {}

    for r in righe:
        info = api.get(bidding_api.lot_id(r["url"]))
        if info:
            d = bidding_api.interpreta(info)
            nuovo = {k: d[k] for k in CAMPI if not (k == "data_chiusura" and not d[k])}
            motivo = "API Catawiki"
        else:
            nuovo, motivo = {}, "regola (lotto non trovato nell'API)"
            p, off = r["prezzo_finale"], r["numero_offerte"] or 0
            if r["status"] == "CLOSED":
                if off == 0:
                    nuovo = {"esito": bidding_api.INVENDUTO, "prezzo_finale": None, "offerta_massima": None}
                    motivo = "stima salvata come prezzo (chiuso senza offerte registrate)"
                else:
                    nuovo = {"esito": bidding_api.VENDUTO}
                    if decimali(p):
                        nuovo["prezzo_finale"] = round(p * 1000)
                        motivo = "virgola delle migliaia (1,250 -> 1.25)"
                    nuovo["offerta_massima"] = nuovo.get("prezzo_finale", p)
            else:
                scaduto = (r["data_chiusura"] or "") not in ("", "N/A") and r["data_chiusura"] < ora
                nuovo = {"esito": bidding_api.NON_VERIFICABILE if scaduto else bidding_api.IN_CORSO}
                motivo = "asta mai ricontrollata dopo la chiusura" if scaduto else motivo
                if decimali(p):
                    nuovo["prezzo_finale"] = round(p * 1000)
                    motivo = "virgola delle migliaia (1,250 -> 1.25)"
                nuovo["offerta_massima"] = nuovo.get("prezzo_finale", p)

        diff = {k: v for k, v in nuovo.items() if r.get(k) != v}
        if not diff:
            continue
        for k, v in diff.items():
            if k in ("esito", "offerta_massima") and r.get(k) is None:
                continue  # primo valore delle colonne nuove: non e' una correzione da registrare
            modifiche.append((r["url"], k, r.get(k), v, motivo, adesso))
            chiave = f"{k} ({motivo})"
            conteggi[chiave] = conteggi.get(chiave, 0) + 1
        if not prova:
            sets = ", ".join(f"{k} = ?" for k in diff)
            cur.execute(f"UPDATE lots SET {sets} WHERE id = ?", list(diff.values()) + [r["id"]])

    if not prova:
        verificati = []
        for r in righe:
            info = api.get(bidding_api.lot_id(r["url"]))
            if info and info.get("closed") is True:
                verificati.append((r["url"], bidding_api.interpreta(info)["esito"], adesso))
        cur.executemany("INSERT OR REPLACE INTO verifiche_api VALUES (?,?,?)", verificati)
        cur.executemany("INSERT INTO correzioni_prezzi VALUES (?,?,?,?,?,?)",
                        [tuple(None if x is None else str(x) for x in m) for m in modifiche])
        con.commit()
    esiti = dict(cur.execute("SELECT esito, COUNT(*) FROM lots GROUP BY esito").fetchall()) if not prova else {}
    con.close()

    report = BASE / f"correzioni_prezzi_{nome}.csv"
    with open(report, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "campo", "prima", "dopo", "motivo", "data"])
        w.writerows(modifiche)
    print(f"  modifiche{' (PROVA, database non toccato)' if prova else ''}:")
    for k, v in sorted(conteggi.items()):
        print(f"    {v:6d}  {k}")
    if esiti:
        print("  esito dei lotti adesso: " + ", ".join(f"{k}: {v}" for k, v in esiti.items()))
    print(f"  report: {report.name}")


def main():
    p = argparse.ArgumentParser(description="Corregge prezzi ed esiti dei lotti nei database")
    p.add_argument("--prova", action="store_true", help="non modifica i database, scrive solo il report")
    p.add_argument("--senza-api", action="store_true", help="solo regole offline, senza chiedere a Catawiki")
    p.add_argument("--solo", choices=list(PROGETTI))
    a = p.parse_args()
    for nome, db in PROGETTI.items():
        if a.solo and nome != a.solo:
            continue
        correggi(nome, db, a.prova, not a.senza_api)
    print("\nFatto. Ora riavvia backend/scheduler e rilancia export_powerbi\\esporta_powerbi.bat")


if __name__ == "__main__":
    main()
