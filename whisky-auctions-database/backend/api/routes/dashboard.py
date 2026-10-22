from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from database import get_db, LotORM, async_session
import pandas as pd
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression

router = APIRouter()


@router.get("/hierarchy")
async def get_hierarchy():
    """
    Get complete hierarchy: Distilleria > Stile > Eta
    Returns sorted structure for UI dropdown building
    """
    # Get all lots from database
    async with async_session() as session:
        result = await session.execute(select(LotORM))
        all_lots = result.scalars().all()
    
    # Build hierarchy
    hierarchy = {}
    
    for lot in all_lots:
        distilleria = lot.distilleria or "Unknown"
        stile = lot.stile or "Brut"
        eta = lot.eta or "NV"
        
        if distilleria not in hierarchy:
            hierarchy[distilleria] = {}
        
        if stile not in hierarchy[distilleria]:
            hierarchy[distilleria][stile] = set()
        
        hierarchy[distilleria][stile].add(eta)
    
    # Convert to sorted JSON structure
    result_list = []
    for distilleria in sorted(hierarchy.keys()):
        tipologie = []
        for stile in sorted(hierarchy[distilleria].keys()):
            annate = sorted([str(v) for v in hierarchy[distilleria][stile]])
            tipologie.append({
                "name": stile,
                "annate": annate
            })
        
        result_list.append({
            "name": distilleria,
            "tipologie": tipologie
        })
    
    return result_list


@router.get("/stats")
async def get_stats(
    distilleria: str = Query(...),
    stile: str = Query(None),
    eta: str = Query(None)
):
    """
    Get statistics for a specific combination
    Returns data grouped by closing date with mean and median prices
    """
    async with async_session() as session:
        # Build query
        query = select(LotORM).where(LotORM.distilleria == distilleria)
        
        if stile:
            query = query.where(LotORM.stile == stile)
        if eta:
            query = query.where(LotORM.eta == eta)
        
        result = await session.execute(query)
        lots = result.scalars().all()
    
    # Convert to DataFrame for analysis
    data = []
    for lot in lots:
        if lot.prezzo_finale and lot.prezzo_finale > 0:
            data.append({
                'data': lot.data_chiusura or "Unknown",
                'prezzo': lot.prezzo_finale,
                'numero_bottiglie': lot.numero_bottiglie or 1,
                'url': lot.url,
                'status': lot.status
            })
    
    if not data:
        return []
    
    df = pd.DataFrame(data)
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    df = df.dropna(subset=['data']).sort_values('data')
    
    # Group by date and calculate statistics
    grouped = df.groupby('data')['prezzo'].agg(['mean', 'median']).reset_index()
    grouped['data'] = grouped['data'].dt.strftime('%Y-%m-%d')
    
    return grouped.to_dict(orient='records')


@router.get("/predict")
async def get_prediction(
    distilleria: str = Query(...),
    stile: str = Query(None)
):
    """
    Predict next price using linear regression
    Returns: prediction, confidence (R²), strategy (BUY/HOLD/AVOID)
    """
    async with async_session() as session:
        query = select(LotORM).where(LotORM.distilleria == distilleria)
        
        if stile:
            query = query.where(LotORM.stile == stile)
        
        result = await session.execute(query)
        lots = result.scalars().all()
    
    # Prepare data for ML
    prices = [
        lot.prezzo_finale 
        for lot in lots 
        if lot.prezzo_finale and lot.prezzo_finale > 0 and lot.status == "CLOSED"
    ]
    
    if len(prices) < 2:
        return {
            "prediction": None,
            "confidence": 0,
            "strategy": "INSUFFICIENT_DATA",
            "message": "Need at least 2 closed auctions to make prediction"
        }
    
    # Linear regression on sequential data
    X = np.arange(len(prices)).reshape(-1, 1)
    y = np.array(prices)
    
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict next price
    next_idx = np.array([[len(prices)]])
    prediction = float(model.predict(next_idx)[0])
    
    # Calculate confidence (R² score, normalized to 0-5)
    r_squared = model.score(X, y)
    confidence = min(5, max(0, int(r_squared * 5)))
    
    # Determine strategy
    if r_squared > 0.7:
        strategy = "BUY"
        trend = "strong uptrend"
    elif r_squared > 0.4:
        strategy = "HOLD"
        trend = "moderate trend"
    else:
        strategy = "AVOID"
        trend = "weak trend"
    
    # Calculate trend direction
    price_trend = "↑ Uptrend" if model.coef_[0] > 0 else "↓ Downtrend"
    
    return {
        "prediction": round(prediction, 2),
        "confidence": confidence,
        "confidence_score": round(r_squared, 3),
        "strategy": strategy,
        "trend": price_trend,
        "current_avg": round(np.mean(prices), 2),
        "price_range": {
            "min": round(min(prices), 2),
            "max": round(max(prices), 2)
        },
        "num_data_points": len(prices)
    }
