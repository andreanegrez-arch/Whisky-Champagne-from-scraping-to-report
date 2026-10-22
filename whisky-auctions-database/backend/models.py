from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict
from datetime import datetime

class LotBase(BaseModel):
    distilleria: str = Field(...)
    imbottigliatore: Optional[str] = None
    stile: str = Field(...)
    numero_bottiglie: int = Field(...)
    formato: str = Field(...)
    eta: str = Field(...)
    data_chiusura: Optional[str] = Field(None)
    prezzo_riserva: str = Field(...)
    numero_offerte: int = Field(...)
    nazionalita: str = Field(...)
    prezzo_finale: Optional[float] = Field(None)
    costi_spedizione: Optional[str] = Field(None)
    title: str
    currency: Optional[str] = None
    status: str
    url: HttpUrl
    has_box: bool = False
    is_mixed: bool = False
    timestamp: datetime

    class Config:
        populate_by_name = True
        from_attributes = True

class Lot(LotBase):
    id: Optional[int] = None

class ScrapeStatus(BaseModel):
    is_running: bool
    last_run: Optional[datetime] = None
    progress: Optional[float] = None
    message: Optional[str] = None

class DistilleryStats(BaseModel):
    distilleria: Optional[str] = None
    prezzo_min: float
    prezzo_max: float
    prezzo_medio: float
    lotti_totali: int
    bottiglie_totali: int

class AnalysisSummary(BaseModel):
    total_lots: int
    sold_lots: int
    success_rate: float
    distillery_stats: List[DistilleryStats]

class HistoricalPrice(BaseModel):
    date: str
    price: float
    reserve: str
    num_bottles: int
    price_per_bottle: float
    has_box: bool = False
    url: str

class StrategyComparison(BaseModel):
    individual_avg: float
    bundle_avg: float
    recommendation: str
    potential_gain_pct: float

class BoxAnalysis(BaseModel):
    avg_with_box: float
    avg_without_box: float
    premium_abs: float
    premium_pct: float
    max_box_buy_price: float
    sample_size_with: int
    sample_size_without: int

class NationalityStat(BaseModel):
    country: str
    lots_won: int
    avg_price: float
    total_spent: float

class TopTradedBottleNationality(BaseModel):
    distilleria: str
    stile: str
    total_lots: int
    nationalities: List[NationalityStat]

class BottleAnalysis(BaseModel):
    distilleria: str
    stile: str
    eta: str
    formato: Optional[str] = None
    stats: DistilleryStats
    history: List[HistoricalPrice]
    projection: Dict[str, float] = Field(description="Simulated auction results for today")
    comparison: Optional[StrategyComparison] = None
    box_analysis: Optional[BoxAnalysis] = None
    nationalities: List[NationalityStat] = []


class AggregateMetrics(BaseModel):
    distilleria: Optional[str]
    stile: Optional[str]
    eta: Optional[str]
    formato: Optional[str]
    has_box: bool = False
    total_lots: int
    total_bottles: int
    average_price: float
    median_price: float
    min_price: float
    max_price: float
    trend_score: float
    strategy_score: int


class RangePoint(BaseModel):
    key: str
    average: float
    median: float
    count: int


class MetricsResponse(BaseModel):
    metrics: AggregateMetrics
    series: List[RangePoint]
    best_strategy: StrategyComparison

