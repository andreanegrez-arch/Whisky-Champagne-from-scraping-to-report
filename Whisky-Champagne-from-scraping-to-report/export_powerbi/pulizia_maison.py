r"""
Pulizia della colonna `maison` dei lotti champagne, usata da export_powerbi.py.

Il database non viene modificato: la correzione avviene solo nei CSV.
Ordine delle regole (la prima che si applica vince):

1. maison_da_verificare.csv: se nella colonna `maison_corretta` hai scritto un
   nome, vale quello (sono i casi che Andrea controlla a mano).
2. mappa_maison.csv (colonne originale,maison,tipologia,regola): correzioni
   puntuali. Modificabile in Excel; per aggiungere una correzione basta una riga
   nuova. Se `tipologia` e' compilata, sostituisce anche la tipologia del lotto
   (es. Giulio Ferrari -> maison "Fratelli Lunelli", tipologia "Trento DOC").
3. Regole automatiche, per i nomi nuovi che lo scraper trovera' in futuro:
   - "Accessori/Non-bottiglia" con tipologia "Items": bicchieri, vassoi, libri...
   - "Lotto misto": piu' produttori nello stesso campo (virgole, "+", "x2")
   - titolo intero al posto della maison: si tiene la parte prima di " - "
   - prefisso "Champagne"/"Maison" tolto se il resto e' una maison nota
   - stesso nome con accenti/maiuscole/trattini diversi -> forma piu' usata
   - nome di cuvee attaccato a una maison nota -> solo la maison
   - tutto minuscolo / tutto maiuscolo -> iniziali maiuscole
Valori che export_powerbi.py ESCLUDE dal CSV (record eliminati):
   "Lotto misto" e "(elimina)" (champagne commerciali senza produttore).
Usa solo la libreria standard.
"""

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
MAPPA_PATH = CARTELLA / "mappa_maison.csv"
VERIFICA_PATH = CARTELLA / "maison_da_verificare.csv"

LOTTO_MISTO = "Lotto misto"
ACCESSORI = "Accessori/Non-bottiglia"
TIPOLOGIA_ACCESSORI = "Items"
ELIMINA = "(elimina)"
DA_ESCLUDERE = {LOTTO_MISTO, ELIMINA}

ACCESSORI_RE = re.compile(
    r"(?i)\b(glass(es)?|flutes?|tray|bucket|cooler|candle\w*|bowl|wall art|stopper|"
    r"opener|sabre|saber|lamp|mirror|ice bucket|drinking dom|led)\b|non-bottiglia")
MISTO_RE = re.compile(r",|;|\+|\bx\d\b|\b\d+ x\b|\bmix(ed)?\b", re.I)
TITOLO_RE = re.compile(r"\s[-–]\s.*(champagne|aoc|bottle|magnum|reims|\(\d)", re.I)
PREFISSO_RE = re.compile(r"(?i)^(champagne|maison)\s+")

# Controllo sul TITOLO del lotto (rivedi_lotto):
# - BOTTIGLIA_RE: il titolo dichiara bottiglie con il volume, come fa Catawiki
#   ("1 Bottle (0.75L)", "2 Magnum (1.5L)", "1 Belshazzar (12.0L)").
# - OGGETTO_RE: categorie Catawiki di oggetti che non sono bottiglie
#   (secchielli, bicchieri, accessori, libri, lampade...).
BOTTIGLIA_RE = re.compile(
    r"(?i)\b(bottles?|magnums?|jeroboams?|rehoboams?|methuselahs?|mathusalems?|"
    r"salmanazars?|balthazars?|belshazzars?|nebuchadnezzars?)\s*\(\s*[\d.,]+\s*l\)")
OGGETTO_RE = re.compile(
    r"(?i)champagne cooler|ice bucket|champagne bucket|wine accessory|champagne glass|"
    r"champagne flute|candle\w*|wall art|drinking dom|serving tray|menu holder|"
    r"paperweight|\bbowl\b|\bstopper\b")
TIPOLOGIA_GENERICA = "Items"
TIPOLOGIA_NON_SPECIFICATA = "Non specificata"
NON_BOTTIGLIA = "(non bottiglia)"


def tipologia_da_titolo(titolo):
    """'... - Champagne Blanc de Blancs - 2 Magnum (1.5L)' -> 'Blanc de Blancs'."""
    m = re.search(r"(?i)-\s*champagne\b([^-]*)", titolo or "")
    # prima la categoria scritta dopo "- Champagne", poi tutto il titolo
    for parte in ((m.group(1) if m else ""), titolo or ""):
        parte = parte.lower()
        if re.search(r"\bros[ée]", parte):
            return "Brut Rosé"
        if "blanc de blancs" in parte:
            return "Blanc de Blancs"
        if re.search(r"extra brut|brut nature|pas dos|z[eé]ro dos|non dos", parte):
            return "Extra Brut"
        if re.search(r"demi|ice imp", parte):
            return "Demi-Sec"
        if re.search(r"\bbrut\b", parte):
            return "Brut"
    return TIPOLOGIA_NON_SPECIFICATA
SPAZI_RE = re.compile(r"\s+")


def chiave(s):
    """Forma di confronto: senza accenti, minuscola, solo lettere e cifre."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(et|and)\b", "&", s)
    return re.sub(r"[^a-z0-9&]", "", s)


def _leggi_csv(path, col_da, col_a):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r[col_da]: r[col_a].strip() for r in csv.DictReader(f)
                if r.get(col_da) is not None and (r.get(col_a) or "").strip()}


def carica_mappa():
    return _leggi_csv(MAPPA_PATH, "originale", "maison")


def carica_tipologie():
    return _leggi_csv(MAPPA_PATH, "originale", "tipologia")


def carica_verifiche():
    """originale -> maison_corretta. Le righe ancora da decidere (maison_corretta
    vuota) restano nel dizionario con valore "" e il nome esce com'e'."""
    if not VERIFICA_PATH.exists():
        return {}
    with open(VERIFICA_PATH, encoding="utf-8-sig", newline="") as f:
        return {r["originale"]: (r.get("maison_corretta") or "").strip()
                for r in csv.DictReader(f) if r.get("originale")}


class PulitoreMaison:
    def __init__(self, valori, mappa=None, verifiche=None):
        self.mappa = carica_mappa() if mappa is None else mappa
        self.verifiche = carica_verifiche() if verifiche is None else verifiche
        self.tipologie = carica_tipologie() if mappa is None else {}
        conta = Counter(SPAZI_RE.sub(" ", v).strip() for v in valori if v)
        # maison "note": nomi puliti usati in almeno 3 lotti, piu' le destinazioni della mappa
        noti = Counter()
        for v, n in conta.items():
            if n >= 3 and not (MISTO_RE.search(v) or TITOLO_RE.search(v) or ACCESSORI_RE.search(v)
                               or v.islower() or v.isupper() or PREFISSO_RE.match(v)):
                noti[v] += n
        for v in set(self.mappa.values()) | {x for x in self.verifiche.values() if x}:
            noti[v] += 1000  # le scelte fatte a mano vincono sulle varianti
        noti.pop(LOTTO_MISTO, None)
        noti.pop(ACCESSORI, None)
        noti.pop(ELIMINA, None)
        # per ogni chiave, la forma piu' usata
        self.canonico = {}
        for v, _ in noti.most_common():
            self.canonico.setdefault(chiave(v), v)
        # chiavi lunghe prima: "Pierre de Charme" prima di "Pierre"
        self.prefissi = sorted(((k, v) for k, v in self.canonico.items() if len(k) >= 5),
                               key=lambda t: len(t[0]), reverse=True)
        self.cache = {}

    def _nota(self, v):
        return self.canonico.get(chiave(v))

    def _prefisso_noto(self, v):
        k = chiave(v)
        for pk, nome in self.prefissi:
            if k.startswith(pk) and len(k) > len(pk):
                return nome
        return None

    def _calcola(self, v):
        if v in self.verifiche:
            return self.verifiche[v] or v  # non ancora deciso: resta com'e'
        if v in self.mappa:
            return self.mappa[v]
        if not v:
            return v
        if ACCESSORI_RE.search(v):
            return ACCESSORI
        if MISTO_RE.search(v.rstrip(" ,;")):
            return LOTTO_MISTO
        v = v.rstrip(" ,;.")
        if TITOLO_RE.search(v):
            v = re.split(r"\s[-–]\s", v, maxsplit=1)[0].strip()
        senza = PREFISSO_RE.sub("", v)
        for cand in (v, senza):
            nota = self._nota(cand)
            if nota:
                return nota
        for cand in (v, senza):
            nota = self._prefisso_noto(cand)
            if nota:
                return nota
        if v.islower() or (v.isupper() and len(v) > 4):
            return v.title()
        return v

    def __call__(self, v):
        v = "" if v is None else SPAZI_RE.sub(" ", str(v)).strip()
        if v not in self.cache:
            self.cache[v] = self._calcola(v)
        return self.cache[v]

    def tipologia(self, originale, tipologia_attuale):
        """Tipologia da scrivere nel CSV per un lotto con questa maison originale."""
        v = "" if originale is None else SPAZI_RE.sub(" ", str(originale)).strip()
        if v in self.tipologie:
            return self.tipologie[v]
        if self(v) == ACCESSORI:
            return TIPOLOGIA_ACCESSORI
        return tipologia_attuale

    def escludi(self, maison_pulita):
        """True se il lotto va tolto dal CSV (lotto misto o senza produttore)."""
        return maison_pulita in DA_ESCLUDERE

    def maison_da_titolo(self, titolo):
        """Maison letta dal titolo: '2015 Louis Roederer Cristal Con Astuccio - ...'
        -> 'Louis Roederer'. Toglie l'annata iniziale e tiene la parte prima di ' - ' o ','."""
        t = re.sub(r"^\s*\d{4}\s+", "", titolo or "")
        t = re.split(r"\s[-–]\s|,", t, maxsplit=1)[0].strip()
        nuova = self(t)
        return nuova if nuova and nuova not in (ACCESSORI, LOTTO_MISTO, ELIMINA) else None

    def rivedi_lotto(self, r):
        """Controllo sul titolo, dopo la pulizia della maison. Modifica r e
        restituisce None se il lotto resta, oppure il motivo dell'esclusione.
        - oggetto che non e' una bottiglia (secchielli, bicchieri, libri...) -> escluso
        - maison 'Accessori' ma il titolo e' una bottiglia -> maison presa dal titolo
        - tipologia 'Items' su una bottiglia -> tipologia presa dal titolo
        - tipologia che non si ricava nemmeno dal titolo -> escluso"""
        titolo = r.get("title") or ""
        bottiglia = bool(BOTTIGLIA_RE.search(titolo))
        if not bottiglia and (OGGETTO_RE.search(titolo) or r.get("maison") == ACCESSORI):
            return NON_BOTTIGLIA
        if r.get("maison") == ACCESSORI:
            nuova = self.maison_da_titolo(titolo)
            if nuova is None:
                return NON_BOTTIGLIA
            r["maison"] = nuova
            if r.get("tipologia") in (TIPOLOGIA_ACCESSORI, TIPOLOGIA_GENERICA, None, ""):
                r["tipologia"] = tipologia_da_titolo(titolo)
        if r.get("tipologia") in (TIPOLOGIA_GENERICA, TIPOLOGIA_ACCESSORI):
            r["tipologia"] = tipologia_da_titolo(titolo)
        if r.get("tipologia") == TIPOLOGIA_NON_SPECIFICATA:
            return TIPOLOGIA_NON_SPECIFICATA.lower()  # tipologia non ricavabile: fuori dal CSV
        return None
