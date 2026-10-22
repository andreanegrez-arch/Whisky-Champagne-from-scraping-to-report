r"""
Esporta i due database SQLite di Elite-Dashboard (champagne e whisky) in CSV
gia' puliti e tipizzati, pronti per il report Power BI (BaseReport).

Come si usa (Prompt dei comandi, dalla cartella Elite-Dashboard):
    python export_powerbi\export_powerbi.py
oppure doppio clic su export_powerbi\esporta_powerbi.bat

Solo libreria standard, database aperti in SOLA LETTURA (si puo' lanciare anche
col backend acceso). I CSV vengono scritti nella cartella dello script e
sovrascritti a ogni esecuzione (prima su un .tmp, poi sostituiti in un colpo).

File prodotti (uno per ogni tabella del modello Power BI)
----------------------------------------------------------
    lotti_champagne.csv           -> tabella lotti_champagne
    lotti_whisky.csv              -> tabella lotti_whisky
    DimCountry.csv                -> tabella DimCountry (prima era una query Power Query)
    Calendario.csv                -> tabella Calendario (stesse colonne della tabella DAX)
    lotti_ritirati_champagne.csv  -> lotti ritirati da Catawiki (404 confermato)
    lotti_ritirati_whisky.csv

Formati garantiti in TUTTI i CSV (controllati alla fine da verifica_csv)
------------------------------------------------------------------------
    date           AAAA-MM-GG               (data_chiusura, Data, *_chiusura)
    date con ora   AAAA-MM-GG HH:MM:SS      (timestamp, data_ora_chiusura, ...)
                   niente microsecondi, niente "T"
    interi         solo cifre               (id, numero_bottiglie, has_box, ...)
    decimali       punto decimale, senza ".0" inutili (75 e non 75.0; 0.7; 1.5)
    testo          spazi doppi e spazi ai bordi tolti
    vuoto          cella vuota (mai "nan", "None", "N/A") -> null in Power BI
Codifica UTF-8 con BOM, separatore ",". Con --formato-italiano: ";" e virgola
decimale (le date restano AAAA-MM-GG, che Power BI legge in qualsiasi lingua).

Colonne dei lotti
-----------------
Stesse colonne e stesso ordine di prima (le query esistenti continuano a
funzionare), piu' UNA colonna in fondo:
    data_ora_chiusura   data e ora di fine asta. `data_chiusura` ora e' SOLO la
                        data, cosi' la relazione con Calendario[Data] funziona
                        sempre, anche se in Power Query la colonna e' "Data/ora".
`formato` (litri): se il titolo del lotto indica un formato unico diverso da
quello nel database, vince il titolo. Lo scraper whisky metteva 0.70 di default:
"Macallan Select Oak - 1 Litre" risultava 0.70, ora 1. Se il titolo ha piu'
formati (lotti misti) resta il valore del database.

Nazionalita' del vincitore (dal 30/09/2026)
-------------------------------------------
La colonna grezza `nazionalita` non viene esportata. Al suo posto:
    nazionalita_stato   verificata | da verificare | non venduto | asta aperta
    nazionalita_codice  codice ISO a 2 lettere (es. IT), SOLO se verificata
    nazionalita_nome    nome del paese in italiano, SOLO se verificata
    winner_username / winner_id   solo per le righe verificate

Esito d'asta (dall'11/10/2026, vedi correggi_prezzi.py), in fondo al CSV:
    esito            venduto | invenduto | in corso | non verificabile
    offerta_massima  offerta piu' alta ricevuta, anche se il lotto non e' venduto

Pulizia distilleria (whisky): vedi pulizia_distilleria.py e mappa_distillerie.csv.
Pulizia maison (champagne, dal 15/10/2026): vedi pulizia_maison.py.
    mappa_maison.csv           correzioni gia' decise (originale -> maison, tipologia)
    maison_da_verificare.csv   casi dubbi: scrivi il nome giusto in `maison_corretta`
                               e rilancia l'export; finche' e' vuota il nome resta com'e'
I lotti misti (piu' produttori nello stesso lotto) e gli champagne commerciali senza
produttore ("(elimina)") NON vengono scritti nel CSV. Gli accessori (bicchieri,
vassoi, libri) escono con maison "Accessori/Non-bottiglia" e tipologia "Items".

Opzioni:
    --formato-italiano           separatore ';' e virgola decimale
    --tieni-colonne-vuote        non scarta costi_spedizione e currency
    --base PERCORSO              cartella Elite-Dashboard (default: sopra lo script)
    --out PERCORSO               cartella di destinazione (default: quella dello script)
    --solo whisky|champagne      riscrive solo i CSV dei lotti di quel progetto
                                 (DimCountry e Calendario usano sempre entrambi)
    --senza-pulizia-distilleria  `distilleria` cosi' com'e' nel database
    --senza-pulizia-maison       `maison` cosi' com'e' nel database
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pulizia_distilleria import Pulitore  # noqa: E402
from pulizia_maison import PulitoreMaison  # noqa: E402

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# (progetto, nome CSV, percorso del DB relativo alla cartella Elite-Dashboard)
SORGENTI = [
    ("champagne", "lotti_champagne.csv", Path("champagne-auctions-database") / "backend" / "Data SQLite Marzo.db"),
    ("whisky", "lotti_whisky.csv", Path("whisky-auctions-database") / "backend" / "Whisky SQLite.db"),
]

# Colonne senza dati utili (costi_spedizione: "N/A" o testo della pagina; currency: vuota)
COLONNE_DA_ESCLUDERE = {"costi_spedizione", "currency"}
# Colonne grezze sostituite dalle colonne pulite della nazionalita'
COLONNE_SOSTITUITE = {"nazionalita", "winner_username", "winner_id"}
COLONNE_ESITO = ["esito", "offerta_massima"]
COLONNE_NAZIONALITA = ["nazionalita_stato", "nazionalita_codice", "nazionalita_nome",
                       "winner_username", "winner_id"]
COLONNE_AGGIUNTE = ["data_ora_chiusura"]

# Tipo di ogni colonna nei CSV. Tutto quello che non e' qui e' testo.
TIPI = {
    # solo data
    "data_chiusura": "data", "Data": "data",
    "whisky_prima_chiusura": "data", "whisky_ultima_chiusura": "data",
    "champagne_prima_chiusura": "data", "champagne_ultima_chiusura": "data",
    # data e ora
    "timestamp": "dataora", "data_ora_chiusura": "dataora", "primo_404": "dataora",
    "confermato_404": "dataora", "ultima_rilevazione": "dataora",
    "whisky_ultima_rilevazione": "dataora", "champagne_ultima_rilevazione": "dataora",
    # decimali
    "formato": "decimale", "prezzo_finale": "decimale", "offerta_massima": "decimale",
    "ultima_offerta": "decimale",
    # interi
    "id": "intero", "lot_id": "intero", "numero_bottiglie": "intero", "numero_offerte": "intero",
    "has_box": "intero", "is_mixed": "intero",
    "whisky_lotti_vinti": "intero", "champagne_lotti_vinti": "intero",
    "Mese Numero": "intero", "Anno": "intero", "Mese Numero Fiscale": "intero", "Anno Fiscale": "intero",
}

TOKEN_RE = re.compile(r"^[0-9a-f]{40}$")  # winner_id della logica nuova
SCONOSCIUTI = {"", "unknown", "sconosciuto", "nv", "nan", "none", "n/a"}
TESTI_VUOTI = {"nan", "none", "n/a", "na", "null"}

PAESI = {
    "AD": "Andorra", "AE": "Emirati Arabi Uniti", "AL": "Albania", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "BA": "Bosnia ed Erzegovina", "BE": "Belgio", "BG": "Bulgaria", "BR": "Brasile",
    "CA": "Canada", "CH": "Svizzera", "CL": "Cile", "CN": "Cina", "CY": "Cipro", "CZ": "Repubblica Ceca",
    "DE": "Germania", "DK": "Danimarca", "EE": "Estonia", "ES": "Spagna", "FI": "Finlandia",
    "FR": "Francia", "GB": "Regno Unito", "GR": "Grecia", "HK": "Hong Kong", "HR": "Croazia",
    "HU": "Ungheria", "IE": "Irlanda", "IL": "Israele", "IN": "India", "IS": "Islanda", "IT": "Italia",
    "JP": "Giappone", "KR": "Corea del Sud", "LI": "Liechtenstein", "LT": "Lituania", "LU": "Lussemburgo",
    "LV": "Lettonia", "MC": "Monaco", "ME": "Montenegro", "MK": "Macedonia del Nord", "MT": "Malta",
    "MX": "Messico", "NL": "Paesi Bassi", "NO": "Norvegia", "NZ": "Nuova Zelanda", "PL": "Polonia",
    "PT": "Portogallo", "RO": "Romania", "RS": "Serbia", "SE": "Svezia", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovacchia", "SM": "San Marino", "TR": "Turchia", "TW": "Taiwan",
    "UA": "Ucraina", "US": "Stati Uniti", "VA": "Citta' del Vaticano", "ZA": "Sudafrica",
}

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# ---------------------------------------------------------------------------
# Pulizia dei singoli valori
# ---------------------------------------------------------------------------

DATA_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?")
SPAZI_RE = re.compile(r"\s+")
FORMATO_TESTO_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*l\b", re.I)          # "Magnum 1.5 L"
FORMATO_TITOLO_RE = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(ml|cl|ltr|litres?|liters?|l)(?![a-z])", re.I)


def _vuoto(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in TESTI_VUOTI | {""})


def pulisci_testo(v):
    if _vuoto(v):
        return ""
    return SPAZI_RE.sub(" ", str(v)).strip()


def a_datetime(v):
    """Testo/ datetime del DB -> datetime (None se non e' una data valida)."""
    if isinstance(v, datetime):
        return v.replace(microsecond=0)
    if _vuoto(v):
        return None
    m = DATA_RE.match(str(v).strip())
    if not m:
        return None
    a, me, g, h, mi, s = (int(x) if x else 0 for x in m.groups())
    try:
        return datetime(a, me, g, h, mi, s)
    except ValueError:
        return None


def a_numero(v):
    if _vuoto(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    m = FORMATO_TESTO_RE.search(t) if not re.fullmatch(r"-?\d+(?:[.,]\d+)?", t) else None
    if m:
        t = m.group(1)
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def litri_da_titolo(titolo):
    """Formato (litri) indicato nel titolo, solo se e' uno e uno solo."""
    trovati = set()
    for num, unita in FORMATO_TITOLO_RE.findall(titolo or ""):
        x = float(num.replace(",", "."))
        u = unita.lower()
        x = x / 1000 if u == "ml" else x / 100 if u == "cl" else x
        if 0.02 <= x <= 30:
            trovati.add(round(x, 3))
    return trovati.pop() if len(trovati) == 1 else None


def formatta(colonna, valore, italiano):
    """Valore gia' pulito -> testo da scrivere nel CSV, secondo TIPI."""
    tipo = TIPI.get(colonna, "testo")
    if valore is None or valore == "":
        return ""
    if tipo == "data":
        d = valore if isinstance(valore, (date, datetime)) else a_datetime(valore)
        return d.strftime("%Y-%m-%d") if d else ""
    if tipo == "dataora":
        d = valore if isinstance(valore, datetime) else a_datetime(valore)
        return d.strftime("%Y-%m-%d %H:%M:%S") if d else ""
    if tipo == "intero":
        n = a_numero(valore)
        return str(int(round(n))) if n is not None else ""
    if tipo == "decimale":
        n = a_numero(valore)
        if n is None:
            return ""
        testo = str(int(n)) if n == int(n) else f"{n:.3f}".rstrip("0")
        return testo.replace(".", ",") if italiano else testo
    return pulisci_testo(valore)


# ---------------------------------------------------------------------------
# Lotti
# ---------------------------------------------------------------------------

def colonne_nazionalita(r, invenduti):
    """Colonne pulite della nazionalita' per una riga di `lots` (dict)."""
    naz = str(r.get("nazionalita") or "").strip()
    wid = str(r.get("winner_id") or "").strip()
    stato = str(r.get("status") or "").upper()
    esito = str(r.get("esito") or "")
    vuoto = dict.fromkeys(COLONNE_NAZIONALITA, "")
    if esito in ("invenduto", "non verificabile"):
        vuoto["nazionalita_stato"] = "non venduto" if esito == "invenduto" else "non verificabile"
        return vuoto
    if TOKEN_RE.match(wid) and naz.lower() not in SCONOSCIUTI:
        codice = naz.upper()
        return {"nazionalita_stato": "verificata", "nazionalita_codice": codice,
                "nazionalita_nome": PAESI.get(codice, codice),
                "winner_username": pulisci_testo(r.get("winner_username")), "winner_id": wid}
    if esito == "venduto":
        vuoto["nazionalita_stato"] = "da verificare"
    elif esito == "in corso" or stato != "CLOSED":
        vuoto["nazionalita_stato"] = "asta aperta"
    elif r.get("url") in invenduti or r.get("numero_offerte") in (0, "0"):
        vuoto["nazionalita_stato"] = "non venduto"
    else:
        vuoto["nazionalita_stato"] = "da verificare"
    return vuoto


def lotti_invenduti(conn):
    try:
        return {r[0] for r in conn.execute(
            "SELECT url FROM backfill_nazionalita WHERE esito = 'invenduto'")}
    except sqlite3.OperationalError:
        return set()


def correggi_formato(riga, stat):
    """formato in litri; se il titolo indica un formato unico diverso, vince il titolo."""
    db = a_numero(riga.get("formato"))
    tit = litri_da_titolo(riga.get("title"))
    if tit is not None and (db is None or abs(tit - db) > 0.001):
        stat["formato"] += 1
        return tit
    return db


def leggi_lotti(conn, escludi, pulisci, pulisci_maison=True):
    """Righe di `lots` gia' pulite, come lista di dict (chiave = colonna CSV)."""
    invenduti = lotti_invenduti(conn)
    cur = conn.execute("SELECT * FROM lots ORDER BY id")
    nomi = [d[0] for d in cur.description]
    tenute = [n for n in nomi
              if n not in escludi and n not in COLONNE_SOSTITUITE and n not in COLONNE_ESITO]
    intest = tenute + COLONNE_NAZIONALITA + [c for c in COLONNE_ESITO if c in nomi] + COLONNE_AGGIUNTE
    grezze = [dict(zip(nomi, r)) for r in cur.fetchall()]
    pul = None
    if pulisci and "distilleria" in nomi:
        pul = Pulitore([str(r["distilleria"] or "") for r in grezze])
    pul_m = None
    if pulisci_maison and "maison" in nomi:
        pul_m = PulitoreMaison([str(r["maison"] or "") for r in grezze])
    stat = {"formato": 0, "distilleria": 0, "maison": 0, "pul_maison": pul_m, "esclusi": Counter()}
    righe = []
    for g in grezze:
        r = {c: g.get(c) for c in tenute}
        r.update(colonne_nazionalita(g, invenduti))
        for c in COLONNE_ESITO:
            if c in nomi:
                r[c] = g[c]
        for c in ("title", "maison", "distilleria", "tipologia", "stile", "vintage", "eta",
                  "imbottigliatore", "status", "prezzo_riserva", "url"):
            if c in r:
                r[c] = pulisci_testo(r[c])
        if pul is not None:
            nuova = pul(r["distilleria"])
            stat["distilleria"] += nuova != r["distilleria"]
            r["distilleria"] = nuova
        if pul_m is not None:
            originale = r["maison"]
            nuova = pul_m(originale)
            if pul_m.escludi(nuova):
                stat["esclusi"][nuova] += 1
                continue
            stat["maison"] += nuova != originale
            r["maison"] = nuova
            r["tipologia"] = pul_m.tipologia(originale, r.get("tipologia"))
            motivo = pul_m.rivedi_lotto(r)  # oggetti non bottiglia, tipologia 'Items'
            if motivo:
                stat["esclusi"][motivo] += 1
                continue
        r["formato"] = correggi_formato(r, stat)
        dt = a_datetime(g.get("data_chiusura"))
        r["data_chiusura"] = dt.date() if dt else None
        r["data_ora_chiusura"] = dt
        r["timestamp"] = a_datetime(g.get("timestamp"))
        righe.append(r)
    return intest, righe, stat


def leggi_ritirati(conn, pulisci, escludi, pul_maison=None):
    try:
        cur = conn.execute("SELECT * FROM lotti_ritirati ORDER BY data_chiusura")
    except sqlite3.OperationalError:
        return None, []
    nomi = [d[0] for d in cur.description]
    cols_lots = {r[1] for r in conn.execute("PRAGMA table_info(lots)")}
    rinomina = ({"gruppo": "maison", "tipo": "tipologia", "annata": "vintage"} if "maison" in cols_lots
                else {"gruppo": "distilleria", "tipo": "stile", "annata": "eta"})
    tenute = [n for n in nomi if n != "dati_completi" and n not in escludi]
    intest = ["mese"] + [rinomina.get(n, n) for n in tenute] + COLONNE_AGGIUNTE
    grezze = [dict(zip(nomi, r)) for r in cur.fetchall()]
    pul = None
    if pulisci and "distilleria" in intest:
        pul = Pulitore([str(r.get("gruppo") or "") for r in grezze])
    stat = {"formato": 0}
    righe = []
    for g in grezze:
        r = {rinomina.get(n, n): (pulisci_testo(g[n]) if TIPI.get(rinomina.get(n, n), "testo") == "testo"
                                  else g[n]) for n in tenute}
        if pul is not None:
            r["distilleria"] = pul(r["distilleria"])
        if pul_maison is not None and "maison" in r:
            originale = r["maison"]
            r["maison"] = pul_maison(originale)
            if pul_maison.escludi(r["maison"]):
                continue
            r["tipologia"] = pul_maison.tipologia(originale, r.get("tipologia"))
            if pul_maison.rivedi_lotto(r):
                continue
        r["formato"] = correggi_formato(r, stat)
        dt = a_datetime(g.get("data_chiusura"))
        r["mese"] = dt.strftime("%Y-%m") if dt else ""
        r["data_chiusura"] = dt.date() if dt else None
        r["data_ora_chiusura"] = dt
        righe.append(r)
    return intest, righe


# ---------------------------------------------------------------------------
# DimCountry e Calendario (stesse colonne delle tabelle del report)
# ---------------------------------------------------------------------------

DIMCOUNTRY_COLONNE = ["nazionalita_codice", "NAZIONALITA",
                      "whisky_lotti_vinti", "whisky_prima_chiusura", "whisky_ultima_chiusura",
                      "whisky_ultima_rilevazione",
                      "champagne_lotti_vinti", "champagne_prima_chiusura", "champagne_ultima_chiusura",
                      "champagne_ultima_rilevazione"]

CALENDARIO_COLONNE = ["Data", "Mese Numero", "Mese Nome", "Quarter", "Anno",
                      "Mese Numero Fiscale", "Mese Nome Fiscale", "Quarter Fiscale", "Anno Fiscale"]


def costruisci_dimcountry(lotti):
    """lotti = {"whisky": righe, "champagne": righe}. Una riga per paese con almeno
    un lotto vinto (nazionalita' verificata), come la vecchia query Dim_Country."""
    paesi = {}
    for prog in ("whisky", "champagne"):
        for r in lotti.get(prog, []):
            cod = r.get("nazionalita_codice")
            if not cod:
                continue
            p = paesi.setdefault(cod, {"nazionalita_codice": cod, "NAZIONALITA": PAESI.get(cod, cod),
                                       "whisky_lotti_vinti": 0, "champagne_lotti_vinti": 0})
            p[f"{prog}_lotti_vinti"] += 1
            for chiave, val, fn in ((f"{prog}_prima_chiusura", r["data_chiusura"], min),
                                    (f"{prog}_ultima_chiusura", r["data_chiusura"], max),
                                    (f"{prog}_ultima_rilevazione", r["timestamp"], max)):
                if val is not None:
                    p[chiave] = fn(p[chiave], val) if p.get(chiave) is not None else val
    return sorted(paesi.values(), key=lambda p: p["NAZIONALITA"])


def costruisci_calendario(lotti):
    """Come la tabella DAX Calendario: anni interi dal primo all'ultimo data_chiusura,
    anno fiscale che parte a luglio."""
    date_ = [r["data_chiusura"] for righe in lotti.values() for r in righe if r["data_chiusura"]]
    if not date_:
        return []
    righe = []
    for o in range(date(min(date_).year, 1, 1).toordinal(), date(max(date_).year, 12, 31).toordinal() + 1):
        d = date.fromordinal(o)
        mf = d.month - 6 if d.month >= 7 else d.month + 6
        righe.append({"Data": d, "Mese Numero": d.month, "Mese Nome": MESI[d.month - 1],
                      "Quarter": f"Q{(d.month - 1) // 3 + 1}", "Anno": d.year,
                      "Mese Numero Fiscale": mf, "Mese Nome Fiscale": MESI[d.month - 1],
                      "Quarter Fiscale": f"Q{(mf - 1) // 3 + 1}",
                      "Anno Fiscale": d.year + 1 if d.month >= 7 else d.year})
    return righe


# ---------------------------------------------------------------------------
# Scrittura e verifica
# ---------------------------------------------------------------------------

def scrivi_csv(path, intestazione, righe, italiano):
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";" if italiano else ",", quoting=csv.QUOTE_MINIMAL)
        w.writerow(intestazione)
        for r in righe:
            w.writerow([formatta(c, r.get(c), italiano) for c in intestazione])
    os.replace(tmp, path)  # Power BI non vede mai un CSV scritto a meta'
    return len(righe)


CONTROLLI = {
    "data": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "dataora": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
    "intero": re.compile(r"^-?\d+$"),
    "decimale": re.compile(r"^-?\d+(?:[.,]\d+)?$"),
}


def verifica_csv(path, italiano, chiave=None):
    """Rilegge il CSV e controlla che ogni cella rispetti il tipo della colonna."""
    errori = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        lett = csv.reader(f, delimiter=";" if italiano else ",")
        intest = next(lett)
        visti = set()
        for n, riga in enumerate(lett, start=2):
            if len(riga) != len(intest):
                errori.append(f"riga {n}: {len(riga)} colonne invece di {len(intest)}")
                continue
            for c, v in zip(intest, riga):
                tipo = TIPI.get(c, "testo")
                if v == "":
                    continue
                if tipo in CONTROLLI and not CONTROLLI[tipo].match(v):
                    errori.append(f"riga {n}, {c}: '{v}' non e' {tipo}")
                elif tipo == "testo" and (v != v.strip() or "  " in v or v.lower() in TESTI_VUOTI):
                    errori.append(f"riga {n}, {c}: testo non pulito '{v[:40]}'")
            if chiave:
                k = riga[intest.index(chiave)]
                if k in visti:
                    errori.append(f"riga {n}: {chiave} duplicato ({k})")
                visti.add(k)
    if errori:
        print(f"  VERIFICA {path.name}: {len(errori)} problemi, primi 5:")
        for e in errori[:5]:
            print("    -", e)
    else:
        print(f"  verifica {path.name}: OK")
    return not errori


def main():
    p = argparse.ArgumentParser(description="Esporta i database Elite-Dashboard in CSV per Power BI")
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parent.parent)
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--formato-italiano", action="store_true")
    p.add_argument("--tieni-colonne-vuote", action="store_true")
    p.add_argument("--solo", choices=["whisky", "champagne"])
    p.add_argument("--senza-pulizia-distilleria", action="store_true")
    p.add_argument("--senza-pulizia-maison", action="store_true")
    a = p.parse_args()

    escludi = set() if a.tieni_colonne_vuote else COLONNE_DA_ESCLUDERE
    ita = a.formato_italiano
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"Cartella progetto: {a.base}")
    print(f"Cartella output:   {a.out}")

    ok = True
    lotti = {}
    for prog, nome_csv, rel in SORGENTI:
        db = a.base / rel
        print(f"\n{nome_csv}")
        if not db.exists():
            print(f"  ATTENZIONE: database non trovato: {db}")
            ok = False
            continue
        conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            intest, righe, stat = leggi_lotti(conn, escludi, not a.senza_pulizia_distilleria,
                                              not a.senza_pulizia_maison)
            lotti[prog] = righe
            if a.solo and a.solo != prog:
                print("  (solo letto per DimCountry/Calendario, CSV non riscritto)")
                continue
            n = scrivi_csv(a.out / nome_csv, intest, righe, ita)
            print(f"  {n} righe scritte; formato corretto dal titolo su {stat['formato']} righe"
                  + (f"; distilleria pulita su {stat['distilleria']} righe" if prog == "whisky" else "")
                  + (f"; maison pulita su {stat['maison']} righe" if stat["pul_maison"] else ""))
            for motivo, quanti in stat["esclusi"].items():
                print(f"  esclusi {quanti} lotti '{motivo}'")
            ok &= verifica_csv(a.out / nome_csv, ita, chiave="id")

            intest_r, righe_r = leggi_ritirati(conn, not a.senza_pulizia_distilleria, escludi,
                                              stat["pul_maison"])
            if intest_r:
                out_r = a.out / nome_csv.replace("lotti_", "lotti_ritirati_")
                print(f"  {scrivi_csv(out_r, intest_r, righe_r, ita)} lotti ritirati -> {out_r.name}")
                ok &= verifica_csv(out_r, ita, chiave="url")
        finally:
            conn.close()

    if len(lotti) == 2:
        print("\nDimCountry.csv")
        paesi = costruisci_dimcountry(lotti)
        print(f"  {scrivi_csv(a.out / 'DimCountry.csv', DIMCOUNTRY_COLONNE, paesi, ita)} paesi")
        ok &= verifica_csv(a.out / "DimCountry.csv", ita, chiave="nazionalita_codice")

        print("\nCalendario.csv")
        cal = costruisci_calendario(lotti)
        print(f"  {scrivi_csv(a.out / 'Calendario.csv', CALENDARIO_COLONNE, cal, ita)} giorni"
              f" ({cal[0]['Data']} -> {cal[-1]['Data']})")
        ok &= verifica_csv(a.out / "Calendario.csv", ita, chiave="Data")
    else:
        print("\nDimCountry.csv e Calendario.csv non aggiornati: serve leggere entrambi i database")

    print("\nTutto OK." if ok else "\nATTENZIONE: ci sono problemi, leggi sopra.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
