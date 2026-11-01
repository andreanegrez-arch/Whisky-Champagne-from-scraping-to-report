"""
grafico_aste.py - grafico prezzi delle aste per il bot Telegram (comando /grafico).

Cosa produce
------------
1. PNG       Immagine del grafico (prezzo nel tempo) con ogni punto NUMERATO.
             Telegram la mostra subito nella chat.
2. Pulsanti  Sotto l'immagine, un pulsante per ogni punto ("#3 · €120"):
             toccandolo si apre l'asta Catawiki corrispondente.
3. HTML      Grafico interattivo inviato come file: aprendolo, ogni punto e'
             cliccabile e porta direttamente all'asta (tenendo il dito / il
             mouse sopra si vedono titolo, prezzo e data). Sotto il grafico c'e'
             anche l'elenco numerato dei lotti con i link.

Punti pieni = lotti CHIUSI (prezzo finale), punti vuoti = aste APERTE
(offerta attuale). Il file e' identico per whisky e champagne: cambia solo la
configurazione passata da telegram_bot.py.
"""

import html
import io
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_PUNTI = 30          # oltre, grafico e pulsanti diventano illeggibili
GIORNI_DEFAULT = 30     # finestra temporale senza filtro di ricerca


@dataclass
class Punto:
    numero: int
    data: datetime
    prezzo: float
    titolo: str
    url: str
    aperto: bool


def _parse_data(valore):
    if not valore:
        return None
    testo = str(valore).strip().replace("T", " ")
    for parte in (testo[:19], testo[:16], testo[:10]):
        try:
            return datetime.fromisoformat(parte)
        except ValueError:
            continue
    return None


def carica_punti(db_path, colonne_ricerca, filtro="", giorni=None, limite=MAX_PUNTI):
    """Legge dal database i lotti da disegnare.

    filtro          testo libero: ogni parola deve comparire nel titolo o in una
                    delle colonne_ricerca (es. "lagavulin 16").
    giorni          finestra temporale; se None: 30 giorni senza filtro,
                    nessun limite con filtro (si vuole lo storico del prodotto).
    Restituisce i punti piu' recenti (max `limite`), ordinati per data.
    """
    parole = [p for p in filtro.lower().split() if p]
    if giorni is None and not parole:
        giorni = GIORNI_DEFAULT

    where = ["prezzo_finale > 0", "url IS NOT NULL", "data_chiusura IS NOT NULL",
             "status IN ('CLOSED', 'OPEN')"]
    params = []
    campi = ["title"] + list(colonne_ricerca)
    for parola in parole:
        where.append("(" + " OR ".join(f"LOWER(COALESCE({c}, '')) LIKE ?" for c in campi) + ")")
        params.extend([f"%{parola}%"] * len(campi))
    if giorni:
        where.append("data_chiusura >= ?")
        params.append((datetime.now() - timedelta(days=giorni)).strftime("%Y-%m-%d"))

    query = (f"SELECT data_chiusura, prezzo_finale, title, url, status FROM lots "
             f"WHERE {' AND '.join(where)} ORDER BY data_chiusura DESC LIMIT ?")
    params.append(int(limite))

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        righe = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    punti = []
    for data_txt, prezzo, titolo, url, status in righe:
        data = _parse_data(data_txt)
        if data is None:
            continue
        punti.append(Punto(0, data, float(prezzo), titolo or "", url, status == "OPEN"))
    punti.sort(key=lambda p: p.data)
    for i, p in enumerate(punti, start=1):
        p.numero = i
    return punti


def _euro(valore):
    return f"€{valore:,.0f}".replace(",", ".")


def crea_png(punti, titolo):
    """Grafico statico con i punti numerati. Restituisce bytes PNG (o None
    se matplotlib non e' installato)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=130)
    chiusi = [p for p in punti if not p.aperto]
    aperti = [p for p in punti if p.aperto]
    ax.plot([p.data for p in punti], [p.prezzo for p in punti],
            color="#b8c0cc", linewidth=1, zorder=1)
    if chiusi:
        ax.scatter([p.data for p in chiusi], [p.prezzo for p in chiusi], s=170,
                   color="#2a6fdb", zorder=2, label="Chiuso (prezzo finale)")
    if aperti:
        ax.scatter([p.data for p in aperti], [p.prezzo for p in aperti], s=170,
                   facecolors="white", edgecolors="#e07b00", linewidths=2, zorder=2,
                   label="Aperto (offerta attuale)")
    for p in punti:
        ax.annotate(str(p.numero), (p.data, p.prezzo), ha="center", va="center",
                    fontsize=7, fontweight="bold", zorder=3,
                    color="#e07b00" if p.aperto else "white")

    # le emoji non sono nei font di matplotlib: nel PNG si tolgono
    ax.set_title("".join(ch for ch in titolo if ord(ch) < 0x2190).strip(), fontsize=12, loc="left")
    ax.set_ylabel("Prezzo (€)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _euro(v)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    ax.grid(axis="y", color="#e6e8eb")
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.text(0.99, 0.01, "Tocca i pulsanti sotto l'immagine per aprire l'asta n°",
             ha="right", fontsize=7, color="#777")
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def crea_html(punti, titolo):
    """Grafico interattivo autonomo (nessuna libreria esterna): ogni punto e'
    un link all'asta. Restituisce bytes UTF-8."""
    W, H = 900, 440
    ml, mr, mt, mb = 70, 20, 20, 50
    t0 = min(p.data for p in punti).timestamp()
    t1 = max(p.data for p in punti).timestamp()
    v0 = min(p.prezzo for p in punti)
    v1 = max(p.prezzo for p in punti)
    if t1 == t0:
        t0, t1 = t0 - 86400, t1 + 86400
    pad = (v1 - v0) * 0.08 or max(v1 * 0.1, 1)
    v0, v1 = max(0, v0 - pad), v1 + pad

    def x(p):
        return ml + (p.data.timestamp() - t0) / (t1 - t0) * (W - ml - mr)

    def y(v):
        return mt + (1 - (v - v0) / (v1 - v0)) * (H - mt - mb)

    svg = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(titolo)}">']
    for i in range(5):  # griglia e asse Y
        v = v0 + (v1 - v0) * i / 4
        svg.append(f'<line class="grid" x1="{ml}" x2="{W - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="ax" x="{ml - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{_euro(v)}</text>')
    ultima_x = -1e9  # etichette asse X, senza sovrapposizioni
    for p in punti:
        if x(p) - ultima_x < 90:
            continue
        ultima_x = x(p)
        svg.append(f'<text class="ax" x="{x(p):.1f}" y="{H - mb + 20}" text-anchor="middle">'
                   f'{p.data:%d/%m/%y}</text>')
    linea = " ".join(f"{x(p):.1f},{y(p.prezzo):.1f}" for p in punti)
    svg.append(f'<polyline class="trend" points="{linea}"/>')
    for p in punti:
        info = f"#{p.numero} · {_euro(p.prezzo)} · {p.data:%d/%m/%Y} · {'APERTA' if p.aperto else 'chiusa'}\n{p.titolo}"
        cls = "pt open" if p.aperto else "pt"
        svg.append(
            f'<a href="{html.escape(p.url)}" target="_blank" rel="noopener">'
            f'<title>{html.escape(info)}</title>'
            f'<circle class="{cls}" cx="{x(p):.1f}" cy="{y(p.prezzo):.1f}" r="13"/>'
            f'<text class="num{" open" if p.aperto else ""}" x="{x(p):.1f}" y="{y(p.prezzo) + 3.5:.1f}" '
            f'text-anchor="middle">{p.numero}</text></a>')
    svg.append("</svg>")

    righe = "".join(
        f'<tr><td>{p.numero}</td><td>{p.data:%d/%m/%y}</td><td class="r">{_euro(p.prezzo)}</td>'
        f'<td><a href="{html.escape(p.url)}" target="_blank" rel="noopener">{html.escape(p.titolo)}</a>'
        f'{" <b>(aperta)</b>" if p.aperto else ""}</td></tr>'
        for p in reversed(punti))

    pagina = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titolo)}</title>
<style>
:root {{ --bg:#fff; --fg:#1d2330; --muted:#6b7280; --grid:#e6e8eb; --line:#b8c0cc;
        --closed:#2a6fdb; --open:#e07b00; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#14171c; --fg:#e8eaed; --muted:#9aa0a6; --grid:#2a2f37; --line:#4a515c;
          --closed:#5b9bff; --open:#ffa53d; }} }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg);
       font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif; }}
h1 {{ font-size:18px; margin:0 0 4px; }} p {{ color:var(--muted); font-size:13px; margin:0 0 12px; }}
.scroll {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
svg {{ width:100%; min-width:760px; height:auto; display:block; }}
.grid {{ stroke:var(--grid); }} .ax {{ fill:var(--muted); font-size:12px; }}
.trend {{ fill:none; stroke:var(--line); stroke-width:1.5; }}
.pt {{ fill:var(--closed); cursor:pointer; }} .pt.open {{ fill:var(--bg); stroke:var(--open); stroke-width:2.5; }}
a:hover .pt {{ stroke:var(--fg); stroke-width:3; }}
.num {{ fill:#fff; font-size:10px; font-weight:700; pointer-events:none; }} .num.open {{ fill:var(--open); }}
table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:16px; }}
td {{ padding:6px 4px; border-top:1px solid var(--grid); vertical-align:top; }} td.r {{ text-align:right; white-space:nowrap; }}
td a {{ color:var(--closed); }}
</style></head><body>
<h1>{html.escape(titolo)}</h1>
<p>Tocca un punto per aprire l'asta su Catawiki (su telefono scorri il grafico di lato). ● chiusa (prezzo finale) · ○ aperta (offerta attuale)</p>
<div class="scroll">{''.join(svg)}</div>
<table>{righe}</table>
</body></html>"""
    return pagina.encode("utf-8")


def pulsanti(punti, per_riga=3):
    """Righe di (etichetta, url) per la InlineKeyboard di Telegram."""
    tasti = [(f"#{p.numero} · {_euro(p.prezzo)}{' ○' if p.aperto else ''}", p.url)
             for p in reversed(punti)  # i piu' recenti per primi
             if str(p.url).startswith(("http://", "https://"))]
    return [tasti[i:i + per_riga] for i in range(0, len(tasti), per_riga)]


def titolo_grafico(prodotto, filtro, giorni, punti):
    if filtro:
        base = f"{prodotto} – «{filtro}»" + (f", ultimi {giorni} giorni" if giorni else "")
    else:
        base = f"{prodotto} – ultimi {giorni or GIORNI_DEFAULT} giorni"
    return f"{base} ({len(punti)} lotti)"


def analizza_argomenti(args):
    """'/grafico lagavulin 16 90g' -> ('lagavulin 16', 90). Un ultimo argomento
    del tipo '90g' / '90gg' imposta i giorni."""
    args = list(args or [])
    giorni = None
    if args:
        ultimo = args[-1].lower().rstrip("g")
        if args[-1].lower().endswith("g") and ultimo.isdigit():
            giorni = int(ultimo)
            args = args[:-1]
    return " ".join(args).strip(), giorni
