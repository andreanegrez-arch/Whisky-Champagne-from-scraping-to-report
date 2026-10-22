r"""
Pulizia della colonna `distilleria` dei lotti whisky, usata da export_powerbi.py.

Lo scraper, quando su Catawiki non trova il campo "Distilleria", ci mette il nome
del lotto (es. "Glen Garioch 2013 12 years old The Nectar of the Daily Drams").
Qui lo riportiamo al solo nome della distilleria, in quest'ordine:

1. mappa_distillerie.csv (stessa cartella): tabella originale -> distilleria,
   modificabile anche a mano in Excel. Ha la precedenza su tutto il resto.
2. Lotti con piu' whisky ("A + B", oppure "X 12 years old & Y 1979") -> "Mixed Lot".
3. "1885 Lowland Distillery (undisclosed)" e simili -> "Undisclosed Distillery".
4. Il nome inizia con una distilleria gia' nota -> quella distilleria
   (es. "Cragganmore 1993 10 years old ..." -> "Cragganmore").
5. Altrimenti si taglia via eta', anno e parole come Single, Cask, Edition.

I valori gia' puliti (senza numeri, '+' o parole tipiche del nome del lotto)
restano come sono, salvo che siano nella mappa.
Usa solo la libreria standard.
"""

import csv
import re
from pathlib import Path

MAPPA_PATH = Path(__file__).with_name("mappa_distillerie.csv")

MIXED = "Mixed Lot"
UNDISCLOSED = "Undisclosed Distillery"
SPECIALI = {MIXED, UNDISCLOSED, "Merchandise", ""}

SPORCO_RE = re.compile(r"\+|\d|single|cask|blend|malt|edition|release|bourbon|sherry", re.I)
UNDISCLOSED_RE = re.compile(r"^\d{4} .*Distillery", re.I)
MISTO_RE = re.compile(r"\d.*\s&\s.*\d")
TAGLIO_RE = re.compile(
    r"\s(?=(?:\d+\w*|no\.|single|cask|pure|straight|blended|malt|triple|special|limited|rare|"
    r"edition|batch|series|selection|reserve|collection|mizunara|master\w*|the|–|-)(?:\s|$))",
    re.I)
GENERICI = {"whisky", "single", "blended"}


def sporco(v):
    return bool(SPORCO_RE.search(v)) or len(v) > 25


def carica_mappa(path=MAPPA_PATH):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["originale"]: r["distilleria"] for r in csv.DictReader(f) if r.get("originale")}


def _senza_the(x):
    return x[4:] if x.startswith("the ") else x


class Pulitore:
    def __init__(self, valori, mappa=None):
        self.mappa = carica_mappa() if mappa is None else mappa
        noti = {v for v in valori if v and not sporco(v)} | set(self.mappa.values())
        noti -= SPECIALI
        # i piu' lunghi prima: "Glen Grant" vince su "Glen"
        self.noti = sorted(((n, n.lower()) for n in noti), key=lambda t: len(t[0]), reverse=True)
        self.cache = {}

    def _trova(self, v):
        vl = v.lower()
        for cand in (vl, _senza_the(vl), "the " + vl):
            for n, nl in self.noti:
                if cand == nl or cand.startswith(nl + " ") or cand.startswith(nl + "'"):
                    return n
                ns = _senza_the(nl)
                if len(ns) > 3 and (cand == ns or cand.startswith(ns + " ")):
                    return n
        return None

    def _calcola(self, v):
        if v in self.mappa:
            return self.mappa[v]
        if not v or not sporco(v):
            return v
        if "+" in v or MISTO_RE.search(v):
            return MIXED
        if UNDISCLOSED_RE.match(v):
            return UNDISCLOSED
        trovato = self._trova(v)
        if trovato:
            return self.mappa.get(trovato, trovato)
        corto = TAGLIO_RE.split(v, maxsplit=1)[0].strip(" –-&")
        if not corto or corto.lower() in GENERICI:
            return v
        return self.mappa.get(corto, corto)

    def __call__(self, v):
        v = "" if v is None else str(v)
        if v not in self.cache:
            self.cache[v] = self._calcola(v)
        return self.cache[v]
