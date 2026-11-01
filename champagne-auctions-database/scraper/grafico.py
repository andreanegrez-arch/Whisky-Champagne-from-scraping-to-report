"""
grafico.py - grafico cronologico dei prezzi di una bottiglia, in PNG (01/11/2026).

Usato dal comando Telegram /grafico. Usa matplotlib se e' installato e si
carica (02/11/2026); altrimenti ripiega su un disegno in Python puro (solo zlib
e struct della libreria standard), utile se Smart App Control blocca le DLL di
matplotlib come era successo con selectolax.

Cosa disegna:
  - un punto per ogni lotto venduto (prezzo per bottiglia, alla data di chiusura)
  - la media mobile su una finestra di giorni (linea), adattata alla durata dello storico
  - la media di tutto lo storico (linea tratteggiata)
  - l'ultima vendita evidenziata in arancione

Lo stesso file esiste identico nei progetti champagne e whisky.
"""
import struct
import unicodedata
import zlib
from datetime import datetime

# ------------------------------------------------------------------ stile
W, H = 1200, 720
SFONDO = (255, 255, 255)
TESTO = (40, 44, 52)
TESTO_SOFT = (110, 116, 128)
GRIGLIA = (230, 232, 236)
ASSE = (180, 184, 192)
PUNTI = (120, 160, 210)        # vendite
LINEA = (31, 78, 140)          # media mobile
MEDIA = (150, 150, 150)        # media complessiva
ULTIMO = (230, 120, 20)        # ultima vendita

# Media mobile: finestra in giorni = durata dello storico / 12, tra 14 e 90 giorni
FINESTRA_MIN, FINESTRA_MAX = 14, 90

# Margini dell'area del grafico
ML, MR, MT, MB = 110, 40, 110, 80

# ------------------------------------------------------------------ font 5x7
# Ogni carattere: 7 righe da 5 colonne ('#' = pixel acceso)
_GLIFI = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .#### #.... #.... #.... #.... #.... .####
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .#### #.... #.... #.### #...# #...# .###.
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. ...#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# ##..# #.#.# #..## #...# #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ####. ....# ....# .###. ....# ....# ####.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 .###. #.... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ....# .###.
. ..... ..... ..... ..... ..... .##.. .##..
, ..... ..... ..... ..... .##.. .##.. .#...
- ..... ..... ..... ##### ..... ..... .....
+ ..... ..#.. ..#.. ##### ..#.. ..#.. .....
/ ....# ....# ...#. ..#.. .#... #.... #....
: ..... .##.. .##.. ..... .##.. .##.. .....
% ##..# ##..# ...#. ..#.. .#... #..## #..##
( ...#. ..#.. .#... .#... .#... ..#.. ...#.
) .#... ..#.. ...#. ...#. ...#. ..#.. .#...
| ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
\u20ac ..### .#... ####. .#... ####. .#... ..###
' ..#.. ..#.. ..... ..... ..... ..... .....
& .##.. #..#. #.#.. .#... #.#.# #..#. .##.#
? .###. #...# ....# ...#. ..#.. ..... ..#..
* ..... #.#.# .###. ##### .###. #.#.# .....
= ..... ..... ##### ..... ##### ..... .....
< ...#. ..#.. .#... #.... .#... ..#.. ...#.
> .#... ..#.. ...#. ....# ...#. ..#.. .#...
_ ..... ..... ..... ..... ..... ..... #####
"""
FONT = {" ": "." * 35}
for _r in _GLIFI.strip().splitlines():
    _c, *_righe = _r.split(" ")
    FONT[_c.encode().decode("unicode_escape") if _c.startswith("\\") else _c] = "".join(_righe)


def _ascii(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo))
    return "".join(c for c in t if not unicodedata.combining(c) or c == "€").upper()


class Tela:
    """Buffer RGB semplice con le primitive di disegno che servono."""

    def __init__(self, w, h, sfondo):
        self.w, self.h = w, h
        self.px = bytearray(bytes(sfondo) * (w * h))

    def punto(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def rett(self, x0, y0, x1, y1, c):
        x0, x1 = max(0, int(min(x0, x1))), min(self.w, int(max(x0, x1)))
        y0, y1 = max(0, int(min(y0, y1))), min(self.h, int(max(y0, y1)))
        riga = bytes(c) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(riga)] = riga

    def disco(self, cx, cy, r, c):
        cx, cy = int(round(cx)), int(round(cy))
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self.rett(cx - dx, cy + dy, cx + dx + 1, cy + dy + 1, c)

    def linea(self, x0, y0, x1, y1, c, spessore=1, tratteggio=0):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) or 1
        r = spessore // 2
        for k in range(n + 1):
            if tratteggio and (k // tratteggio) % 2:
                continue
            x = x0 + (x1 - x0) * k / n
            y = y0 + (y1 - y0) * k / n
            if spessore <= 1:
                self.punto(int(round(x)), int(round(y)), c)
            else:
                self.rett(x - r, y - r, x - r + spessore, y - r + spessore, c)

    def testo(self, x, y, s, c, scala=2, allinea="sx"):
        s = _ascii(s)
        larg = len(s) * 6 * scala - scala
        if allinea == "dx":
            x -= larg
        elif allinea == "centro":
            x -= larg // 2
        for ch in s:
            g = FONT.get(ch, FONT["?"])
            for i, bit in enumerate(g):
                if bit == "#":
                    gx, gy = i % 5, i // 5
                    self.rett(x + gx * scala, y + gy * scala,
                              x + (gx + 1) * scala, y + (gy + 1) * scala, c)
            x += 6 * scala
        return larg

    def png(self) -> bytes:
        raw = bytearray()
        riga = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * riga:(y + 1) * riga]

        def chunk(tipo, dati):
            return (struct.pack(">I", len(dati)) + tipo + dati
                    + struct.pack(">I", zlib.crc32(tipo + dati) & 0xFFFFFFFF))

        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


# ------------------------------------------------------------------ scale degli assi

def _passo_tondo(intervallo, n=5):
    if intervallo <= 0:
        return 1
    grezzo = intervallo / n
    esp = 10 ** len(str(int(grezzo))) / 10 if grezzo >= 1 else 10 ** -2
    for m in (1, 2, 2.5, 5, 10):
        if grezzo <= m * esp:
            return m * esp
    return 10 * esp


def _euro_breve(v):
    if v >= 10000:
        return f"{v / 1000:.0f}K €"
    if v >= 1000:
        return f"{v / 1000:.1f}K €".replace(".", ",")
    return f"{v:.0f} €"


def _mesi_tra(d0, d1):
    return (d1.year - d0.year) * 12 + d1.month - d0.month


def _tick_date(d0, d1):
    """Date delle etichette sull'asse x: mesi (o giorni se lo storico e' corto)."""
    from datetime import timedelta
    giorni = (d1 - d0).days
    if giorni <= 45:
        passo = max(1, giorni // 6 or 1)
        out, d = [], datetime(d0.year, d0.month, d0.day)
        while d <= d1:
            out.append((d, d.strftime("%d/%m")))
            d += timedelta(days=passo)
        return out
    mesi = _mesi_tra(d0, d1)
    passo = next(p for p in (1, 2, 3, 6, 12, 24, 60) if mesi / p <= 7)
    out = []
    y, m = d0.year, d0.month + 1
    if m > 12:
        y, m = y + 1, 1
    while (y, m) <= (d1.year, d1.month):
        if (m - 1) % passo == 0:
            out.append((datetime(y, m, 1), f"{m:02d}/{str(y)[2:]}"))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ------------------------------------------------------------------ grafico

def _disegna_puro(ris: dict) -> bytes:
    """Versione in Python puro (riserva se matplotlib non si carica)."""
    storico = ris["storico"]
    date = [datetime.strptime(v["data"][:16], "%Y-%m-%d %H:%M") for v in storico]
    prezzi = [v["prezzo_bott"] for v in storico]

    t = Tela(W, H, SFONDO)
    x0, x1, y0, y1 = ML, W - MR, MT, H - MB

    # --- titolo e sottotitolo
    titolo = "  -  ".join(str(x) for x in ris["richiesta"] if str(x).strip() not in ("", "*"))
    t.testo(ML, 24, titolo[:60], TESTO, scala=3)
    sotto = (f"{ris['vendite']} {'vendita' if ris['vendite'] == 1 else 'vendite'}  -  media {_euro_breve(ris['media'])}  -  "
             f"prezzo per bottiglia, lotti venduti")
    t.testo(ML, 60, sotto, TESTO_SOFT, scala=2)

    # --- scala y (parte da 0 se i prezzi sono vicini a 0, altrimenti dal minimo arrotondato)
    pmin, pmax = min(prezzi), max(prezzi)
    if pmax == pmin:
        pmin, pmax = pmin * 0.8, pmax * 1.2 or 1
    passo = _passo_tondo(pmax - pmin)
    ymin = max(0, (pmin // passo) * passo)
    ymax = (pmax // passo + 1) * passo
    if ymin < passo:
        ymin = 0

    def Y(p):
        return y1 - (p - ymin) / (ymax - ymin) * (y1 - y0)

    # --- scala x (con un po' di margine ai lati)
    t0, t1 = min(date), max(date)
    span = (t1 - t0).total_seconds() or 86400 * 30
    pad = span * 0.03
    tmin, tmax = t0.timestamp() - pad, t1.timestamp() + pad

    def X(d):
        return x0 + (d.timestamp() - tmin) / (tmax - tmin) * (x1 - x0)

    # --- griglia ed etichette y
    v = ymin
    while v <= ymax + 1e-9:
        yy = int(round(Y(v)))
        t.linea(x0, yy, x1, yy, GRIGLIA)
        t.testo(x0 - 12, yy - 7, _euro_breve(v), TESTO_SOFT, scala=2, allinea="dx")
        v += passo

    # --- etichette x
    for d, et in _tick_date(t0, t1):
        if tmin <= d.timestamp() <= tmax:
            xx = int(round(X(d)))
            t.linea(xx, y1, xx, y1 + 6, ASSE)
            t.testo(xx, y1 + 14, et, TESTO_SOFT, scala=2, allinea="centro")
    t.linea(x0, y1, x1, y1, ASSE, spessore=2)

    # --- media complessiva (tratteggiata)
    ym = Y(ris["media"])
    t.linea(x0, ym, x1, ym, MEDIA, spessore=2, tratteggio=8)

    # --- punti delle vendite
    for d, p in zip(date, prezzi):
        t.disco(X(d), Y(p), 5, PUNTI)

    # --- media mobile su finestra di giorni (un punto per giorno di vendita)
    giorni_tot = max(1, (t1 - t0).days)
    finestra = int(min(FINESTRA_MAX, max(FINESTRA_MIN, giorni_tot / 12)))
    if len(prezzi) >= 2:
        prec, j, visti = None, 0, set()
        for i in range(len(prezzi)):
            giorno = date[i].date()
            if giorno in visti:
                continue
            visti.add(giorno)
            # ultimo indice dello stesso giorno
            k = i
            while k + 1 < len(prezzi) and date[k + 1].date() == giorno:
                k += 1
            while (date[k] - date[j]).days > finestra:
                j += 1
            fin = prezzi[j:k + 1]
            pt = (X(date[k]), Y(sum(fin) / len(fin)))
            # niente linea sopra i periodi senza vendite piu' lunghi della finestra
            if i > 0 and (date[i] - date[i - 1]).days > finestra:
                prec = None
            if prec:
                t.linea(prec[0], prec[1], pt[0], pt[1], LINEA, spessore=3)
            prec = pt

    # --- ultima vendita
    xu, yu = X(date[-1]), Y(prezzi[-1])
    t.disco(xu, yu, 9, SFONDO)
    t.disco(xu, yu, 7, ULTIMO)

    # --- legenda
    lx, ly = ML, 88
    t.disco(lx + 6, ly + 7, 5, PUNTI)
    lx += 20 + t.testo(lx + 20, ly, "vendita", TESTO_SOFT) + 30
    t.linea(lx, ly + 7, lx + 30, ly + 7, LINEA, spessore=3)
    lx += 40 + t.testo(lx + 40, ly, f"media {finestra} giorni", TESTO_SOFT) + 30
    t.linea(lx, ly + 7, lx + 30, ly + 7, MEDIA, spessore=2, tratteggio=8)
    lx += 40 + t.testo(lx + 40, ly, "media totale", TESTO_SOFT) + 30
    t.disco(lx + 6, ly + 7, 7, ULTIMO)
    t.testo(lx + 20, ly, f"ultima {_euro_breve(prezzi[-1])} ({date[-1].strftime('%d/%m/%y')})", ULTIMO)

    return t.png()


# ------------------------------------------------------------------ versione matplotlib

def _finestra_giorni(date):
    giorni_tot = max(1, (max(date) - min(date)).days)
    return int(min(FINESTRA_MAX, max(FINESTRA_MIN, giorni_tot / 12)))


def _media_mobile(date, prezzi, finestra):
    """Segmenti [(date, valori), ...] della media mobile, spezzati nei buchi > finestra."""
    segmenti, xs, ys, j, visti = [], [], [], 0, set()
    for i in range(len(prezzi)):
        giorno = date[i].date()
        if giorno in visti:
            continue
        visti.add(giorno)
        k = i
        while k + 1 < len(prezzi) and date[k + 1].date() == giorno:
            k += 1
        while (date[k] - date[j]).days > finestra:
            j += 1
        if i > 0 and (date[i] - date[i - 1]).days > finestra and xs:
            segmenti.append((xs, ys))
            xs, ys = [], []
        fin = prezzi[j:k + 1]
        xs.append(date[k])
        ys.append(sum(fin) / len(fin))
    if xs:
        segmenti.append((xs, ys))
    return segmenti


def _euro_it(v, decimali=0):
    s = f"{v:,.{decimali}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} \u20ac"


def _hex(c):
    return "#%02x%02x%02x" % c


def _disegna_matplotlib(ris: dict) -> bytes:
    import io
    import matplotlib
    matplotlib.use("Agg")  # nessuna finestra: solo immagine in memoria
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    storico = ris["storico"]
    date = [datetime.strptime(v["data"][:16], "%Y-%m-%d %H:%M") for v in storico]
    prezzi = [v["prezzo_bott"] for v in storico]
    speciali = [bool(v.get("edizione")) for v in storico]
    misto = any(speciali) and not all(speciali)
    finestra = _finestra_giorni(date)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # punti delle vendite (se ci sono standard e speciali insieme, colori diversi)
    std = [(d, p) for d, p, sp in zip(date, prezzi, speciali) if not sp or not misto]
    if std:
        ax.scatter(*zip(*std), s=26, color=_hex(PUNTI), alpha=0.75, linewidths=0,
                   label="vendita", zorder=3)
    if misto:
        spc = [(d, p) for d, p, sp in zip(date, prezzi, speciali) if sp]
        ax.scatter(*zip(*spc), s=30, facecolors="none", edgecolors="#8e5cc4", linewidths=1.3,
                   label="edizione speciale", zorder=3)

    # media mobile
    if len(prezzi) >= 2:
        for n, (xs, ys) in enumerate(_media_mobile(date, prezzi, finestra)):
            ax.plot(xs, ys, color=_hex(LINEA), linewidth=2.2, zorder=4,
                    label=f"media {finestra} giorni" if n == 0 else None)

    # media totale
    ax.axhline(ris["media"], color=_hex(MEDIA), linewidth=1.3, linestyle=(0, (5, 4)), zorder=2,
               label=f"media totale {_euro_it(ris['media'])}")

    # ultima vendita
    ax.scatter([date[-1]], [prezzi[-1]], s=90, color=_hex(ULTIMO), edgecolors="white",
               linewidths=1.5, zorder=5,
               label=f"ultima {_euro_it(prezzi[-1])} ({date[-1].strftime('%d/%m/%y')})")

    # assi
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _euro_it(v)))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    loc = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(loc)
    giorni = (max(date) - min(date)).days
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m" if giorni <= 45 else "%m/%y"))
    if giorni == 0:
        from datetime import timedelta
        ax.set_xlim(date[0] - timedelta(days=3), date[0] + timedelta(days=3))
    ax.grid(axis="y", color=_hex(GRIGLIA), linewidth=0.8, zorder=0)
    for lato in ("top", "right", "left"):
        ax.spines[lato].set_visible(False)
    ax.spines["bottom"].set_color(_hex(ASSE))
    ax.tick_params(colors=_hex(TESTO_SOFT), labelsize=9, length=0)
    ax.tick_params(axis="x", length=4, color=_hex(ASSE))

    # titolo
    titolo = "  \u00b7  ".join(str(x) for x in ris["richiesta"] if str(x).strip() not in ("", "*"))
    n = ris["vendite"]
    fig.text(0.075, 0.955, titolo, fontsize=15, fontweight="bold", color=_hex(TESTO), ha="left")
    fig.text(0.075, 0.915,
             f"{n} {'vendita' if n == 1 else 'vendite'} \u00b7 prezzo per bottiglia dei lotti venduti"
             + (f" \u00b7 escluse {sum(ris['escluse'].values())} edizioni speciali" if ris.get("escluse") else ""),
             fontsize=9.5, color=_hex(TESTO_SOFT), ha="left")
    leg = ax.legend(loc="upper left", bbox_to_anchor=(0, 1.1), ncol=5, frameon=False,
                    fontsize=8.5, handlelength=1.8, columnspacing=1.4, borderaxespad=0)
    for t in leg.get_texts():
        t.set_color(_hex(TESTO_SOFT))
    fig.subplots_adjust(left=0.075, right=0.975, top=0.80, bottom=0.08)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def disegna(ris: dict) -> bytes:
    """Riceve il risultato di price_lookup.cerca e restituisce il PNG.
    Prova matplotlib; se non e' installato o Windows lo blocca, usa la versione in Python puro."""
    try:
        return _disegna_matplotlib(ris)
    except Exception as e:  # ImportError, DLL bloccata, ...
        import logging
        logging.warning(f"grafico: matplotlib non disponibile ({e}), uso il disegno semplice")
        return _disegna_puro(ris)
