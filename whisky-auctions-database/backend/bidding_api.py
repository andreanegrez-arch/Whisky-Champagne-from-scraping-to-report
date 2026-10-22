"""
bidding_api.py - esito ufficiale delle aste dall'API di Catawiki (11/10/2026).

E' la stessa API che usa la pagina del lotto per disegnare il riquadro offerte:
    https://www.catawiki.com/buyer/api/v3/bidding/lots?ids=ID1,ID2,...   (fino a 100 id)
Per ogni lotto restituisce, anche per i lotti vecchi ormai archiviati:
    current_bid_amount.EUR   offerta massima (o corrente, se l'asta e' aperta)
    closed                   asta chiusa
    winner_token             presente solo se il lotto e' stato VENDUTO
    reserve_price_met        riserva raggiunta (None = senza riserva)
    bidding_end_time         chiusura reale del lotto (UTC)

Perche' serve: la pagina del lotto non basta.
  - Lotti chiusi non venduti: la pagina mostra solo la STIMA ("Estimate EUR 1,000 -
    EUR 1,200") e gli scraper la salvavano come prezzo finale.
  - Lotti vecchi: la pagina reindirizza alla categoria (lotto archiviato) oppure
    al NUOVO lotto con cui il venditore ha rimesso all'asta la bottiglia; lo scraper
    seguiva il reindirizzamento e scriveva sul lotto vecchio i dati di quello nuovo.
  - Lotti rimasti OPEN nel database dopo la chiusura: il prezzo era l'offerta di
    quando erano stati visti l'ultima volta, non quella finale.
L'API risponde per id del lotto, quindi niente di tutto questo puo' succedere.
"""

import logging
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

API_URL = "https://www.catawiki.com/buyer/api/v3/bidding/lots?ids="
# Lotti per richiesta: provato il 11/10/2026, 500 id funzionano (URL ~5 KB),
# 1000 no (HTTP 400, URL troppo lungo). Se una richiesta da' 400 il gruppo viene
# diviso a meta' automaticamente.
CHUNK = 500

VENDUTO = "venduto"
INVENDUTO = "invenduto"
IN_CORSO = "in corso"
NON_VERIFICABILE = "non verificabile"

_RE_ID = re.compile(r"/l/(\d+)")


def lot_id(url):
    m = _RE_ID.search(url or "")
    return int(m.group(1)) if m else None


def _end_str(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def interpreta(info):
    """
    Dati di un lotto dall'API -> dict con:
      esito          venduto / invenduto / in corso
      status         CLOSED / OPEN (stessi valori di prima)
      offerta_massima  offerta piu' alta (float) o None se nessuna offerta
      prezzo_finale  prezzo di aggiudicazione se venduto, offerta corrente se in
                     corso, None se invenduto (l'offerta massima NON e' un prezzo
                     di vendita: resta in offerta_massima)
      data_chiusura  'YYYY-MM-DD HH:MM' UTC (stesso formato degli scraper)
    """
    amt = (info.get("current_bid_amount") or {}).get("EUR")
    offerta = float(amt) if isinstance(amt, (int, float)) and amt > 0 else None
    closed = info.get("closed") is True
    if closed:
        esito = VENDUTO if info.get("winner_token") else INVENDUTO
    else:
        esito = IN_CORSO
    return {
        "esito": esito,
        "status": "CLOSED" if closed else "OPEN",
        "offerta_massima": offerta,
        "prezzo_finale": offerta if esito in (VENDUTO, IN_CORSO) else None,
        "data_chiusura": _end_str(info.get("bidding_end_time")),
        "reserve_price_met": info.get("reserve_price_met"),
    }


def _chunks(ids):
    ids = [i for i in dict.fromkeys(ids) if i]
    for k in range(0, len(ids), CHUNK):
        yield ids[k:k + CHUNK]


def _parse(resp_json):
    out = {}
    for lot in (resp_json or {}).get("lots") or []:
        if isinstance(lot, dict) and lot.get("id"):
            out[int(lot["id"])] = lot
    return out


def piano(ids):
    """Quanti lotti diversi e quante richieste servono (per mostrarlo prima di partire)."""
    unici = [i for i in dict.fromkeys(ids) if i]
    return len(unici), (len(unici) + CHUNK - 1) // CHUNK


def fetch_sync(session, ids, pausa=0.5, tentativi=3):
    """session: curl_cffi.requests.Session (o requests). Restituisce {id: info grezza}."""
    risultati = {}
    coda = list(_chunks(ids))
    while coda:
        gruppo = coda.pop(0)
        url = API_URL + ",".join(str(i) for i in gruppo)
        for t in range(tentativi):
            try:
                r = session.get(url, timeout=30)
                if r.status_code == 200:
                    risultati.update(_parse(r.json()))
                    break
                if r.status_code in (400, 414) and len(gruppo) > 1:
                    meta = len(gruppo) // 2
                    coda[:0] = [gruppo[:meta], gruppo[meta:]]
                    break
                logger.warning(f"API offerte: HTTP {r.status_code} (tentativo {t + 1})")
            except Exception as e:
                logger.warning(f"API offerte: {e} (tentativo {t + 1})")
            time.sleep(2 * (t + 1))
        time.sleep(pausa)
    return risultati


async def fetch_async(session, ids, pausa=0.5, tentativi=3):
    """session: curl_cffi.requests.AsyncSession. Restituisce {id: info grezza}."""
    import asyncio
    risultati = {}
    coda = list(_chunks(ids))
    while coda:
        gruppo = coda.pop(0)
        url = API_URL + ",".join(str(i) for i in gruppo)
        for t in range(tentativi):
            try:
                r = await session.get(url, timeout=30)
                if r.status_code == 200:
                    risultati.update(_parse(r.json()))
                    break
                if r.status_code in (400, 414) and len(gruppo) > 1:
                    meta = len(gruppo) // 2
                    coda[:0] = [gruppo[:meta], gruppo[meta:]]
                    break
                logger.warning(f"API offerte: HTTP {r.status_code} (tentativo {t + 1})")
            except Exception as e:
                logger.warning(f"API offerte: {e} (tentativo {t + 1})")
            await asyncio.sleep(2 * (t + 1))
        await asyncio.sleep(pausa)
    return risultati


_RE_PAGE_LOT_ID = re.compile(r'"lot_id"\s*:\s*(\d+)')


def stesso_lotto(url, html, final_url=None):
    """
    False se la pagina scaricata e' di un ALTRO lotto (reindirizzamento a un lotto
    rimesso all'asta o alla pagina della categoria): in quel caso i dati della
    pagina non vanno scritti sul lotto dell'url.
    """
    atteso = lot_id(url)
    if atteso is None:
        return True
    if final_url and "/l/" not in str(final_url):
        return False
    if final_url and lot_id(str(final_url)) not in (None, atteso):
        return False
    m = _RE_PAGE_LOT_ID.search(html or "")
    if m and int(m.group(1)) != atteso:
        return False
    return True


def da_pagina(tree):
    """
    Stessi dati di interpreta(), letti dal blocco offerte incorporato nella pagina
    del lotto (__NEXT_DATA__ -> biddingBlockResponse). Serve solo se l'API non
    risponde. None se la pagina non contiene il blocco offerte.
    Non usa MAI i numeri scritti nel riquadro offerte (c'e' anche la stima).
    """
    try:
        from lot_status import get_bidding_block
    except Exception:
        return None
    bb = get_bidding_block(tree) or {}
    if not bb or not isinstance(bb.get("closed"), bool):
        return None
    live = ((bb.get("live") or {}).get("lot") or {})
    end_ms = bb.get("biddingEndTime") or live.get("biddingEndTime")
    end = None
    if isinstance(end_ms, (int, float)) and end_ms > 0:
        end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).isoformat()
    info = {
        "closed": bb["closed"],
        "current_bid_amount": {"EUR": bb.get("localizedCurrentBidAmount")},
        # sold=True solo per i lotti chiusi e venduti
        "winner_token": "pagina" if (bb["closed"] and bb.get("sold") is True) else None,
        "reserve_price_met": bb.get("reservePriceMet"),
        "bidding_end_time": end,
    }
    return interpreta(info)
