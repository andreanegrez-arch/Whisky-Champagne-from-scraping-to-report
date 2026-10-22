"""
lotti_ritirati.py - lotti che Catawiki ha tolto dal sito (pagina 404).

Regola di conferma (doppio controllo)
-------------------------------------
1. Il primo 404 su un lotto lo SEGNA soltanto (tabella lotti_404_segnalati).
   Il lotto resta nel database e viene ricontrollato alla sessione successiva.
2. Il lotto viene considerato ritirato solo se risponde di nuovo 404:
   - allo STESSO identico URL (confronto esatto della stringa, e anche l'ID
     numerico del lotto deve coincidere: nessun mismatch ammesso);
   - in una sessione di scraping DIVERSA da quella del primo 404.
   Solo allora il lotto viene spostato nella tabella lotti_ritirati (con tutti
   i suoi dati) e tolto da `lots`, cosi' non viene piu' richiesto.
3. Se nel frattempo la pagina torna a rispondere (200), il segnale viene tolto.

Il report Excel "Lotti 404_Ritirati_Da_Catawiki.xlsx" (cartella data del
progetto) viene rigenerato dopo ogni sessione. Contiene il riepilogo mensile
(lotti presentati, ritirati, % sul totale), il dettaglio dei lotti ritirati e
le categorie (per maison/distilleria, tipologia/stile, formato).
"""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(HERE)
EXCEL_NAME = "Lotti 404_Ritirati_Da_Catawiki.xlsx"
EXCEL_PATH = os.path.join(PROJECT_DIR, "data", EXCEL_NAME)

SEGNATO = "segnato"          # primo 404: solo segnalato
GIA_SEGNATO = "gia_segnato"  # 404 ripetuto nella STESSA sessione: nessuna conferma
RITIRATO = "ritirato"        # secondo 404 in una sessione diversa: archiviato

_LOT_ID = re.compile(r"/l/(\d+)")


def _db_path():
    from database import DB_PATH  # import locale: evita dipendenze circolari
    return DB_PATH


def lot_id_from_url(url):
    m = _LOT_ID.search(url or "")
    return m.group(1) if m else None


def _fields(con):
    """Nomi delle colonne del progetto: champagne (maison...) o whisky (distilleria...)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(lots)")}
    if "maison" in cols:
        return {"gruppo": ("maison", "Maison"), "tipo": ("tipologia", "Tipologia"), "annata": ("vintage", "Vintage")}
    return {"gruppo": ("distilleria", "Distilleria"), "tipo": ("stile", "Stile"), "annata": ("eta", "Età")}


def connect(db_path=None):
    con = sqlite3.connect(db_path or _db_path(), timeout=60)
    con.execute(
        """CREATE TABLE IF NOT EXISTS lotti_404_segnalati (
               url TEXT PRIMARY KEY,
               lot_id TEXT,
               primo_404 TEXT,
               sessione TEXT,
               fonte TEXT
           )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS lotti_ritirati (
               url TEXT PRIMARY KEY,
               lot_id TEXT,
               primo_404 TEXT,
               confermato_404 TEXT,
               fonte TEXT,
               title TEXT,
               gruppo TEXT,
               tipo TEXT,
               annata TEXT,
               formato TEXT,
               numero_bottiglie INTEGER,
               is_mixed INTEGER,
               has_box INTEGER,
               ultima_offerta REAL,
               currency TEXT,
               numero_offerte INTEGER,
               data_chiusura TEXT,
               stato_ultimo TEXT,
               ultima_rilevazione TEXT,
               dati_completi TEXT
           )"""
    )
    con.commit()
    return con


def register_404(url, session_id, fonte, lot_info=None, db_path=None):
    """
    Registra una risposta 404 per `url`. Restituisce SEGNATO, GIA_SEGNATO o RITIRATO.

    lot_info: dati del lotto (usati se il lotto non e' nella tabella `lots`,
              ad es. quando la fonte e' l'Excel dello scheduler). Chiavi:
              title, gruppo, tipo, annata, formato, numero_bottiglie, is_mixed,
              has_box, prezzo, currency, numero_offerte, data_chiusura, status, timestamp
    """
    now = datetime.now().isoformat(timespec="seconds")
    lot_id = lot_id_from_url(url)
    con = connect(db_path)
    try:
        mark = con.execute(
            "SELECT url, lot_id, primo_404, sessione FROM lotti_404_segnalati WHERE url = ?", (url,)
        ).fetchone()
        # Controllo di identita': stesso URL (esatto, garantito dalla chiave) e stesso ID lotto
        if mark is None or mark[0] != url or mark[1] != lot_id:
            con.execute(
                "INSERT OR REPLACE INTO lotti_404_segnalati VALUES (?, ?, ?, ?, ?)",
                (url, lot_id, now, session_id, fonte),
            )
            con.commit()
            logger.info(f"404 (primo, segnato): {url}")
            return SEGNATO
        if mark[3] == session_id:
            return GIA_SEGNATO

        # Secondo 404, sessione diversa, stesso identico lotto: archiviazione
        f = _fields(con)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM lots WHERE url = ?", (url,)).fetchone()
        con.row_factory = None
        if row is not None:
            d = dict(row)
            info = {
                "title": d.get("title"), "gruppo": d.get(f["gruppo"][0]), "tipo": d.get(f["tipo"][0]),
                "annata": d.get(f["annata"][0]), "formato": d.get("formato"),
                "numero_bottiglie": d.get("numero_bottiglie"), "is_mixed": d.get("is_mixed"),
                "has_box": d.get("has_box"), "prezzo": d.get("prezzo_finale"), "currency": d.get("currency"),
                "numero_offerte": d.get("numero_offerte"), "data_chiusura": d.get("data_chiusura"),
                "status": d.get("status"), "timestamp": str(d.get("timestamp") or ""),
            }
            full = d
        else:
            info = dict(lot_info or {})
            full = info
        con.execute(
            """INSERT OR REPLACE INTO lotti_ritirati VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                url, lot_id, mark[2], now, fonte,
                info.get("title"), info.get("gruppo"), info.get("tipo"), info.get("annata"),
                info.get("formato"), _int(info.get("numero_bottiglie")), _int(info.get("is_mixed")),
                _int(info.get("has_box")), _float(info.get("prezzo")), info.get("currency"),
                _int(info.get("numero_offerte")), info.get("data_chiusura"), info.get("status"),
                info.get("timestamp"), json.dumps(full, default=str, ensure_ascii=False),
            ),
        )
        con.execute("DELETE FROM lots WHERE url = ?", (url,))
        con.execute("DELETE FROM lotti_404_segnalati WHERE url = ?", (url,))
        con.commit()
        logger.info(f"404 confermato: lotto ritirato da Catawiki, archiviato: {url}")
        return RITIRATO
    finally:
        con.close()


def clear_404(url, db_path=None):
    """La pagina risponde di nuovo: il segnale di 404 viene tolto."""
    con = connect(db_path)
    try:
        cur = con.execute("DELETE FROM lotti_404_segnalati WHERE url = ?", (url,))
        con.commit()
        if cur.rowcount:
            logger.info(f"404 rientrato (la pagina risponde di nuovo): {url}")
    finally:
        con.close()


def marked_urls(db_path=None):
    """URL con un primo 404 in attesa di conferma."""
    con = connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT url FROM lotti_404_segnalati")}
    finally:
        con.close()


def lot_info_from_excel(df, url):
    """Dati del lotto dall'ultima riga dello storico Excel dello scheduler."""
    if df is None or df.empty or "url" not in df.columns:
        return {}
    rows = df[df["url"] == url]
    if rows.empty:
        return {}
    r = rows.iloc[-1].to_dict()
    pick = lambda *names: next((r.get(n) for n in names if n in r and str(r.get(n)) != "nan"), None)
    return {
        "title": pick("title"), "gruppo": pick("Maison", "Distilleria"), "tipo": pick("Tipologia", "Stile"),
        "annata": pick("Vintage", "Eta"), "formato": pick("Formato"), "numero_bottiglie": pick("Numero Bottiglie"),
        "prezzo": pick("Prezzo Finale"), "currency": pick("currency"), "numero_offerte": pick("Numero Offerte"),
        "data_chiusura": pick("Data Chiusura"), "status": pick("status"), "timestamp": str(pick("timestamp") or ""),
    }


def archived_urls(db_path=None):
    con = connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT url FROM lotti_ritirati")}
    finally:
        con.close()


def export_excel(path=EXCEL_PATH, db_path=None):
    """Rigenera il report Excel. Restituisce il numero di lotti ritirati."""
    import pandas as pd

    con = connect(db_path)
    try:
        f = _fields(con)
        G, T, A = f["gruppo"][1], f["tipo"][1], f["annata"][1]
        rit = pd.read_sql("SELECT * FROM lotti_ritirati", con)
        pres = pd.read_sql(
            "SELECT substr(data_chiusura, 1, 7) AS mese, COUNT(*) AS n FROM lots "
            "WHERE data_chiusura LIKE '____-__%' GROUP BY 1", con
        )
    finally:
        con.close()

    rit["Mese"] = rit["data_chiusura"].fillna("").str[:7].where(lambda s: s.str.match(r"^\d{4}-\d{2}$"), "Senza data")

    # Riepilogo mensile: i ritirati sono stati tolti da `lots`, quindi i lotti
    # presentati nel mese = lotti in archivio + lotti ritirati.
    by_month = rit.groupby("Mese").size().rename("Ritirati (404)")
    summary = pres.set_index("mese")["n"].rename("Lotti in archivio").to_frame().join(by_month, how="outer").fillna(0)
    summary["Lotti presentati"] = summary["Lotti in archivio"] + summary["Ritirati (404)"]
    summary["% ritirati"] = (summary["Ritirati (404)"] / summary["Lotti presentati"].where(summary["Lotti presentati"] > 0)).fillna(0)
    summary = summary.reset_index().rename(columns={"index": "Mese", "mese": "Mese"}).sort_values("Mese", ascending=False)
    summary = summary[["Mese", "Lotti presentati", "Ritirati (404)", "% ritirati", "Lotti in archivio"]]
    for c in ["Lotti presentati", "Ritirati (404)", "Lotti in archivio"]:
        summary[c] = summary[c].astype(int)

    detail = pd.DataFrame({
        "Mese": rit["Mese"],
        "Data chiusura (UTC)": rit["data_chiusura"],
        G: rit["gruppo"], T: rit["tipo"], A: rit["annata"],
        "Formato": rit["formato"], "Bottiglie": rit["numero_bottiglie"],
        "Lotto misto": rit["is_mixed"].map({1: "Sì", 0: "No"}),
        "Con box": rit["has_box"].map({1: "Sì", 0: "No"}),
        "Ultima offerta rilevata": rit["ultima_offerta"], "Valuta": rit["currency"],
        "Offerte": rit["numero_offerte"], "Stato all'ultima rilevazione": rit["stato_ultimo"],
        "Titolo del lotto": rit["title"], "URL": rit["url"], "ID lotto": rit["lot_id"],
        "Primo 404": rit["primo_404"], "404 confermato": rit["confermato_404"], "Rilevato da": rit["fonte"],
    }).sort_values(["Mese", "Data chiusura (UTC)"], ascending=False)

    def cat(col, label):
        if rit.empty:
            return pd.DataFrame(columns=[label, "Lotti ritirati", "Valore ultime offerte"])
        g = rit.assign(k=rit[col].fillna("N/D")).groupby("k").agg(
            n=("url", "size"), v=("ultima_offerta", "sum")).reset_index()
        g.columns = [label, "Lotti ritirati", "Valore ultime offerte"]
        return g.sort_values("Lotti ritirati", ascending=False)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with pd.ExcelWriter(path, engine="xlsxwriter",
                            engine_kwargs={"options": {"nan_inf_to_errors": True}}) as w:
            wb = w.book
            pct = wb.add_format({"num_format": "0.0%"})
            eur = wb.add_format({"num_format": "#,##0.00"})

            summary.to_excel(w, sheet_name="Riepilogo mensile", index=False, startrow=2)
            ws = w.sheets["Riepilogo mensile"]
            ws.write(0, 0, "Su tutti i lotti presentati nel mese, quanti sono stati ritirati da Catawiki (pagina 404 confermata due volte)")
            ws.set_column(0, 0, 12)
            ws.set_column(1, 2, 18)
            ws.set_column(3, 3, 12, pct)
            ws.set_column(4, 4, 18)

            detail.to_excel(w, sheet_name="Lotti ritirati", index=False)
            wd = w.sheets["Lotti ritirati"]
            wd.autofilter(0, 0, max(len(detail), 1), len(detail.columns) - 1)
            wd.freeze_panes(1, 0)
            wd.set_column(0, 1, 16)
            wd.set_column(2, 9, 14)
            wd.set_column(9, 9, 16, eur)
            wd.set_column(13, 13, 60)
            wd.set_column(14, 14, 40)

            row = 0
            wc = wb.add_worksheet("Per categoria")
            w.sheets["Per categoria"] = wc
            for col, label in [("gruppo", G), ("tipo", T), ("formato", "Formato"), ("annata", A)]:
                t = cat(col, label)
                wc.write(row, 0, f"Ritirati per {label.lower()}")
                t.to_excel(w, sheet_name="Per categoria", index=False, startrow=row + 1)
                row += len(t) + 4
            wc.set_column(0, 0, 28)
            wc.set_column(1, 1, 16)
            wc.set_column(2, 2, 22, eur)
    except PermissionError:
        logger.warning(f"Impossibile aggiornare '{EXCEL_NAME}': il file e' aperto in Excel? Riprovo alla prossima sessione.")
    return len(rit)


def _int(v):
    try:
        return None if v is None or v == "" else int(float(v))
    except (TypeError, ValueError):
        return 1 if str(v).lower() in ("true", "sì", "si", "yes") else 0 if str(v).lower() in ("false", "no") else None


def _float(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None
