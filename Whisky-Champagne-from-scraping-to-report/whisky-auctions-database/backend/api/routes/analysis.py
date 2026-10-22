from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from typing import List, Dict
from database import get_db, LotORM
from api.routes.lots import filtro_imbottigliatore
from models import AnalysisSummary, DistilleryStats, BottleAnalysis, HistoricalPrice, StrategyComparison, MetricsResponse, AggregateMetrics, RangePoint, NationalityStat, TopTradedBottleNationality, BoxAnalysis
from starlette.concurrency import run_in_threadpool
from datetime import datetime

router = APIRouter()

# Valori che NON sono una nazionalita': vengono esclusi da grafici e statistiche.
# "Unknown" = lotto non venduto, oppure letto con la vecchia logica di estrazione.
UNKNOWN_NATIONALITIES = ("Unknown", "Sconosciuto", "NV", "")


def known_nationality():
    return and_(LotORM.nazionalita != None, LotORM.nazionalita.notin_(UNKNOWN_NATIONALITIES))

@router.get("/summary", response_model=AnalysisSummary)
async def get_summary(filter_mode: str = "all", db: AsyncSession = Depends(get_db)):
    # Base query for counts
    def apply_filter(q):
        if filter_mode == "pure":
            return q.where(or_(LotORM.is_mixed == False, LotORM.is_mixed == None))
        elif filter_mode == "mixed":
            return q.where(LotORM.is_mixed == True)
        return q

    # Total lots
    total_q = apply_filter(select(func.count()).select_from(LotORM))
    total_lots = (await db.execute(total_q)).scalar()
    
    # Sold lots
    sold_q = apply_filter(select(func.count()).select_from(LotORM).where(LotORM.numero_offerte > 0))
    sold_lots = (await db.execute(sold_q)).scalar()
    
    success_rate = (sold_lots / total_lots * 100) if total_lots > 0 else 0
    
    # Distilleria Stats
    stats_q = apply_filter(select(
        LotORM.distilleria,
        func.min(LotORM.prezzo_finale).label("prezzo_min"),
        func.max(LotORM.prezzo_finale).label("prezzo_max"),
        func.avg(LotORM.prezzo_finale).label("prezzo_medio"),
        func.count().label("lotti_totali"),
        func.sum(LotORM.numero_bottiglie).label("bottiglie_totali")
    ).group_by(LotORM.distilleria).order_by(func.sum(LotORM.numero_bottiglie).desc()))
    
    stats_res = await db.execute(stats_q)
    rows = stats_res.all()
    distillery_stats = [
        DistilleryStats(
            distilleria=r.distilleria,
            prezzo_min=r.prezzo_min or 0,
            prezzo_max=r.prezzo_max or 0,
            prezzo_medio=r.prezzo_medio or 0,
            lotti_totali=r.lotti_totali,
            bottiglie_totali=r.bottiglie_totali or 0
        ) for r in rows
    ]
    
    return AnalysisSummary(
        total_lots=total_lots,
        sold_lots=sold_lots,
        success_rate=success_rate,
        distillery_stats=distillery_stats
    )

@router.get("/bottle", response_model=BottleAnalysis)
async def get_bottle_analysis(
    distilleria: str, 
    stile: str, 
    eta: str, 
    formato: str = None, 
    has_box: bool = None, 
    filter_mode: str = "all",
    db: AsyncSession = Depends(get_db)
):
    # Fetch only successful CLOSED lots for this specific bottle
    query = select(LotORM).where(
        LotORM.distilleria == distilleria,
        LotORM.stile == stile,
        LotORM.eta == eta,
        LotORM.status == "CLOSED",
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0
    )
    
    if filter_mode == "pure":
        query = query.where(or_(LotORM.is_mixed == False, LotORM.is_mixed == None))
    elif filter_mode == "mixed":
        query = query.where(LotORM.is_mixed == True)

    if formato:
        query = query.where(LotORM.formato == formato)
    if has_box is not None:
        query = query.where(LotORM.has_box == has_box)
        
    query = query.order_by(LotORM.data_chiusura.asc())
    
    result = await db.execute(query)
    lots = result.scalars().all()

    # Basic Stats
    prices = [l.prezzo_finale for l in lots if l.prezzo_finale and l.prezzo_finale > 0]
    prezzo_min = min(prices) if prices else 0
    prezzo_max = max(prices) if prices else 0
    prezzo_medio = sum(prices) / len(prices) if prices else 0
    
    stats = DistilleryStats(
        distilleria=distilleria,
        prezzo_min=prezzo_min,
        prezzo_max=prezzo_max,
        prezzo_medio=prezzo_medio,
        lotti_totali=len(lots),
        bottiglie_totali=sum([(l.numero_bottiglie or 0) for l in lots])
    )
    
    # History with price per bottle - Filter out suspicious future dates for CLOSED status
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    history = [
        HistoricalPrice(
            date=l.data_chiusura or "Unknown",
            price=l.prezzo_finale or 0,
            reserve=l.prezzo_riserva,
            num_bottles=(l.numero_bottiglie or 1),
            price_per_bottle=(l.prezzo_finale / (l.numero_bottiglie or 1)) if l.prezzo_finale and (l.numero_bottiglie or 0) > 0 else 0,
            has_box=l.has_box,
            url=str(l.url)
        ) for l in lots if l.status == "CLOSED" and (l.data_chiusura and l.data_chiusura <= now_str)
    ]
    
    # Strategy Comparison (Single vs Bundle)
    singles = [h.price_per_bottle for h in history if h.num_bottles == 1 and h.price_per_bottle > 0]
    bundles = [h.price_per_bottle for h in history if h.num_bottles > 1 and h.price_per_bottle > 0]
    
    avg_single = sum(singles) / len(singles) if singles else 0
    avg_bundle = sum(bundles) / len(bundles) if bundles else 0
    
    recommendation = "BUNDLING (Lots > 1)" if avg_bundle > avg_single else "SINGLE (Individual lots)"
    if not singles and not bundles:
        recommendation = "NOT ENOUGH DATA"
    elif not singles:
        recommendation = "BUNDLING (Single sales missing)"
    elif not bundles:
        recommendation = "SINGLE (Bundle sales missing)"
        
    gain_pct = ((abs(avg_bundle - avg_single) / min(avg_single, avg_bundle)) * 100) if (avg_single > 0 and avg_bundle > 0) else 0
    
    comparison = StrategyComparison(
        individual_avg=round(avg_single, 2),
        bundle_avg=round(avg_bundle, 2),
        recommendation=recommendation,
        potential_gain_pct=round(gain_pct, 1)
    )
    
    # Box Analysis (Premium for having the box)
    with_box_prices = [(l.prezzo_finale / (l.numero_bottiglie or 1)) for l in lots if l.has_box and l.prezzo_finale and (l.numero_bottiglie or 0) > 0]
    without_box_prices = [(l.prezzo_finale / (l.numero_bottiglie or 1)) for l in lots if not l.has_box and l.prezzo_finale and (l.numero_bottiglie or 0) > 0]
    
    avg_with = sum(with_box_prices) / len(with_box_prices) if with_box_prices else 0
    avg_without = sum(without_box_prices) / len(without_box_prices) if without_box_prices else 0
    
    premium_abs = avg_with - avg_without if (avg_with > 0 and avg_without > 0) else 0
    premium_pct = (premium_abs / avg_without * 100) if (premium_abs > 0 and avg_without > 0) else 0
    
    box_analysis = BoxAnalysis(
        avg_with_box=round(avg_with, 2),
        avg_without_box=round(avg_without, 2),
        premium_abs=round(premium_abs, 2),
        premium_pct=round(premium_pct, 1),
        max_box_buy_price=round(premium_abs * 0.6, 2), # Suggest paying up to 60% of premium
        sample_size_with=len(with_box_prices),
        sample_size_without=len(without_box_prices)
    )

    # Projection (Simple: mean of last 5 prices)
    last_prices = prices[-5:] if len(prices) >= 5 else prices
    projected_price = sum(last_prices) / len(last_prices) if last_prices else 0
    
    projection = {
        "predicted_price": round(projected_price, 2),
        "confidence": 0.8 if len(prices) > 5 else 0.5,
        "min_expected": round(projected_price * 0.9, 2),
        "max_expected": round(projected_price * 1.1, 2)
    }
    
    # Nationalities Analytics - ONLY from successful CLOSED sales
    nat_stats = {}
    for l in lots:
        # Extra safety check (query already filters, but being defensive)
        if l.status != "CLOSED" or not l.nazionalita or l.nazionalita in UNKNOWN_NATIONALITIES or not l.prezzo_finale or l.prezzo_finale <= 0:
            continue
        country = l.nazionalita
        price = l.prezzo_finale or 0
        if price <= 0:
            continue
            
        if country not in nat_stats:
            nat_stats[country] = {"lots_won": 0, "total_spent": 0.0}
            
        nat_stats[country]["lots_won"] += 1
        nat_stats[country]["total_spent"] += price
        
    nationalities = []
    for country, d in nat_stats.items():
        avg = d["total_spent"] / d["lots_won"] if d["lots_won"] > 0 else 0
        nationalities.append(
            NationalityStat(
                country=country,
                lots_won=d["lots_won"],
                total_spent=round(d["total_spent"], 2),
                avg_price=round(avg, 2)
            )
        )
    # Sort primarily by volume, then by total spent
    nationalities.sort(key=lambda x: (x.lots_won, x.total_spent), reverse=True)

    return BottleAnalysis(
        distilleria=distilleria,
        stile=stile,
        eta=eta,
        formato=formato,
        stats=stats,
        history=history,
        projection=projection,
        comparison=comparison,
        box_analysis=box_analysis,
        nationalities=nationalities
    )


def calc_median(values):
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        return 0
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return float((sorted_vals[mid-1] + sorted_vals[mid]) / 2)


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    distilleria: str = None,
    stile: str = None,
    eta: str = None,
    formato: str = None,
    has_box: bool = None,
    filter_mode: str = "all",
    db: AsyncSession = Depends(get_db)
):
    context = []
    query = select(LotORM).where(LotORM.prezzo_finale != None, LotORM.prezzo_finale > 0)

    if filter_mode == "pure":
        query = query.where(or_(LotORM.is_mixed == False, LotORM.is_mixed == None))
    elif filter_mode == "mixed":
        query = query.where(LotORM.is_mixed == True)

    if distilleria:
        query = query.where(LotORM.distilleria == distilleria)
    if stile:
        query = query.where(LotORM.stile == stile)
    if eta:
        query = query.where(LotORM.eta == eta)
    if formato:
        query = query.where(LotORM.formato == formato)
    if has_box is not None:
        query = query.where(LotORM.has_box == has_box)

    query = query.order_by(LotORM.data_chiusura.asc())
    result = await db.execute(query)
    rows = result.scalars().all()

    prices = [r.prezzo_finale for r in rows if r.prezzo_finale is not None and r.prezzo_finale > 0]
    counts = len(rows)
    total_bottles = sum([(r.numero_bottiglie or 0) for r in rows])

    average_price = float(sum(prices)/len(prices)) if prices else 0
    median_price = calc_median(prices)
    min_price = float(min(prices)) if prices else 0
    max_price = float(max(prices)) if prices else 0

    # Grouping for series by year
    by_year = {}
    for r in rows:
        key = r.eta or 'Unknown'
        by_year.setdefault(key, []).append(r.prezzo_finale)

    series = []
    for key in sorted(by_year.keys()):
        bucket = [p for p in by_year[key] if p is not None and p > 0]
        if not bucket:
            continue
        series.append(RangePoint(
            key=key,
            average=float(sum(bucket)/len(bucket)),
            median=calc_median(bucket),
            count=len(bucket)
        ))

    # Trend score: simple derivative of avg prices by year
    sorted_series = sorted(series, key=lambda x: x.key)
    trend_score = 0.0
    if len(sorted_series) >= 2:
        first = sorted_series[0].average
        last = sorted_series[-1].average
        trend_score = ((last - first) / first * 100.0) if first > 0 else 0.0

    # Strategy prediction score: based on diff between single and bundle price per bottle
    singles = [r.prezzo_finale / (r.numero_bottiglie or 1) for r in rows if (r.numero_bottiglie or 0) == 1 and r.prezzo_finale > 0]
    bundles = [r.prezzo_finale / (r.numero_bottiglie or 1) for r in rows if (r.numero_bottiglie or 0) > 1 and r.prezzo_finale > 0]

    avg_single = float(sum(singles)/len(singles)) if singles else 0
    avg_bundle = float(sum(bundles)/len(bundles)) if bundles else 0

    strategy_score = 0
    if avg_single > 0 and avg_bundle > 0:
        ratio = min(avg_single, avg_bundle) / max(avg_single, avg_bundle)
        strategy_score = int(round((1 - ratio) * 5))

    if not singles and not bundles:
        strategy_score = 0

    best_strategy = StrategyComparison(
        individual_avg=round(avg_single,2),
        bundle_avg=round(avg_bundle,2),
        recommendation="BUNDLE" if avg_bundle > avg_single else "SINGLE",
        potential_gain_pct=round(abs(avg_bundle - avg_single) / (min(avg_single, avg_bundle) if min(avg_single, avg_bundle) > 0 else 1) * 100,2)
    )

    metrics = AggregateMetrics(
        distilleria=distilleria,
        stile=stile,
        eta=eta,
        formato=formato,
        has_box=has_box if has_box is not None else False,
        total_lots=counts,
        total_bottles=total_bottles,
        average_price=round(average_price, 2),
        median_price=round(median_price, 2),
        min_price=round(min_price, 2),
        max_price=round(max_price, 2),
        trend_score=round(trend_score, 2),
        strategy_score=strategy_score
    )

    return MetricsResponse(metrics=metrics, series=series, best_strategy=best_strategy)


@router.get("/hierarchy")
async def get_hierarchy(has_box: bool = None, db: AsyncSession = Depends(get_db)):
    q = select(LotORM.distilleria, LotORM.stile, LotORM.eta, LotORM.formato).where(
        LotORM.distilleria != None,
        LotORM.status == "CLOSED",
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0
    )
    if has_box is not None:
        q = q.where(LotORM.has_box == has_box)
    result = await db.execute(q)
    rows = result.all()

    hierarchy = {}
    for distilleria, stile, eta, formato in rows:
        if distilleria is None:
            continue
        m = hierarchy.setdefault(distilleria, {})
        t = m.setdefault(stile or "Unknown", {})
        v = t.setdefault(eta or "Unknown", set())
        if formato:
            v.add(formato)

    output = []
    for distilleria, tip_dict in sorted(hierarchy.items()):
        tipologie_list = []
        for stile, annate_dict in sorted(tip_dict.items()):
            annate_list = []
            for annata, formati in sorted(annate_dict.items()):
                annate_list.append({
                    "name": annata,
                    "formati": sorted(list(formati))
                })
            tipologie_list.append({
                "name": stile,
                "annate": annate_list
            })
        output.append({"name": distilleria, "tipologie": tipologie_list})

    return output


@router.get("/stats")
async def get_stats(
    distilleria: str,
    stile: str = None,
    eta: str = None,
    formato: str = None,
    has_box: bool = None,
    imbottigliatore: str = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(LotORM).where(LotORM.distilleria == distilleria)
    if imbottigliatore:
        query = filtro_imbottigliatore(query, imbottigliatore)
    if stile:
        query = query.where(LotORM.stile == stile)
    if eta:
        query = query.where(LotORM.eta == eta)
    if formato:
        query = query.where(LotORM.formato == formato)
    if has_box is not None:
        query = query.where(LotORM.has_box == has_box)
        
    query = query.order_by(LotORM.data_chiusura.asc())

    res = await db.execute(query)
    lots = res.scalars().all()

    if not lots:
        return []

    # prepare grouped by data_chiusura
    data_map = {}
    for l in lots:
        d = l.data_chiusura or "Unknown"
        if d is None:
            d = "Unknown"
        if l.prezzo_finale is None or l.prezzo_finale <= 0:
            continue
        data_map.setdefault(d, []).append(l.prezzo_finale)

    result = []
    for date in sorted(data_map.keys()):
        values = data_map[date]
        values_sorted = sorted(values)
        median = (values_sorted[len(values_sorted)//2] if len(values_sorted)%2==1
                  else (values_sorted[len(values_sorted)//2 - 1] + values_sorted[len(values_sorted)//2]) / 2)
        result.append({
            "data": date,
            "mean": float(sum(values)/len(values)) if values else 0.0,
            "median": float(median)
        })
    return result


def _linear_regression_predict(x_values, y_values):
    n = len(x_values)
    if n < 2:
        return 0.0, 0.0, 0.0
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    den = sum((x - x_mean) ** 2 for x in x_values)
    if den == 0:
        return 0.0, 0.0, 0.0
    slope = num / den
    intercept = y_mean - slope * x_mean
    y_predicted = [intercept + slope * x for x in x_values]
    # R^2
    ss_tot = sum((y - y_mean) ** 2 for y in y_values)
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(y_values, y_predicted))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return intercept, slope, max(0.0, min(1.0, r2))


@router.get("/predict")
async def get_predict(
    distilleria: str,
    stile: str,
    formato: str = None,
    has_box: bool = None,
    imbottigliatore: str = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(LotORM).where(
        LotORM.distilleria == distilleria,
        LotORM.stile == stile,
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0
    )
    if imbottigliatore:
        query = filtro_imbottigliatore(query, imbottigliatore)
    if formato:
        query = query.where(LotORM.formato == formato)
    if has_box is not None:
        query = query.where(LotORM.has_box == has_box)
        
    query = query.order_by(LotORM.data_chiusura.asc())

    res = await db.execute(query)
    rows = res.scalars().all()

    if len(rows) < 3:
        return {
            "prediction": None,
            "confidence": 0,
            "strategy": "INSUFFICIENT DATA",
            "count": len(rows)
        }

    y = [r.prezzo_finale for r in rows]
    x = list(range(1, len(y) + 1))

    intercept, slope, r2 = _linear_regression_predict(x, y)

    future_x = len(y) + 1
    pred_price = intercept + slope * future_x
    pred_price = max(0.0, float(pred_price))

    if r2 > 0.7:
        strategy = "BUY"
    elif r2 > 0.4:
        strategy = "HOLD"
    else:
        strategy = "AVOID"

    return {
        "prediction": round(pred_price, 2),
        "confidence": round(r2 * 5, 1),
        "strategy": strategy,
        "r2": round(r2, 3),
        "count": len(rows)
    }

@router.get("/top-nationalities", response_model=List[TopTradedBottleNationality])
async def get_top_nationalities(db: AsyncSession = Depends(get_db)):
    q = select(LotORM).where(
        LotORM.status == "CLOSED",
        known_nationality(),
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0
    )
    result = await db.execute(q)
    lots = result.scalars().all()

    groups = {}
    for l in lots:
        if not l.distilleria or not l.stile:
            continue
        key = (l.distilleria, l.stile)
        if key not in groups:
            groups[key] = []
        groups[key].append(l)

    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)[:10]

    output = []
    for (distilleria, stile), group_lots in sorted_groups:
        nat_stats = {}
        for l in group_lots:
            country = l.nazionalita
            if country not in nat_stats:
                nat_stats[country] = {"lots_won": 0, "total_spent": 0.0}
            nat_stats[country]["lots_won"] += 1
            nat_stats[country]["total_spent"] += l.prezzo_finale
            
        nationalities = []
        for country, d in nat_stats.items():
            avg = d["total_spent"] / d["lots_won"] if d["lots_won"] > 0 else 0
            nationalities.append(
                NationalityStat(
                    country=country,
                    lots_won=d["lots_won"],
                    total_spent=round(d["total_spent"], 2),
                    avg_price=round(avg, 2)
                )
            )
            
        nationalities.sort(key=lambda x: (x.lots_won, x.total_spent), reverse=True)
        
        output.append(
            TopTradedBottleNationality(
                distilleria=distilleria,
                stile=stile,
                total_lots=len(group_lots),
                nationalities=nationalities
            )
        )
        
    return output

@router.get("/nationalities")
async def get_nationalities(distilleria: str = None, db: AsyncSession = Depends(get_db)):
    q = select(LotORM).where(
        LotORM.status == "CLOSED",
        known_nationality(),
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0
    )
    if distilleria:
        q = q.where(LotORM.distilleria == distilleria)
        
    result = await db.execute(q)
    lots = result.scalars().all()
    
    # Group by distilleria and nationality
    nat_stats = {}
    for l in lots:
        if not l.distilleria:
            continue
        m = l.distilleria
        nat = l.nazionalita
        if m not in nat_stats:
            nat_stats[m] = {}
        if nat not in nat_stats[m]:
            nat_stats[m][nat] = 0
        nat_stats[m][nat] += 1
        
    # Convert to expected format
    output = {}
    for m, d in nat_stats.items():
        output[m] = [{"nationality": nat, "count": count} for nat, count in d.items()]
        
    if distilleria:
        return output.get(distilleria, [])
    return output


@router.get("/nationality-lots")
async def get_nationality_lots(
    country: str,
    distilleria: str = None,
    stile: str = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db)
):
    """
    Drill-through: i lotti chiusi e venduti attribuiti a una nazionalita'
    (stessi criteri dei grafici), opzionalmente filtrati per distilleria/stile.
    """
    q = select(LotORM).where(
        LotORM.status == "CLOSED",
        LotORM.prezzo_finale != None,
        LotORM.prezzo_finale > 0,
        LotORM.nazionalita == country,
    )
    if distilleria:
        q = q.where(LotORM.distilleria == distilleria)
    if stile:
        q = q.where(LotORM.stile == stile)
    q = q.order_by(LotORM.data_chiusura.desc())
    lots = (await db.execute(q)).scalars().all()

    prices = [l.prezzo_finale for l in lots]
    total = sum(prices)
    return {
        "country": country,
        "distilleria": distilleria,
        "stile": stile,
        "total_lots": len(lots),
        "total_spent": round(total, 2),
        "avg_price": round(total / len(lots), 2) if lots else 0,
        "lots": [
            {
                "id": l.id,
                "title": l.title,
                "distilleria": l.distilleria,
                "stile": l.stile,
                "eta": l.eta,
                "formato": l.formato,
                "numero_bottiglie": l.numero_bottiglie,
                "prezzo_finale": l.prezzo_finale,
                "currency": l.currency,
                "data_chiusura": l.data_chiusura,
                "numero_offerte": l.numero_offerte,
                "winner_username": l.winner_username,
                "has_box": l.has_box,
                "is_mixed": l.is_mixed,
                "url": l.url,
            }
            for l in lots[:limit]
        ],
    }


@router.get("/bottlers")
async def get_bottlers(distilleria: str = None, db: AsyncSession = Depends(get_db)):
    """Elenco imbottigliatori con numero di lotti (per i menu a discesa)."""
    q = select(LotORM.imbottigliatore, func.count()).group_by(LotORM.imbottigliatore)
    if distilleria:
        q = q.where(LotORM.distilleria == distilleria)
    rows = (await db.execute(q)).all()
    out = [{"name": name or "Original bottling", "count": n} for name, n in rows]
    merged = {}
    for r in out:
        merged[r["name"]] = merged.get(r["name"], 0) + r["count"]
    return sorted(({"name": k, "count": v} for k, v in merged.items()), key=lambda x: x["name"].casefold())
