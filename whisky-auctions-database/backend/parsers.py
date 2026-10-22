"""
Advanced parsing logic for whisky lot titles
Extracts: distilleria, stile, eta, and special editions
"""
import re
from typing import Dict, Optional

# Known whisky distilleries
KNOWN_DISTILLERIAS = {
    "macallan": "The Macallan",
    "ardbeg": "Ardbeg",
    "lagavulin": "Lagavulin",
    "laphroaig": "Laphroaig",
    "bowmore": "Bowmore",
    "highland park": "Highland Park",
    "talisker": "Talisker",
    "glenfiddich": "Glenfiddich",
    "glenlivet": "The Glenlivet",
    "balvenie": "The Balvenie",
    "springbank": "Springbank",
    "yamazaki": "Yamazaki",
    "hibiki": "Hibiki",
    "nikka": "Nikka",
    "buffalo trace": "Buffalo Trace",
    "blanton": "Blanton's",
    "glenmorangie": "Glenmorangie",
    "caol ila": "Caol Ila",
    "bunnahabhain": "Bunnahabhain",
    "bruichladdich": "Bruichladdich",
    "octomore": "Octomore",
    "kilchoman": "Kilchoman",
    "dalmore": "The Dalmore",
    "glendronach": "The Glendronach",
    "glenfarclas": "Glenfarclas",
    "oban": "Oban",
    "pappy van winkle": "Pappy Van Winkle",
    "wellers": "W.L. Weller",
    "rosebank": "Rosebank",
    "port ellen": "Port Ellen",
    "brora": "Brora",
    "karuizawa": "Karuizawa",
    "hanyu": "Hanyu",
    "chichibu": "Chichibu",
    "glenkinchie": "Glenkinchie",
    "mortlach": "Mortlach",
    "linkwood": "Linkwood",
    "old pulteney": "Old Pulteney",
    "glengoyne": "Glengoyne",
    "auchentoshan": "Auchentoshan",
    "glen scotia": "Glen Scotia",
    "arran": "Arran",
    "jura": "Jura",
    "tobermory": "Tobermory",
    "ledaig": "Ledaig",
    "benriach": "BenRiach",
    "glenallachie": "GlenAllachie",
    "tamdhu": "Tamdhu",
    "benromach": "Benromach",
    "aberlour": "Aberlour",
    "cardhu": "Cardhu",
    "craigellachie": "Craigellachie",
    "dailuaine": "Dailuaine",
    "teaninich": "Teaninich",
    "clynelish": "Clynelish",
    "daftmill": "Daftmill",
    "johnnie walker": "Johnnie Walker",
    "chivas regal": "Chivas Regal",
    "jack daniel": "Jack Daniel's",
    "maker's mark": "Maker's Mark",
    "jim beam": "Jim Beam",
    "wild turkey": "Wild Turkey",
    "woodford reserve": "Woodford Reserve",
    "blanton": "Blanton's",
    "pappy van winkle": "Pappy Van Winkle",
    "suntory": "Suntory",
    "ichiro": "Ichiro's Malt",
    "kavalan": "Kavalan",
    "amrut": "Amrut",
    "banton": "Blanton's",
    "four roses": "Four Roses",
    "glen scotia": "Glen Scotia",
    "yamazaki": "Yamazaki",
    "hibiki": "Hibiki",
    "hakushu": "Hakushu",
    "nikka": "Nikka",
    "justerini & brooks": "Justerini & Brooks",
    "knockando": "Knockando",
    "j&b": "Justerini & Brooks",
}

# Alias aggiuntivi (30/09/2026): nomi che nei titoli compaiono in forme diverse
KNOWN_DISTILLERIAS.update({
    "stagg": "Stagg",
    "george t. stagg": "George T. Stagg",
    "old bushmills": "Bushmills",
    "bushmills": "Bushmills",
    "macallan": "The Macallan",
    "the macallan": "The Macallan",
    "glen grant": "Glen Grant",
    "royal salute": "Royal Salute",
    "ballantine's": "Ballantine's",
    "caperdonich": "Caperdonich",
    "redbreast": "Redbreast",
    "midleton": "Midleton",
    "crown royal": "Crown Royal",
    "port dundas": "Port Dundas",
    "whyte & mackay": "Whyte & Mackay",
    "white horse": "White Horse",
    "dewar's": "Dewar's",
    "bell's": "Bell's",
    "100 pipers": "100 Pipers",
})

# Whisky styles detection
STILE_PATTERNS = {
    r"single\s*malt": "Single Malt",
    r"blended\s*malt": "Blended Malt",
    r"blended\s*whisky|blended\s*scotch": "Blended",
    r"bourbon": "Bourbon",
    r"rye": "Rye",
    r"single\s*grain": "Single Grain",
    r"single\s*cask": "Single Cask",
    r"cask\s*strength": "Cask Strength",
    r"peated": "Peated",
    r"japanese\s*whisky": "Japanese Whisky",
    r"irish\s*whiskey": "Irish Whiskey",
}

# Special editions and limited releases
SPECIAL_KEYWORDS = {
    "limited edition": "Limited Edition",
    "special release": "Special Release",
    "distiller's edition": "Distillers Edition",
    "cask strength": "Cask Strength",
    "sherry oak": "Sherry Oak",
    "double wood": "Double Wood",
    "port wood": "Port Wood",
    "peat monster": "Peat Monster",
    "anniversary": "Anniversary Edition",
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison"""
    text = text.lower().strip()
    return text


# ---------------------------------------------------------------------------
# Distilleria (riscritto il 30/09/2026)
# ---------------------------------------------------------------------------
# Prima si cercava nel titolo solo una lista di ~80 nomi: tutto il resto
# (Caperdonich, Glen Garioch, Bushmills, Royal Salute...) finiva in "Unknown"
# (4.980 lotti su 21.661). Ora, in ordine:
#   1. scheda del lotto su Catawiki (campo "Distillery"/"Brand"), se disponibile
#   2. titolo: Catawiki compone i titoli whisky sempre come
#      "<Distilleria> [annata] [eta'] [prodotto] - [imbottigliatore] - b. [anno] - [formato]"
#      quindi la distilleria e' la parte iniziale del titolo, prima di annata/eta'.
#      La si confronta con i nomi noti e con il vocabolario costruito dai dati
#      (distillerie_vocabolario.json), per ridurre "Caperdonich Small Batch
#      Release" a "Caperdonich".
#   3. lotti con piu' bottiglie di produttori diversi ("A + B"): "Mixed Lot"

import json as _json
import os as _os

_VOCAB_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "distillerie_vocabolario.json")
try:
    with open(_VOCAB_PATH, encoding="utf-8") as _f:
        _VOCAB = _json.load(_f)  # {nome minuscolo: nome canonico}
except (OSError, ValueError):
    _VOCAB = {}

SPEC_NAMES = ("distillery", "distillery/brand", "brand", "producer", "distiller", "distilleria", "brand/distillery")

_YEARISH = re.compile(r"^(?:'?(?:18|19|20)\d{2}s?'?|\d+(?:yo|y\.o\.|y)?|\d+(?:[.,]\d+)?(?:cl|ml|l|%|proof)|b\.|#\d+)$", re.I)
_AGE_WORDS = {"years", "year", "yo", "y.o."}
_GENERIC_START = {"the", "glen", "old", "royal", "a", "an", "single", "blended", "speyside", "highland",
                  "islay", "lowland", "campbeltown", "island", "scotch", "whisky", "whiskey", "rare", "very"}
_MIXED_WORDS = {"various", "mixed", "assorted"}


def _first_segment(title: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip()
    return t.split(" - ")[0].strip()


def _cut_name(seg: str) -> str:
    """Parole iniziali, prima del primo anno / eta' / numero."""
    out = []
    seg = seg.split(",")[0]
    words = seg.split(" ")
    for i, w in enumerate(words):
        wl = w.lower().strip(",")
        if _YEARISH.match(wl) or wl in _AGE_WORDS:
            break
        if out and re.search(r"\d", wl):  # "Batch 25C", "125.6 Proof", "No.5": dettagli del prodotto
            break
        if wl == "old" and out and out[-1].lower() in _AGE_WORDS:
            break
        out.append(w)
    return " ".join(out).strip(" ,&+")


def canonical_distilleria(name: str) -> Optional[str]:
    """Nome canonico: lista nota, poi vocabolario, poi il nome cosi' com'e'."""
    if not name:
        return None
    n = re.sub(r"\s+", " ", name).strip().strip("'\"").strip()
    if not n or n.lower() in ("unknown", "n/a", "none", "distillery unknown"):
        return None
    low = n.lower()
    if low in KNOWN_DISTILLERIAS:
        return KNOWN_DISTILLERIAS[low]
    if low.startswith("the ") and low[4:] in KNOWN_DISTILLERIAS:
        return KNOWN_DISTILLERIAS[low[4:]]
    if low in _VOCAB:
        return _VOCAB[low]
    return n


def _from_title_segment(seg: str) -> Optional[str]:
    low = seg.lower()
    # Distillerie non dichiarate: "'1898 Speyside Distillery' 2013 12 years old ..."
    m = re.match(r"^'((?:\d{4} )?[^']*distill[^']*)'", seg, re.I)
    if m:
        return f"{m.group(1).strip()} (undisclosed)"
    if low.startswith("distillery unknown"):
        # Catawiki stesso indica la distilleria come sconosciuta/non dichiarata:
        # non e' un errore del parser, quindi non lo lasciamo come "Unknown"
        return "Undisclosed Distillery"
    if low.split(" ")[0] in _MIXED_WORDS:
        return "Mixed Lot"
    # Nomi noti all'inizio del titolo (il piu' lungo vince)
    for key in sorted(KNOWN_DISTILLERIAS, key=len, reverse=True):
        if low == key or low.startswith(key + " ") or low.startswith(key + "'") or low.startswith("the " + key + " "):
            return KNOWN_DISTILLERIAS[key]
    name = _cut_name(seg)
    if not name:
        return None
    # Radice piu' corta presente nel vocabolario ("Caperdonich Small Batch" -> "Caperdonich")
    words = name.split(" ")
    for k in range(1, len(words) + 1):
        pref = " ".join(words[:k]).lower()
        if k == 1 and pref in _GENERIC_START:
            continue
        if pref in _VOCAB:
            return _VOCAB[pref]
    return canonical_distilleria(name)


def _is_recognized(name: str) -> bool:
    low = name.lower()
    return (low in _VOCAB or low in {v.lower() for v in KNOWN_DISTILLERIAS.values()}
            or low.endswith("(undisclosed)"))


def detect_distilleria(title: str, specs: Optional[Dict] = None) -> Optional[str]:
    """Distilleria del lotto. `specs`: scheda del lotto {nome campo: valore}, se disponibile."""
    if specs:
        for k, v in specs.items():
            if str(k).strip().lower() in SPEC_NAMES and v:
                vals = [x.strip() for x in re.split(r",| & | \+ ", str(v)) if x.strip()]
                if len(vals) > 1 and len({(canonical_distilleria(x) or "").lower() for x in vals}) > 1:
                    return "Mixed Lot"
                c = canonical_distilleria(str(v))
                if c:
                    return c
    if not title:
        return None
    seg = _first_segment(title)
    # Lotti con prodotti diversi: "Crown Royal 10yo + Canadian Club 12yo"
    if " + " in seg:
        parts = [x.strip() for x in seg.split(" + ") if x.strip()]
        # contano solo le parti riconosciute (nome noto o nel vocabolario):
        # "Chivas Regal 18yo + Display" e' un lotto Chivas, non misto
        names = [_from_title_segment(x) for x in parts]
        known = {n.lower() for n in names if n and _is_recognized(n)}
        if len(known) > 1:
            return "Mixed Lot"
        if len(known) == 1:
            return next(n for n in names if n and n.lower() in known)
    d = _from_title_segment(seg)
    if d:
        return d
    # Ultimo tentativo: un nome noto in qualunque punto del titolo
    low = title.lower()
    for key in sorted(KNOWN_DISTILLERIAS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", low):
            return KNOWN_DISTILLERIAS[key]
    return None


# ---------------------------------------------------------------------------
# Imbottigliatore (30/09/2026)
# ---------------------------------------------------------------------------
# Gli imbottigliatori indipendenti comprano botti dalle distillerie e le
# imbottigliano con la propria etichetta (es. "Macallan 1990 8 years old -
# Dun Eideann"): la distilleria resta Macallan, l'imbottigliatore e' Dun Eideann.
# Se nessun imbottigliatore indipendente viene riconosciuto il lotto e'
# considerato un imbottigliamento ufficiale ("Original bottling").

ORIGINAL_BOTTLING = "Original bottling"
UNSPECIFIED_INDEPENDENT = "Independent (not specified)"

# nome canonico -> alias cercati nel titolo (parole intere, maiuscole indifferenti)
# Nome canonico = nome esteso (niente sigle: "The Scotch Malt Whisky Society", non "SMWS").
# Le sigle restano solo come alias per riconoscerle nei titoli.
INDEPENDENT_BOTTLERS = {
    "Signatory Vintage": ["signatory vintage", "signatory"],
    "Gordon & MacPhail": ["gordon & macphail", "gordon and macphail", "gordon & mcphail", "connoisseurs choice"],
    "Douglas Laing": ["douglas laing", "xtra old particular", "old particular"],
    "Hunter Laing": ["hunter laing", "old malt cask", "first editions"],
    "Murray McDavid": ["murray mcdavid"],
    "Wilson & Morgan": ["wilson & morgan", "wilson and morgan"],
    "Cadenhead's": ["cadenhead's", "cadenheads", "cadenhead"],
    "Samaroli": ["samaroli"],
    "Duncan Taylor": ["duncan taylor", "rare auld", "whisky galore", "lonach"],
    "The Whisky Agency": ["the whisky agency", "whisky agency"],
    "Moon Import": ["moon import"],
    "Whisky Broker": ["whisky broker", "whiskybroker"],
    "Silver Seal": ["silver seal"],
    "Claxton's": ["claxton's", "claxtons"],
    "Jack Wiebers": ["jack wiebers"],
    "That Boutique-y Whisky Company": ["that boutique-y whisky company", "boutique-y whisky", "boutiquey"],
    "La Maison du Whisky": ["la maison du whisky", "lmdw"],
    "Wealth Solutions": ["wealth solutions"],
    "James Eadie": ["james eadie"],
    "Malts of Scotland": ["malts of scotland"],
    "The Whisky Chamber": ["the whisky chamber", "whisky chamber"],
    "Elixir Distillers": ["elixir distillers", "the single malts of scotland", "single malts of scotland"],
    "High Spirits": ["high spirits"],
    "Scotch Universe": ["scotch universe"],
    "The Scotch Malt Whisky Society": ["the scotch malt whisky society", "scotch malt whisky society", "smws"],
    "Master of Malt": ["master of malt"],
    "Hart Brothers": ["hart brothers", "hart bros"],
    "Sexywhisky": ["sexywhisky", "sexy whisky"],
    "Thompson Brothers": ["thompson brothers", "thompson bros"],
    "Berry Brothers & Rudd": ["berry brothers & rudd", "berry bros", "berry brothers", "berrys' own", "berry's own"],
    "Dun Eideann": ["dun eideann", "dun eidean"],
    "The Cooper's Choice": ["cooper's choice", "coopers choice"],
    "Van Wees": ["van wees"],
    "The Whisky Jury": ["the whisky jury", "whisky jury"],
    "Watt Whisky": ["watt whisky"],
    "Kingsbury": ["kingsbury"],
    "Blackadder": ["blackadder", "raw cask"],
    "Adelphi": ["adelphi"],
    "Maltbarn": ["maltbarn"],
    "Kirsch Whisky": ["kirsch whisky", "kirsch import"],
    "Villa Konthor": ["villa konthor"],
    "A.D. Rattray": ["a.d. rattray", "ad rattray", "a. d. rattray"],
    "Speciality Drinks": ["speciality drinks"],
    "Chieftain's": ["chieftain's", "chieftains"],
    "Mackillop's Choice": ["mackillop's choice", "mackillops choice"],
    "Asta Morris": ["asta morris"],
    "Cask 88": ["cask 88"],
    "Sansibar": ["sansibar"],
    "The Whisky Exchange": ["the whisky exchange"],
    "Valinch & Mallet": ["valinch & mallet", "valinch and mallet"],
    "Càrn Mòr": ["carn mor", "càrn mòr", "morrison & mackay"],
    "North Star Spirits": ["north star spirits", "north star"],
    "Brave New Spirits": ["brave new spirits"],
    "Lady of the Glen": ["lady of the glen"],
    "Whisky Sponge": ["whisky sponge"],
    "Decadent Drinks": ["decadent drinks"],
    "Dramfool": ["dramfool"],
    "Hidden Spirits": ["hidden spirits"],
    "Sestante": ["sestante"],
    "Velier": ["velier"],
    "Intertrade": ["intertrade"],
    "Liquid Treasures": ["liquid treasures"],
    "Kintra": ["kintra"],
    "The Maltman": ["the maltman"],
    "Hepburn's Choice": ["hepburn's choice", "langside"],
    "Chapter 7": ["chapter 7"],
    "Whiskybase": ["whiskybase"],
    "WhiskyNerds": ["whiskynerds", "whisky nerds"],
    "Fadandel": ["fadandel"],
    "Acla Selection": ["acla selection"],
    "Whisky-Fässle": ["whisky-fässle", "whisky fässle", "whisky-fassle"],
    "Spirits Shop' Selection": ["spirits shop' selection", "spirits shop selection"],
    "Old Bothwell": ["old bothwell"],
    "Robert Graham": ["robert graham", "dancing stag"],
    "Best Dram": ["best dram"],
    "Buds & Barrels": ["buds & barrels"],
    "Fakeseal": ["fakeseal"],
    "Svenska Eldvatten": ["svenska eldvatten"],
}
# segmenti del titolo che da soli identificano un imbottigliatore
_EXACT_SEGMENT_BOTTLERS = {"the ultimate": "Van Wees"}
_OFFICIAL_WORDS = ("original bottling", "official bottling", "distillery bottling", "proprietary bottling")
SPEC_BOTTLER_NAMES = ("bottler", "bottled by", "independent bottler", "bottler/brand")

_BOTTLER_ALIASES = sorted(
    ((alias, canon) for canon, aliases in INDEPENDENT_BOTTLERS.items() for alias in aliases),
    key=lambda x: len(x[0]), reverse=True)
_BOTTLER_RE = [(re.compile(r"(?<![\w])" + re.escape(a) + r"(?![\w])", re.I), c) for a, c in _BOTTLER_ALIASES]


def canonical_bottler(name: str) -> Optional[str]:
    if not name:
        return None
    low = name.strip().lower()
    if any(w in low for w in _OFFICIAL_WORDS) or low in ("ob", "official", "original", "distillery"):
        return ORIGINAL_BOTTLING
    for rx, canon in _BOTTLER_RE:
        if rx.search(low):
            return canon
    return name.strip()


def detect_bottler(title: str, specs: Optional[Dict] = None, distilleria: Optional[str] = None) -> str:
    """Imbottigliatore del lotto: indipendente riconosciuto, oppure "Original bottling"."""
    if specs:
        for k, v in specs.items():
            if str(k).strip().lower() in SPEC_BOTTLER_NAMES and v:
                c = canonical_bottler(str(v))
                if c:
                    return c
    t = re.sub(r"\s+", " ", title or "")
    low = t.lower()
    for seg in (s.strip().lower() for s in t.split(" - ")):
        if seg in _EXACT_SEGMENT_BOTTLERS:
            return _EXACT_SEGMENT_BOTTLERS[seg]
    # l'imbottigliatore e' di solito verso la fine del titolo: vince la corrispondenza piu' a destra
    best, best_pos = None, -1
    for rx, canon in _BOTTLER_RE:
        for m in rx.finditer(t):
            if m.start() > best_pos:
                best, best_pos = canon, m.start()
    if best:
        return best
    if any(w in low for w in _OFFICIAL_WORDS):
        return ORIGINAL_BOTTLING
    if distilleria and distilleria.endswith("(undisclosed)"):
        return UNSPECIFIED_INDEPENDENT
    return ORIGINAL_BOTTLING


def detect_stile(title: str) -> str:
    """Detect whisky style"""
    normalized = normalize_text(title)
    
    # Check patterns
    for pattern, stile in STILE_PATTERNS.items():
        if re.search(pattern, normalized):
            return stile
    
    # Default to Single Malt (common on Catawiki) or just Whisky
    return "Single Malt"


def detect_eta(title: str) -> Optional[str]:
    """Extract age (years) or vintage year from title"""
    # 1. Look for "X Years Old"
    age_match = re.search(r'\b(\d{1,2})\s*(?:Years?|Y\.?O\.?|Year Old)\b', title, re.I)
    
    # 2. Look for 4-digit years (Vintage)
    matches = re.findall(r'\b((?:18|19|20)\d{2})\b', title)
    
    if age_match and matches:
        return f"{age_match.group(1)} Years ({matches[-1]})"
    elif age_match:
        return f"{age_match.group(1)} Years"
    elif matches:
        return matches[-1]
        
    return "NV"


def detect_special_edition(title: str) -> Optional[str]:
    """Detect special editions and limited releases"""
    normalized = normalize_text(title)
    
    for keyword, name in SPECIAL_KEYWORDS.items():
        if keyword in normalized:
            return name
    
    return None


def detect_box(title: str) -> bool:
    """Detect if lot includes original box/case"""
    normalized = normalize_text(title)
    # Keywords for original box/case
    box_patterns = [
        r"\boriginal\s*box\b",
        r"\boriginal\s*case\b",
        r"\bovp\b",
        r"\bboxed\b",
        r"\bcon\s*scatola\b",
        r"\bcon\s*box\b",
        r"\bowc\b",  # Original Wood Case
        r"\boc\b",   # Original Case
        r"\bogb\b",  # Original Gift Box
        r"\boriginal\s*packaging\b",
        r"\boriginal\s*carton\b",
        r"\bin\s*box\b",
    ]
    
    for pattern in box_patterns:
        if re.search(pattern, normalized):
            return True
            
    return False


def parse_lot_title(title: str, specs: Optional[Dict] = None) -> Dict:
    """
    Main parsing function
    Returns dict with: distilleria, stile, eta, special, title
    specs: scheda del lotto Catawiki {nome campo: valore}, se disponibile
    """
    if not title or not isinstance(title, str):
        return {
            "distilleria": "Unknown",
            "imbottigliatore": ORIGINAL_BOTTLING,
            "stile": "Single Malt",
            "eta": "NV",
            "special": None,
            "title": str(title) if title else "Unknown"
        }
    
    distilleria = detect_distilleria(title, specs)
    if not distilleria:
        distilleria = "Unknown"
    imbottigliatore = detect_bottler(title, specs, distilleria)
    
    stile = detect_stile(title)
    eta = detect_eta(title)
    special = detect_special_edition(title)
    has_box = detect_box(title)
    
    return {
        "distilleria": distilleria,
        "imbottigliatore": imbottigliatore,
        "stile": stile,
        "eta": eta,
        "special": special,
        "has_box": has_box,
        "title": title.strip()
    }


def parse_titles_batch(titles):
    """Parse multiple titles at once"""
    import pandas as pd
    parsed = [parse_lot_title(t) for t in titles]
    return pd.DataFrame(parsed)
