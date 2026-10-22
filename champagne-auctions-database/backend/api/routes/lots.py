from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional
from database import get_db, LotORM
from models import Lot

router = APIRouter()

@router.get("/", response_model=List[Lot])
async def get_lots(
    skip: int = Query(0, ge=0),
    limit: int = Query(2000, ge=1, le=200000),
    maison: Optional[str] = None,
    vintage: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(LotORM).offset(skip).limit(limit).order_by(LotORM.maison.asc(), LotORM.tipologia.asc(), LotORM.vintage.asc())
    if maison:
        query = query.where(LotORM.maison.ilike(f"%{maison}%"))
    if vintage:
        query = query.where(LotORM.vintage == vintage)
    
    result = await db.execute(query)
    lots = result.scalars().all()
    return lots

@router.get("/count")
async def get_lots_count(
    maison: Optional[str] = None,
    vintage: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(func.count()).select_from(LotORM)
    if maison:
        query = query.where(LotORM.maison.ilike(f"%{maison}%"))
    if vintage:
        query = query.where(LotORM.vintage == vintage)
    
    result = await db.execute(query)
    return {"count": result.scalar()}
