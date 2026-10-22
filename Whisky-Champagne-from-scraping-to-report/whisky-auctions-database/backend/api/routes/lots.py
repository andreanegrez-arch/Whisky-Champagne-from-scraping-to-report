from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional
from database import get_db, LotORM
from models import Lot

ORIGINAL_BOTTLING = "Original bottling"


def filtro_imbottigliatore(query, imbottigliatore: str):
    """Valori speciali: "__independent__" (tutti gli indipendenti), "__original__" (ufficiali)."""
    if imbottigliatore == "__independent__":
        return query.where(LotORM.imbottigliatore != None, LotORM.imbottigliatore != ORIGINAL_BOTTLING)
    if imbottigliatore == "__original__":
        return query.where((LotORM.imbottigliatore == None) | (LotORM.imbottigliatore == ORIGINAL_BOTTLING))
    return query.where(LotORM.imbottigliatore == imbottigliatore)

router = APIRouter()

@router.get("/", response_model=List[Lot])
async def get_lots(
    skip: int = Query(0, ge=0),
    limit: int = Query(2000, ge=1, le=200000),
    distilleria: Optional[str] = None,
    eta: Optional[str] = None,
    imbottigliatore: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(LotORM).offset(skip).limit(limit).order_by(LotORM.distilleria.asc(), LotORM.stile.asc(), LotORM.eta.asc())
    if distilleria:
        query = query.where(LotORM.distilleria.ilike(f"%{distilleria}%"))
    if eta:
        query = query.where(LotORM.eta == eta)
    if imbottigliatore:
        query = filtro_imbottigliatore(query, imbottigliatore)
    
    result = await db.execute(query)
    lots = result.scalars().all()
    return lots

@router.get("/count")
async def get_lots_count(
    distilleria: Optional[str] = None,
    eta: Optional[str] = None,
    imbottigliatore: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(func.count()).select_from(LotORM)
    if distilleria:
        query = query.where(LotORM.distilleria.ilike(f"%{distilleria}%"))
    if eta:
        query = query.where(LotORM.eta == eta)
    if imbottigliatore:
        query = filtro_imbottigliatore(query, imbottigliatore)
    
    result = await db.execute(query)
    return {"count": result.scalar()}
