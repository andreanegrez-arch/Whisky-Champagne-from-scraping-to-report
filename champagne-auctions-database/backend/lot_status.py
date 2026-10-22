"""
lot_status.py - stabilisce se un lotto Catawiki e' APERTO o CHIUSO.

Perche' esiste
--------------
La logica precedente cercava frasi come "final bid", "sold for", "bidding
closed" nel testo di TUTTA la pagina. Catawiki pero' incorpora in ogni pagina
il dizionario completo delle traduzioni dell'interfaccia, che contiene sempre
quelle frasi. Risultato: anche le aste aperte venivano segnate CHIUSE.

Come decide (in ordine di affidabilita')
----------------------------------------
1. lot_state       Stato ufficiale del lotto, scritto da Catawiki nel dataLayer
                   della pagina: "closed" oppure "bidding_started".
   closed          Flag del blocco offerte (__NEXT_DATA__ -> biddingBlockResponse),
                   usato se lot_state manca.
2. Scadenza        Orario di chiusura REALE del lotto (biddingBlockResponse,
                   fino a ~40 min dopo quello dell'asta perche' i lotti chiudono
                   scaglionati), altrimenti BiddingEndTime del dataLayer, confrontato
                   con l'ora attuale in UTC. E' il dato da cui il browser calcola il
                   conto alla rovescia: il tempo scorre solo se e' futuro.
3. Pannello offerte  Solo dentro il riquadro del lotto (mai sull'intera pagina):
                   - timer del conto alla rovescia presente e non a zero -> APERTO
                   - classe "closed" sulla barra di stato, oppure etichetta
                     "Final bid" / "Sold for" / "Winning bid"          -> CHIUSO
                   - etichetta "Current bid" / "Starting bid"          -> APERTO
4. ld+json         availability "OutOfStock" -> CHIUSO.
Se nessun segnale e' disponibile: APERTO. Il lotto viene ricontrollato alla
sessione successiva, quindi un APERTO sbagliato si corregge da solo; un
CHIUSO sbagliato invece congelerebbe un prezzo non definitivo.

Se i segnali sono in disaccordo viene scritto un warning nel log, cosi' ci si
accorge subito se Catawiki cambia la struttura della pagina.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

OPEN = "OPEN"
CLOSED = "CLOSED"

# Tolleranza sulla scadenza: evita di chiudere un lotto per pochi secondi di
# differenza tra l'orologio del PC e quello di Catawiki.
GRACE = timedelta(minutes=5)

_CLOSED_STATES = {"closed", "sold", "unsold", "ended", "finished", "expired",
                  "withdrawn", "cancelled", "canceled"}
_OPEN_STATES = {"bidding_started", "bidding_not_started", "not_started",
                "scheduled", "published", "open", "live", "preview"}

_RE_LOT_STATE = re.compile(r'"lot_state"\s*:\s*"([^"]+)"')
_RE_END_TIME = re.compile(r'"BiddingEndTime"\s*:\s*"([^"]+)"')
_BID_SECTION = '[data-testid="lot-bid-status-section"]'
_COUNTER = '[data-testid="lot-bidding-counter"]'


def _scripts_text(tree):
    """Testo degli <script> che contengono i dati del lotto (dataLayer)."""
    for s in tree.css("script"):
        t = s.text()
        if "lot_state" in t or "BiddingEndTime" in t:
            yield t


def get_lot_state(tree):
    """Valore grezzo di lot_state (es. 'closed', 'bidding_started') o None."""
    for t in _scripts_text(tree):
        m = _RE_LOT_STATE.search(t)
        if m:
            return m.group(1).strip().lower()
    return None


def get_end_time_utc(tree):
    """BiddingEndTime come datetime UTC (timezone-aware) o None."""
    for t in _scripts_text(tree):
        m = _RE_END_TIME.search(t)
        if m:
            raw = m.group(1).strip()
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    return None


def get_bidding_block(tree):
    """
    Blocco offerte del lotto: __NEXT_DATA__ -> props.pageProps.biddingBlockResponse.
    Contiene closed, sold, orario di chiusura reale e storico offerte con il
    paese di ogni offerente. Restituisce {} se assente. Il JSON viene letto una
    sola volta per pagina.
    """
    cached = getattr(tree, "_cw_bidding_block", None)
    if cached is not None:
        return cached
    bb = {}
    node = tree.css_first("script#__NEXT_DATA__")
    if node is not None:
        try:
            data = json.loads(node.text())
            bb = (data.get("props", {}).get("pageProps", {}) or {}).get("biddingBlockResponse") or {}
        except Exception as e:
            logger.debug(f"__NEXT_DATA__ non leggibile: {e}")
    try:
        tree._cw_bidding_block = bb
    except Exception:
        pass
    return bb


def get_real_end_time_utc(tree):
    """Orario di chiusura reale del lotto (UTC) o, in mancanza, BiddingEndTime."""
    bb = get_bidding_block(tree)
    ms = bb.get("biddingEndTime") or ((bb.get("live") or {}).get("lot") or {}).get("biddingEndTime")
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return get_end_time_utc(tree)


def closing_date_str(tree):
    """Data di chiusura come la salvano gli scraper: 'YYYY-MM-DD HH:MM' (UTC) o 'N/A'."""
    end = get_real_end_time_utc(tree)
    return end.strftime("%Y-%m-%d %H:%M") if end else "N/A"


def _closed_from_block(tree):
    bb = get_bidding_block(tree)
    if isinstance(bb.get("closed"), bool):
        return CLOSED if bb["closed"] else OPEN
    cs = str(((bb.get("live") or {}).get("lot") or {}).get("closeStatus") or "").lower()
    if cs == "closed":
        return CLOSED
    if cs == "open":
        return OPEN
    return None


UNKNOWN = "Unknown"


def extract_winner(tree):
    """
    Vincitore del lotto da biddingBlockResponse.

    Restituisce {"nazionalita", "winner_username", "winner_id", "sold"}.
    La nazionalita' viene valorizzata SOLO se il lotto e' chiuso e venduto:
    su un'asta aperta chi guida non e' il vincitore, e su un lotto non venduto
    (riserva non raggiunta) un vincitore non esiste. Negli altri casi: "Unknown".
    - winner_username: numero anonimo che Catawiki mostra ("Bidder 7528")
    - winner_id: token dell'offerente (bidderToken)
    """
    out = {"nazionalita": UNKNOWN, "winner_username": UNKNOWN, "winner_id": UNKNOWN, "sold": False}
    bb = get_bidding_block(tree)
    if not bb:
        return out
    closed = _closed_from_block(tree) == CLOSED
    sold = bb.get("sold") is True
    out["sold"] = bool(closed and sold)
    if not out["sold"]:
        return out
    bids = ((bb.get("biddingHistory") or {}).get("bids")) or []
    if not bids:
        return out
    top_token = bb.get("highestBidderToken") or ((bb.get("live") or {}).get("lot") or {}).get("highestBidderToken")
    win = next((b for b in bids if top_token and b.get("bidderToken") == top_token), None)
    if win is None:
        # Senza token: la prima offerta e' la piu' alta (storico in ordine decrescente)
        win = max(bids, key=lambda b: b.get("localizedBidAmount") or 0)
    code = ((win.get("country") or {}).get("code") or "").strip().upper()
    if code:
        out["nazionalita"] = code
    if win.get("bidderName"):
        out["winner_username"] = f"Bidder {win['bidderName']}"
    if win.get("bidderToken"):
        out["winner_id"] = win["bidderToken"]
    return out


def _status_from_lot_state(state):
    if not state:
        return None
    if state in _CLOSED_STATES:
        return CLOSED
    if state in _OPEN_STATES:
        return OPEN
    # Valore nuovo mai visto: prova a interpretarlo, e segnalalo nel log.
    if re.search(r"clos|end|sold|finish|expir|withdraw|cancel", state):
        guess = CLOSED
    elif re.search(r"bidding|start|open|live|schedul", state):
        guess = OPEN
    else:
        guess = None
    logger.warning(f"lot_state sconosciuto '{state}' -> interpretato come {guess}")
    return guess


def _status_from_panel(tree):
    """Segnali dal solo riquadro del lotto. Restituisce (status, motivo) o (None, None)."""
    counter = tree.css_first(_COUNTER)
    if counter is not None:
        digits = re.sub(r"\D", "", counter.text())
        if digits and set(digits) != {"0"}:
            return OPEN, "timer del conto alla rovescia attivo"

    section = tree.css_first(_BID_SECTION)
    if section is None:
        return None, None
    for node in section.css("[class]"):
        cls = node.attributes.get("class") or ""
        if re.search(r"(?:^|[\s_-])closed(?:$|[\s_-])", cls, re.I):
            return CLOSED, "barra di stato del lotto marcata 'closed'"
    label = section.text(separator=" ", strip=True).lower()
    if any(x in label for x in ("final bid", "winning bid", "sold for", "asta conclusa", "offerta finale")):
        return CLOSED, "etichetta 'Final bid' nel riquadro offerte"
    if any(x in label for x in ("current bid", "starting bid", "offerta attuale", "offerta iniziale")):
        return OPEN, "etichetta 'Current bid' nel riquadro offerte"
    return None, None


def _status_from_ldjson(tree):
    for s in tree.css("script[type='application/ld+json']"):
        try:
            data = json.loads(s.text())
        except Exception:
            continue
        offers = data.get("offers") if isinstance(data, dict) else None
        if isinstance(offers, dict) and "OutOfStock" in str(offers.get("availability", "")):
            return CLOSED
    return None


def detect_lot_status(tree, now=None, url=""):
    """
    Restituisce (status, motivo), con status "OPEN" o "CLOSED".

    tree: documento HTMLParser (html_compat o selectolax).
    now:  ora di riferimento; default ora attuale UTC (usato dai test).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    state = get_lot_state(tree)
    by_state = _status_from_lot_state(state)
    by_block = _closed_from_block(tree)

    end = get_real_end_time_utc(tree)
    by_time = None
    if end is not None:
        by_time = CLOSED if now > end + GRACE else OPEN

    by_panel, panel_reason = _status_from_panel(tree)

    if by_state:
        status, reason = by_state, f"lot_state='{state}'"
    elif by_block:
        status, reason = by_block, f"blocco offerte (closed={by_block == CLOSED})"
    elif by_time:
        status = by_time
        reason = f"scadenza {end:%Y-%m-%d %H:%M} UTC {'passata' if by_time == CLOSED else 'futura'}"
    elif by_panel:
        status, reason = by_panel, panel_reason
    else:
        by_ld = _status_from_ldjson(tree)
        status, reason = (by_ld, "ld+json OutOfStock") if by_ld else (OPEN, "nessun segnale, default APERTO")

    # Diagnostica: segnali in disaccordo. Un lotto aperto oltre la scadenza da
    # meno di un'ora e' normale (chiusura in corso), quindi non lo segnaliamo.
    others = {"blocco offerte": by_block, "scadenza": by_time, "pannello": by_panel}
    for name, val in others.items():
        if val and val != status:
            if name == "scadenza" and status == OPEN and end and now - end < timedelta(hours=1):
                continue
            logger.warning(f"Stato lotto: {reason} -> {status}, ma {name} indica {val} ({url})")

    return status, reason


# ---------------------------------------------------------------------------
# Recupero dati storici (usato dagli scheduler sull'Excel)
# ---------------------------------------------------------------------------

def closed_too_early_mask(df, end_col="Data Chiusura", ts_col="timestamp",
                          status_col="status", local_tz="Europe/Rome"):
    """
    Righe marcate CLOSED ma rilevate PRIMA della scadenza dell'asta: con la
    vecchia logica erano lotti aperti classificati per errore come chiusi, e
    il loro prezzo non e' quello finale.

    end_col: scadenza in UTC ("YYYY-MM-DD HH:MM", come la salvano gli scraper)
    ts_col:  momento della rilevazione, ora locale (datetime.now())
    """
    import pandas as pd

    if df.empty or not {end_col, ts_col, status_col} <= set(df.columns):
        return pd.Series(False, index=df.index)
    end = pd.to_datetime(df[end_col], errors="coerce").dt.tz_localize("UTC")
    ts = pd.to_datetime(df[ts_col], errors="coerce")
    ts = ts.dt.tz_localize(local_tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return (df[status_col] == CLOSED) & end.notna() & ts.notna() & (ts < end - GRACE)


def urls_still_open(df, url_col="url", ts_col="timestamp", status_col="status",
                    end_col="Data Chiusura"):
    """
    URL la cui rilevazione PIU' RECENTE e' OPEN (o chiusa troppo presto):
    sono i lotti da ricontrollare per catturare il prezzo finale.
    """
    import pandas as pd

    if df.empty or not {url_col, status_col} <= set(df.columns):
        return []
    d = df.copy()
    d["_early"] = closed_too_early_mask(d, end_col=end_col, ts_col=ts_col, status_col=status_col)
    if ts_col in d.columns:
        d["_ts"] = pd.to_datetime(d[ts_col], errors="coerce")
        d = d.sort_values("_ts", kind="stable")
    last = d.dropna(subset=[url_col]).drop_duplicates(subset=[url_col], keep="last")
    mask = (last[status_col] == OPEN) | last["_early"]
    return last.loc[mask, url_col].tolist()
