"""
price_lookup.py - statistiche di prezzo di una bottiglia dall'archivio SQLite (01/11/2026).

Usato dal comando Telegram /prezzo. Legge il database in sola lettura, quindi
puo' girare mentre lo scraper scrive.

Per una bottiglia (produttore + tipologia + annata + formato) restituisce:
  - prezzo medio di vendita per bottiglia (solo lotti VENDUTI, lotti misti esclusi)
  - data, prezzo di chiusura e link dell'ultimo lotto venduto in archivio
  - trend %: media delle ultime N vendite contro le N precedenti
  - scostamento dell'ultima chiusura dalla media

Lo stesso file esiste identico nei progetti champagne e whisky: cambia solo
la configurazione (PROFILI) scelta dal bot.
"""
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

# Quante vendite confrontare per il trend (ultime N contro le N precedenti)
TREND_FINESTRA = 5

# Colonne del database per ciascun progetto
PROFILI = {
    "champagne": {
        "produttore": "maison",
        "tipologia": "tipologia",
        "annata": "vintage",
        "emoji": "🍾",
        "etichette": ("Maison", "Tipologia", "Annata", "Formato"),
    },
    "whisky": {
        "produttore": "distilleria",
        "tipologia": "stile",
        "annata": "eta",
        "emoji": "🥃",
        "etichette": ("Distilleria", "Stile", "Età/Annata", "Formato"),
    },
}

JOLLY = ("", "*", "-", "tutti", "tutte", "any", "all")


# ---------------------------------------------------------------- normalizzazione

def norma(testo) -> str:
    """minuscolo, senza accenti, spazi e punteggiatura compattati: 'Möet & Chandon' -> 'moet chandon'"""
    if testo is None:
        return ""
    t = unicodedata.normalize("NFKD", str(testo))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9.]+", " ", t)
    return t.strip()


def formato_chiave(testo) -> str:
    """Riduce formati scritti in modi diversi a una chiave unica.
    '75cl', '0,75', '0.75 L', '750ml' -> '0.75'   ·   'magnum', '1.5', '150cl' -> 'magnum'"""
    t = norma(str(testo).replace(",", ".")).replace(" ", "")
    t = re.sub(r"(litri|litro|litre|liter|lt)$", "l", t)
    if not t:
        return ""
    if "jeroboam" in t or re.fullmatch(r"3(\.0)?l?|300cl", t):
        return "jeroboam"
    if "magnum" in t or re.fullmatch(r"1\.5l?|150cl|1500ml", t):
        return "magnum"
    if re.fullmatch(r"0?\.75l?|75(cl)?|750ml", t):
        return "0.75"
    if re.fullmatch(r"0?\.70?l?|70(cl)?|700ml", t):
        return "0.70"
    if re.fullmatch(r"0?\.50?l?|50(cl)?|500ml", t):
        return "0.5"
    if re.fullmatch(r"1(\.0)?l?|100cl|1000ml", t):
        return "1.0"
    return t


def annata_corrisponde(richiesta: str, valore, profilo: str) -> bool:
    r, v = norma(richiesta), norma(valore)
    if r == v:
        return True
    if profilo == "whisky":
        # '12' -> '12 Years' e '12 Years (2010)';  '2010' -> anche '12 Years (2010)'
        if re.fullmatch(r"\d{1,2}", r):
            return re.match(rf"{r} years?\b", v) is not None
        if re.fullmatch(r"\d{4}", r):
            return re.search(rf"\b{r}\b", v) is not None
    return False


def produttore_corrisponde(richiesta: str, valore) -> bool:
    """Prima uguaglianza; poi 'contiene' (es. 'krug' trova 'Krug', 'dom perignon' trova 'Dom Perignon')."""
    r, v = norma(richiesta), norma(valore)
    return bool(r) and (r == v or r in v)


# ---------------------------------------------------------------- query

def _apri(db_path: str) -> sqlite3.Connection:
    # Sola lettura: non blocca lo scraper e non puo' modificare dati per errore
    uri = "file:" + os.path.abspath(db_path).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _colonne(con) -> set:
    return {r[1] for r in con.execute("PRAGMA table_info(lots)").fetchall()}


def _lotti_venduti(con, profilo: str):
    """Tutti i lotti venduti con un prezzo valido, gia' chiusi."""
    p = PROFILI[profilo]
    cols = _colonne(con)
    ha_esito = "esito" in cols
    sel = (f"SELECT {p['produttore']} AS produttore, {p['tipologia']} AS tipologia, "
           f"{p['annata']} AS annata, formato, numero_bottiglie, prezzo_finale, "
           f"data_chiusura, url, title, is_mixed, status"
           + (", esito" if ha_esito else ", NULL AS esito")
           + " FROM lots WHERE prezzo_finale IS NOT NULL AND prezzo_finale > 0")
    adesso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    for r in con.execute(sel):
        esito = (r["esito"] or "").lower()
        if esito:
            if esito != "venduto":
                continue
        elif r["status"] != "CLOSED":
            # lotti vecchi senza esito: vale lo stato CLOSED
            continue
        if r["is_mixed"]:
            continue
        data = r["data_chiusura"] or ""
        if not re.match(r"\d{4}-\d{2}-\d{2}", data) or data > adesso:
            continue
        yield r


def cerca(db_path: str, profilo: str, produttore: str, tipologia: str = "",
          annata: str = "", formato: str = "") -> dict:
    """Restituisce un dict con le statistiche, oppure {'errore': ..., 'suggerimenti': ...}."""
    if not os.path.exists(db_path):
        return {"errore": f"Database non trovato: {db_path}"}

    con = _apri(db_path)
    try:
        venduti = list(_lotti_venduti(con, profilo))
    finally:
        con.close()

    def filtra(righe, livello):
        out = righe
        if livello >= 1:
            out = [r for r in out if produttore_corrisponde(produttore, r["produttore"])]
        if livello >= 2 and norma(tipologia) not in JOLLY:
            out = [r for r in out if norma(r["tipologia"]) == norma(tipologia)]
        if livello >= 3 and norma(annata) not in JOLLY:
            out = [r for r in out if annata_corrisponde(annata, r["annata"], profilo)]
        if livello >= 4 and norma(formato) not in JOLLY:
            fk = formato_chiave(formato)
            out = [r for r in out if formato_chiave(r["formato"]) == fk]
        return out

    trovati = filtra(venduti, 4)
    if not trovati:
        return _senza_risultati(venduti, filtra, profilo)

    # Se 'contiene' ha trovato piu' produttori diversi, li segnaliamo
    produttori = sorted({r["produttore"] for r in trovati if r["produttore"]})
    # Nel titolo usiamo i nomi come sono scritti nel database (se univoci)
    def nome_db(campo, richiesto):
        valori = {r[campo] for r in trovati if r[campo]}
        return str(valori.pop()) if len(valori) == 1 else richiesto
    voce = (nome_db("produttore", produttore), nome_db("tipologia", tipologia),
            nome_db("annata", annata), nome_db("formato", formato))

    vendite = []
    for r in trovati:
        n = r["numero_bottiglie"] or 1
        if n <= 0:
            n = 1
        vendite.append({
            "data": r["data_chiusura"],
            "prezzo_lotto": float(r["prezzo_finale"]),
            "bottiglie": n,
            "prezzo_bott": float(r["prezzo_finale"]) / n,
            "url": r["url"],
            "title": r["title"],
            "formato": r["formato"],
        })
    vendite.sort(key=lambda v: v["data"])

    prezzi = [v["prezzo_bott"] for v in vendite]
    media = sum(prezzi) / len(prezzi)
    ultimo = vendite[-1]

    # Trend: ultime N vendite contro le N precedenti (se poche vendite: due meta')
    n = len(prezzi)
    trend, base_trend = None, ""
    if n >= 2:
        k = min(TREND_FINESTRA, n // 2)
        recenti, precedenti = prezzi[-k:], prezzi[-2 * k:-k]
        m_rec, m_prec = sum(recenti) / k, sum(precedenti) / k
        if m_prec > 0:
            trend = (m_rec - m_prec) / m_prec * 100
            base_trend = ("ultima vendita vs precedente" if k == 1
                          else f"media ultime {k} vendite vs {k} precedenti")

    return {
        "profilo": profilo,
        "richiesta": voce,
        "produttori": produttori,
        "vendite": n,
        "bottiglie": sum(v["bottiglie"] for v in vendite),
        "media": media,
        "min": min(prezzi),
        "max": max(prezzi),
        "ultimo": ultimo,
        "ultimo_vs_media": (ultimo["prezzo_bott"] - media) / media * 100 if media else None,
        "trend": trend,
        "base_trend": base_trend,
        "storico": vendite,  # tutte le vendite in ordine di data (per /grafico)
    }


def _senza_risultati(venduti, filtra, profilo):
    """Trova a che filtro la ricerca si svuota e propone i valori disponibili."""
    nomi = ("produttore", "tipologia", "annata", "formato")
    etichette = PROFILI[profilo]["etichette"]
    for livello in range(1, 5):
        if not filtra(venduti, livello):
            precedente = filtra(venduti, livello - 1)
            campo = nomi[livello - 1]
            if campo == "formato":
                valori = {r["formato"] for r in precedente}
            else:
                valori = {r[campo] for r in precedente}
            valori = sorted(str(v) for v in valori if v not in (None, ""))
            if campo == "produttore" and len(valori) > 40:
                valori = []  # troppi per suggerirli tutti
            return {"errore": f"Nessuna vendita trovata: {etichette[livello - 1]} non corrisponde.",
                    "campo": etichette[livello - 1], "suggerimenti": valori[:25]}
    return {"errore": "Nessuna vendita trovata."}


# ---------------------------------------------------------------- testo per Telegram

def euro(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def pct(x) -> str:
    if x is None:
        return "n.d."
    freccia = "📈" if x > 0.05 else ("📉" if x < -0.05 else "➖")
    return f"{freccia} {x:+.1f}%".replace(".", ",")


def data_it(s: str) -> str:
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M") + " UTC"
    except Exception:
        return s


def formatta(ris: dict, profilo: str) -> str:
    """Messaggio HTML per Telegram."""
    from html import escape
    p = PROFILI[profilo]
    if "errore" in ris:
        msg = f"❌ {escape(ris['errore'])}"
        if ris.get("suggerimenti"):
            msg += f"\n\nValori disponibili per {escape(ris['campo'])}:\n" + \
                   ", ".join(escape(s) for s in ris["suggerimenti"])
        return msg

    prod, tip, ann, fmt = ris["richiesta"]
    voce = " · ".join(escape(x) for x in (prod, tip, ann, fmt) if norma(x) not in JOLLY)
    u = ris["ultimo"]
    righe = [
        f"{p['emoji']} <b>{voce}</b>",
        "",
        f"💶 <b>Prezzo medio di vendita:</b> {euro(ris['media'])} / bott.",
        f"    min {euro(ris['min'])} · max {euro(ris['max'])}",
        f"    su {ris['vendite']} {'lotto venduto' if ris['vendite'] == 1 else 'lotti venduti'}"
        f" ({ris['bottiglie']} {'bottiglia' if ris['bottiglie'] == 1 else 'bottiglie'})",
        "",
        f"🔨 <b>Ultimo lotto in archivio:</b> {data_it(u['data'])}",
        f"    chiusura {euro(u['prezzo_lotto'])}"
        + (f" ({u['bottiglie']} bott. → {euro(u['prezzo_bott'])} / bott.)" if u["bottiglie"] > 1 else ""),
        f"    vs media: {pct(ris['ultimo_vs_media'])}",
        f"    <a href=\"{escape(u['url'] or '')}\">apri il lotto</a>",
        "",
        f"📊 <b>Trend:</b> {pct(ris['trend'])}"
        + (f" <i>({ris['base_trend']})</i>" if ris["base_trend"] else " <i>(serve almeno 2 vendite)</i>"),
    ]
    if len(ris["produttori"]) > 1:
        righe += ["", "⚠️ Ho unito più nomi: " + ", ".join(escape(x) for x in ris["produttori"][:8])
                  + ". Scrivi il nome completo per restringere."]
    righe += ["", "<i>Solo lotti venduti, lotti misti esclusi. Prezzi in euro, al netto di spedizione.</i>"]
    return "\n".join(righe)


def interpreta_argomenti(testo: str):
    """'/prezzo Dom Perignon | Brut | 2012 | 0.75' -> ['Dom Perignon', 'Brut', '2012', '0.75']"""
    corpo = re.sub(r"^/\S+\s*", "", testo or "").strip()
    if not corpo:
        return []
    sep = "|" if "|" in corpo else (";" if ";" in corpo else ",")
    parti = [x.strip() for x in corpo.split(sep)]
    return (parti + ["", "", ""])[:4]


AIUTO = (
    "Uso: <code>/prezzo {campi}</code>\n\n"
    "Esempi:\n"
    "{esempi}\n\n"
    "Il separatore può essere | oppure ;  —  usa * per non filtrare un campo.\n"
    "Formati: 0.75 / 75cl, 0.70 / 70cl, magnum / 1.5, jeroboam / 3."
)
