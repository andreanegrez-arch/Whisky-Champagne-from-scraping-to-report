from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import pandas as pd
import numpy as np
import re
from sklearn.linear_model import LinearRegression
from api.routes import lots, scraper, analysis
from database import init_db
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import traceback
from fastapi import Request
from fastapi.responses import JSONResponse

# Startup / shutdown lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    yield

app = FastAPI(
    title="Catawiki Champagne Auctions API",
    description="Professional API for scraping and analyzing champagne auction data",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        err_msg = f"GLOBAL ERROR: {str(exc)}\n{traceback.format_exc()}"
        logger.error(err_msg)
        with open("debug_error.log", "a") as f:
            f.write(f"\n--- {datetime.now()} ---\n{err_msg}\n")
        return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": "Check debug_error.log"})

# Include routers
app.include_router(lots.router, prefix="/api/lots", tags=["Lots"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])

import os
from datetime import datetime

MONTHS_ITA = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}

now = datetime.now()
mese_nome = MONTHS_ITA[now.month]
excel_name = f"database champagne {mese_nome}.xlsx"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(os.path.dirname(ROOT_DIR), "data", excel_name)

if os.path.exists(excel_path):
    df = pd.read_excel(excel_path)
else:
    # Exact columns needed by routes
    cols = [
        "Maison", "Tipologia", "Numero Bottiglie", "Formato", "Vintage",
        "Data Chiusura", "Prezzo Riserva", "Numero Offerte", "Nazionalita",
        "Prezzo Finale", "Costi Spedizione", "title", "currency", "status", "url", "timestamp"
    ]
    df = pd.DataFrame(columns=cols)

from parsers import detect_maison, detect_tipologia, detect_vintage, parse_lot_title

# ================= FORMAT DETECTION =================
def detect_format(nome: str) -> str:
    nome = str(nome).lower()
    if "magnum" in nome or "1.5" in nome or "1,5" in nome:
        return "Magnum"
    elif "3l" in nome or "jeroboam" in nome:
        return "Jeroboam"
    elif "6l" in nome or "methusalem" in nome or "methuselah" in nome:
        return "Methuselah"
    elif "15l" in nome or "nebuchadnezzar" in nome:
        return "Nebuchadnezzar"
    else:
        return "0.75L"

def parse_row(nome):
    parsed = parse_lot_title(str(nome))
    return {
        "maison":    parsed["maison"],
        "tipologia": parsed["tipologia"],
        "annata":    parsed.get("vintage"),
        "formato":   detect_format(str(nome)),
    }

# Process title with safety check
if not df.empty and 'title' in df.columns:
    parsed_cols = df['title'].apply(parse_row).apply(pd.Series)
    df = pd.concat([df, parsed_cols], axis=1)
else:
    # Initialize parsed columns as empty
    df['maison'] = df.get('Maison', '')
    df['tipologia'] = df.get('Tipologia', '')
    df['annata'] = df.get('Vintage', None)
    df['formato'] = ''

# Safety: ensure is_mixed column exists
if 'is_mixed' not in df.columns:
    df['is_mixed'] = False


# ================= PRICE BY COUNTRY =================
@app.get("/price-by-country")
def price_by_country(maison: str, tipologia: str=None):
    data = df[df['maison'] == maison]

    if tipologia:
        data = data[data['tipologia'] == tipologia]

    grouped = data.groupby(['Nazionalita'])['Prezzo Finale']

    result = pd.DataFrame({
        'country': grouped.mean().index,
        'mean_price': grouped.mean().values
    })

    return result.sort_values(by='mean_price', ascending=False).to_dict(orient='records')

# ================= GEO ANALYSIS =================
@app.get("/geo-analysis")
def geo_analysis(maison: str, tipologia: str=None):
    data = df[df['maison'] == maison]

    if tipologia:
        data = data[data['tipologia'] == tipologia]

    grouped = data.groupby('Nazionalita').size()

    return [
        {"country": k, "count": int(v)}
        for k, v in grouped.items()
    ]

# ================= FORMAT ANALYSIS =================
@app.get("/format-analysis")
def format_analysis(maison: str):
    data = df[df['maison'] == maison]

    grouped = data.groupby('formato')['Prezzo Finale']

    return pd.DataFrame({
        'format': grouped.mean().index,
        'mean_price': grouped.mean().values
    }).to_dict(orient='records')

# ================= INSIGHT =================
# Ora puoi capire:
# - QUALI PAESI PAGANO DI PIÙ
# - QUALI FORMATI RENDONO DI PIÙ
# - DOVE IL MERCATO È PIÙ FORTE

# ================= HIERARCHY =================
@app.get("/api/dashboard/hierarchy")
def hierarchy():
    """
    Returns the full Maison → Tipologia → Annata hierarchy used by the
    Dashboard dropdowns.  Only non-mixed lots are considered.
    """
    data = df[~df["is_mixed"]]

    result = []
    for maison in sorted(data['maison'].unique()):
        m_data = data[data['maison'] == maison]
        tipologie_list = []
        for tipo in sorted(m_data['tipologia'].dropna().unique()):
            t_data = m_data[m_data['tipologia'] == tipo]
            annate = sorted(
                [int(a) for a in t_data['annata'].dropna().unique()],
                reverse=True
            )
            tipologie_list.append({"name": tipo, "annate": annate})
        result.append({"name": maison, "tipologie": tipologie_list})

    return result

# ================= STATS =================
@app.get("/api/dashboard/stats")
def stats(maison: str, tipologia: str=None, annata: int=None):
    data = df[(df['maison']==maison) & (~df["is_mixed"])]

    if tipologia:
        data = data[data['tipologia']==tipologia]
    if annata:
        data = data[data['annata']==annata]

    grouped = data.groupby('Data Chiusura')['Prezzo Finale']

    return pd.DataFrame({
        'data': grouped.mean().index,
        'mean': grouped.mean().values,
        'median': grouped.median().values
    }).to_dict(orient='records')

# ================= PREDICTION =================
@app.get("/api/dashboard/predict")
def predict(maison: str, tipologia: str):
    data = df[
        (df['maison']==maison) &
        (df['tipologia']==tipologia) &
        (~df["is_mixed"])
    ]

    X = np.arange(len(data)).reshape(-1,1)
    y = data['Prezzo Finale'].values

    model = LinearRegression().fit(X,y)

    pred = model.predict([[len(data)+1]])[0]
    score = model.score(X,y)

    if score > 0.7:
        strategy = "BUY"
    elif score > 0.4:
        strategy = "HOLD"
    else:
        strategy = "AVOID"

    return {
        "prediction": float(pred),
        "confidence": min(5, round(score*5)),
        "strategy": strategy
    }

# ================= NATIONALITY STATS =================
@app.get("/api/dashboard/nationalities")
def nationalities(maison: str = None):
    data = df[~df["is_mixed"]].copy()
    
    if maison:
        data = data[data['maison'] == maison]
    
    # Group by maison and nationality, count occurrences
    nat_stats = data.groupby(['maison', 'Nazionalita']).size().reset_index(name='count')
    
    # Convert to nested structure
    result = {}
    for maison_name in nat_stats['maison'].unique():
        maison_data = nat_stats[nat_stats['maison'] == maison_name]
        result[maison_name] = [
            {
                'nationality': row['Nazionalita'],
                'count': int(row['count'])
            }
            for _, row in maison_data.iterrows()
        ]
    
    if maison:
        return result.get(maison, [])
    else:
        return result

# ================= MIXED LOT =================
@app.get("/api/mixed")
def mixed():
    return df[df["is_mixed"]].to_dict(orient="records")

@app.get("/")
async def root():
    return {"message": "Welcome to Catawiki Champagne API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
