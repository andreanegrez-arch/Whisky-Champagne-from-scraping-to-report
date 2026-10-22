"""
scrape_lock.py - segnala quando una sessione di scraping e' in corso.

Backend e scheduler creano un file ".scraping-<nome>.lock" nella cartella del
progetto mentre girano, e lo cancellano alla fine. Lo script di recupero
(backfill_nazionalita.py) lo controlla e si mette in pausa, cosi' non si
sommano le richieste verso Catawiki.

Un file piu' vecchio di STALE_HOURS viene ignorato: serve se una sessione si
e' interrotta di colpo (PC spento, finestra chiusa) senza cancellarlo.
"""

import glob
import json
import os
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STALE_HOURS = 12


def _path(name):
    return os.path.join(PROJECT_DIR, f".scraping-{name}.lock")


def acquire(name):
    try:
        with open(_path(name), "w", encoding="utf-8") as f:
            json.dump({"name": name, "pid": os.getpid(), "started": time.time()}, f)
    except OSError:
        pass


def release(name):
    try:
        os.remove(_path(name))
    except OSError:
        pass


def running_sessions():
    """Nomi delle sessioni di scraping attive (lock recenti)."""
    active = []
    for p in glob.glob(os.path.join(PROJECT_DIR, ".scraping-*.lock")):
        try:
            if time.time() - os.path.getmtime(p) < STALE_HOURS * 3600:
                active.append(os.path.basename(p)[len(".scraping-"):-len(".lock")])
        except OSError:
            pass
    return active
