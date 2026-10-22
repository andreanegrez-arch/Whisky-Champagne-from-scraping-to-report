from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, Boolean
from datetime import datetime
import os

# Database URL (SQLite)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT_DIR, "Whisky SQLite.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class LotORM(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    distilleria: Mapped[str] = mapped_column(String)
    # Imbottigliatore indipendente (es. "Signatory Vintage") o "Original bottling"
    imbottigliatore: Mapped[str] = mapped_column(String, nullable=True)
    stile: Mapped[str] = mapped_column(String)
    numero_bottiglie: Mapped[int] = mapped_column(Integer)
    formato: Mapped[str] = mapped_column(String)
    eta: Mapped[str] = mapped_column(String)
    data_chiusura: Mapped[str] = mapped_column(String, nullable=True)
    prezzo_riserva: Mapped[str] = mapped_column(String)
    numero_offerte: Mapped[int] = mapped_column(Integer)
    nazionalita: Mapped[str] = mapped_column(String)
    prezzo_finale: Mapped[float] = mapped_column(Float, nullable=True)
    # Esito ufficiale dell'asta (vedi bidding_api.py): venduto / invenduto / in corso /
    # non verificabile. prezzo_finale e' il prezzo di vendita solo se esito = venduto.
    esito: Mapped[str] = mapped_column(String, nullable=True)
    # Offerta piu' alta ricevuta (anche se il lotto non e' stato venduto)
    offerta_massima: Mapped[float] = mapped_column(Float, nullable=True)
    costi_spedizione: Mapped[str] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String, unique=True)
    has_box: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mixed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    winner_username: Mapped[str] = mapped_column(String, nullable=True)
    winner_id: Mapped[str] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    # Only run create_all if the database file does not exist to avoid locking issues
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return
    # Migrazione leggera: colonne aggiunte dopo la creazione del database
    async with engine.begin() as conn:
        cols = {row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(lots)")).fetchall()}
        if "imbottigliatore" not in cols:
            await conn.exec_driver_sql("ALTER TABLE lots ADD COLUMN imbottigliatore VARCHAR")
    # Migrazione leggera: colonne esito / offerta_massima (11/10/2026)
    async with engine.begin() as conn:
        cols = {row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(lots)")).fetchall()}
        if "esito" not in cols:
            await conn.exec_driver_sql("ALTER TABLE lots ADD COLUMN esito VARCHAR")
        if "offerta_massima" not in cols:
            await conn.exec_driver_sql("ALTER TABLE lots ADD COLUMN offerta_massima FLOAT")

async def get_db():
    async with async_session() as session:
        yield session
