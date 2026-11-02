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

# Quante ultime vendite numerare sul grafico e nell'elenco con i link (/grafico)
ULTIME_NUMERATE = 10

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


# ---------------------------------------------------------------- edizioni speciali
# Collaborazioni ed edizioni speciali riconosciute dal titolo del lotto (01/11/2026).
# Nel database non c'e' una colonna "edizione": una Dom Perignon 2008 Lenny Kravitz
# finiva nella tipologia "Brut" insieme alla 2008 normale e falsava la media.
# NB: la sola parola "edition" NON basta: "Krug Grande Cuvee 170eme Edition" o
# "Labruyere XIII Edition" sono la numerazione della cuvee normale.
# Ordine: prima i nomi specifici, poi le categorie generiche.
# Terzo valore: "champagne" = vale solo per lo champagne (nel whisky "Batch 007" o
# "Sakura Cask" non sono edizioni speciali); None = vale per tutti e due.
EDIZIONI = [
    # Dom Perignon
    (r"lady\s*gaga", "Lady Gaga", "champagne"),
    (r"lenny\s*kravitz|\bkravitz\b", "Lenny Kravitz", "champagne"),
    (r"basquiat", "Jean-Michel Basquiat", "champagne"),
    (r"damien\s*hirst|\bhirst\b", "Damien Hirst", "champagne"),
    (r"murakami", "Takashi Murakami", "champagne"),
    (r"warhol", "Andy Warhol", "champagne"),
    (r"david\s*lynch", "David Lynch", "champagne"),
    (r"koons|balloon\s*venus", "Jeff Koons", "champagne"),
    (r"michael\s*riedel", "Michael Riedel", "champagne"),
    (r"tokujin|yoshioka", "Tokujin Yoshioka", "champagne"),
    (r"szekely", "Martin Szekely", "champagne"),
    (r"iris\s*van\s*herpen|van\s*herpen", "Iris van Herpen", "champagne"),
    (r"bjork|cunningham", "Bjork & Chris Cunningham", "champagne"),
    (r"lagerfeld", "Karl Lagerfeld", "champagne"),
    (r"marc\s*newson", "Marc Newson", "champagne"),
    (r"kaukoranta", "Edward Kaukoranta", "champagne"),
    (r"legacy\s*edition", "Legacy Edition", None),
    # altre maison
    (r"kusama", "Yayoi Kusama", "champagne"),
    (r"jacquemus", "Jacquemus", "champagne"),
    (r"yinka\s*ilori", "Yinka Ilori", "champagne"),
    (r"pharrell", "Pharrell", "champagne"),
    (r"starck", "Philippe Starck", "champagne"),
    (r"laposse", "Fernando Laposse", "champagne"),
    (r"gaultier", "Jean-Paul Gaultier", "champagne"),
    (r"\b007\b", "007", "champagne"),
    (r"tour\s*eiffel|olympic|la\s*flamme|jeux\s*olympiques", "Olimpiadi / Tour Eiffel", "champagne"),
    (r"golf\s*edition", "Golf Edition", "champagne"),
    (r"monaco", "Monaco", "champagne"),
    (r"sakura", "Sakura", "champagne"),
    (r"bugatti", "Bugatti", "champagne"),
    (r"millennium", "Millennium", None),
    # categorie generiche
    (r"luminous", "Luminous", None),
    (r"limited\s*edition|edition\s*limitee|limited\s*edition|edizione\s*limitata|"
     r"special\s*edition|edition\s*speciale|edizione\s*speciale|collector", "Edizione limitata", None),
    (r"cooler|ice\s*box|ice\s*jacket|bucket|seau|\bglass(es)?\b|flutes?\b|calici|bicchieri|verres", "Con accessori", None),
]
_EDIZIONI_RE = [(re.compile(p), nome, solo) for p, nome, solo in EDIZIONI]


def rileva_edizione(titolo, profilo=None):
    """Nome dell'edizione speciale dal titolo, oppure None se e' una bottiglia standard.
    profilo: 'champagne' o 'whisky' (le voci solo-champagne non valgono per il whisky)."""
    t = norma(titolo)
    for rx, nome, solo in _EDIZIONI_RE:
        if solo and profilo and solo != profilo:
            continue
        if rx.search(t):
            return nome
    return None


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
        r = dict(r)
        if profilo == "champagne":
            r["tipologia"] = _correggi_tipologia(r["tipologia"], r["title"])
        yield r


def _correggi_tipologia(tipologia, titolo):
    """Il parser riconosce 'P2' ma non 'Plenitude 2' scritto per esteso (Dom Perignon)."""
    t = norma(titolo)
    m = re.search(r"plenitude\s*(2|3|deuxieme|troisieme|second|third)", t)
    if m:
        p = "P3" if m.group(1) in ("3", "troisieme", "third") else "P2"
        return p + (" Rosé" if "rose" in t else "")
    return tipologia


def cerca(db_path: str, profilo: str, produttore: str, tipologia: str = "",
          annata: str = "", formato: str = "", edizione: str = "") -> dict:
    """edizione: '' = solo bottiglie standard (default), '*' o 'tutte' = tutto,
    'speciali' = solo edizioni speciali, oppure un nome (es. 'Lady Gaga')."""
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

    # --- edizioni speciali
    from collections import Counter
    con_ed = [(r, rileva_edizione(r["title"], profilo)) for r in trovati]
    tutte_ed = Counter(ed for _, ed in con_ed if ed)
    grezzo = (edizione or "").strip().lower()
    e = norma(edizione)
    if grezzo in ("*", "-", "tutte", "tutto", "tutti", "all", "any"):
        scelti, escluse = con_ed, Counter()
    elif not e:
        scelti = [(r, ed) for r, ed in con_ed if ed is None]
        escluse = tutte_ed
    elif e in ("speciali", "speciale", "special"):
        scelti = [(r, ed) for r, ed in con_ed if ed]
        escluse = Counter()
    else:
        scelti = [(r, ed) for r, ed in con_ed if ed and e in norma(ed)]
        escluse = Counter()
    if not scelti:
        sugg = [f"{k} ({v})" for k, v in tutte_ed.most_common()]
        if e and any(ed is None for _, ed in con_ed):
            sugg = ["standard: lascia vuoto il 5° campo"] + sugg
        return {"errore": "Nessuna vendita per questa edizione." if e
                else "Ci sono solo edizioni speciali per questa bottiglia.",
                "campo": "Edizione", "suggerimenti": sugg}
    trovati = [r for r, _ in scelti]
    nomi_ed = {ed for _, ed in scelti}
    if grezzo in ("*", "-", "tutte", "tutto", "tutti", "all", "any"):
        etichetta_ed = "Tutte le edizioni"
    elif not e:
        etichetta_ed = "Standard"
    elif len(nomi_ed) == 1 and None not in nomi_ed:
        etichetta_ed = nomi_ed.pop()
    elif e in ("speciali", "speciale", "special"):
        etichetta_ed = "Edizioni speciali"
    else:
        etichetta_ed = "Tutte le edizioni"

    # Se 'contiene' ha trovato piu' produttori diversi, li segnaliamo
    produttori = sorted({r["produttore"] for r in trovati if r["produttore"]})
    # Nel titolo usiamo i nomi come sono scritti nel database (se univoci)
    def nome_db(campo, richiesto):
        valori = {r[campo] for r in trovati if r[campo]}
        return str(valori.pop()) if len(valori) == 1 else richiesto
    voce = (nome_db("produttore", produttore), nome_db("tipologia", tipologia),
            nome_db("annata", annata), nome_db("formato", formato), etichetta_ed)

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
            "edizione": rileva_edizione(r["title"], profilo),
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

    # Statistiche separate per edizione (utile con '| tutte' o '| speciali')
    gruppi = {}
    for v in vendite:
        gruppi.setdefault(v["edizione"] or "Standard", []).append(v)
    per_edizione = []
    for nome, vv in gruppi.items():
        pp = [x["prezzo_bott"] for x in vv]
        per_edizione.append({"nome": nome, "vendite": len(vv), "media": sum(pp) / len(pp),
                             "ultimo": vv[-1]})
    per_edizione.sort(key=lambda g: (g["nome"] != "Standard", -g["vendite"]))

    return {
        "profilo": profilo,
        "richiesta": voce,
        "per_edizione": per_edizione,
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
        "escluse": dict(escluse.most_common()),  # edizioni speciali tolte dal calcolo
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

    voce = " · ".join(escape(str(x)) for x in ris["richiesta"] if norma(x) not in JOLLY)
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
    if len(ris.get("per_edizione", [])) > 1:
        righe += ["", "📋 <b>Per edizione</b> (media / ultima vendita):"]
        for g in ris["per_edizione"][:10]:
            u2 = g["ultimo"]
            righe.append(f"    • <b>{escape(g['nome'])}</b>: {g['vendite']} vend. · media {euro(g['media'])}"
                         f" · ultima {euro(u2['prezzo_bott'])} ({u2['data'][8:10]}/{u2['data'][5:7]}/{u2['data'][2:4]})")
        if len(ris["per_edizione"]) > 10:
            righe.append(f"    … e altre {len(ris['per_edizione']) - 10}")
    if len(ris["produttori"]) > 1:
        righe += ["", "⚠️ Ho unito più nomi: " + ", ".join(escape(x) for x in ris["produttori"][:8])
                  + ". Scrivi il nome completo per restringere."]
    if ris.get("escluse"):
        n_esc = sum(ris["escluse"].values())
        elenco = ", ".join(f"{escape(k)} ({v})" for k, v in list(ris["escluse"].items())[:8])
        righe += ["", f"🎨 <b>Escluse {n_esc} edizioni speciali:</b> {elenco}",
                  "    aggiungi <code>| nome</code> come 5° campo per vederne una, "
                  "<code>| tutte</code> per includerle"]
    righe += ["", "<i>Solo lotti venduti, lotti misti esclusi. Prezzi in euro, al netto di spedizione.</i>"]
    return "\n".join(righe)


def formatta_elenco(ris: dict, n: int = ULTIME_NUMERATE) -> str:
    """Ultime n vendite con link, numerate come i punti del grafico (1 = la piu' recente)."""
    from html import escape
    ultime = list(reversed(ris["storico"]))[:n]
    righe = [f"🔗 <b>Ultime {len(ultime)} vendite</b> (numeri come sul grafico):"]
    for i, v in enumerate(ultime, 1):
        d = v["data"]
        ed = v.get("edizione") or "Standard"
        bott = f" ({v['bottiglie']} bott.)" if v["bottiglie"] > 1 else ""
        righe.append(f"<b>{i}.</b> {d[8:10]}/{d[5:7]}/{d[2:4]} · {euro(v['prezzo_bott'])}/bott.{bott}"
                     f" · {escape(ed)} · <a href=\"{escape(v['url'] or '')}\">asta</a>")
    return "\n".join(righe)


def interpreta_argomenti(testo: str):
    """'/prezzo Dom Perignon | Brut | 2012 | 0.75' -> ['Dom Perignon', 'Brut', '2012', '0.75']"""
    corpo = re.sub(r"^/\S+\s*", "", testo or "").strip()
    if not corpo:
        return []
    sep = "|" if "|" in corpo else (";" if ";" in corpo else ",")
    parti = [x.strip() for x in corpo.split(sep)]
    return (parti + ["", "", "", ""])[:5]


AIUTO = (
    "Uso: <code>/prezzo {campi}</code>\n\n"
    "Esempi:\n"
    "{esempi}\n\n"
    "Il separatore può essere | oppure ;  —  usa * per non filtrare un campo.\n"
    "5° campo facoltativo, l'edizione: vuoto = solo bottiglie standard, "
    "<code>Lady Gaga</code>, <code>Luminous</code>… = solo quell'edizione, "
    "<code>speciali</code> = tutte le edizioni speciali, <code>tutte</code> = tutto.\n"
    "Formati: 0.75 / 75cl, 0.70 / 70cl, magnum / 1.5, jeroboam / 3."
)
