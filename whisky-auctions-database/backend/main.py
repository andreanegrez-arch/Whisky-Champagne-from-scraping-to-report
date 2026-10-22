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
    title="Catawiki Whisky Auctions API",
    description="Professional API for scraping and analyzing whisky auction data",
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
excel_name = f"database whisky {mese_nome}.xlsx"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(os.path.dirname(ROOT_DIR), "data", excel_name)

if os.path.exists(excel_path):
    df = pd.read_excel(excel_path)
    # Align headers to model names if they come from old Excel
    header_map = {
        "Nazionalità Offerente": "nazionalita",
        "Nazionalita": "nazionalita",
        "Prezzo Finale": "prezzo_finale",
        "Data Chiusura": "data_chiusura",
        "Numero Bottiglie": "numero_bottiglie"
    }
    df.rename(columns=header_map, inplace=True)
else:
    # Robust initialization for empty month (Aprile)
    cols = [
        "Distilleria", "Stile", "Annata", "Formato", "Nazionalità Offerente",
        "Prezzo Finale", "Data Chiusura", "Prezzo Riserva", "Numero Offerte", "Numero Bottiglie",
        "title", "distilleria", "stile", "annata", "formato", "is_mixed", "prezzo_finale", "nazionalita", "data_chiusura"
    ]
    df = pd.DataFrame(columns=cols)

from parsers import detect_distilleria, detect_stile, detect_eta, parse_lot_title

# ================= FORMAT DETECTION =================
def detect_format(nome: str) -> str:
    nome = nome.lower()
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
        "distilleria":    parsed["distilleria"],
        "stile": parsed["stile"],
        "annata":    parsed.get("eta"),
        "formato":   detect_format(str(nome)),
    }

if not df.empty and 'title' in df.columns:
    parsed = df['title'].apply(parse_row).apply(pd.Series)
    df = pd.concat([df, parsed], axis=1)

# Safety: ensure is_mixed column exists and is boolean
if 'is_mixed' not in df.columns:
    df['is_mixed'] = False
else:
    df['is_mixed'] = df['is_mixed'].fillna(False).astype(bool)


@app.get("/")
async def root():
    return {"message": "Welcome to Catawiki Whisky API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
