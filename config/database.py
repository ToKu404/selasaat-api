# config/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

# Ganti dengan credential database Anda
DATABASE_URL = "mysql+aiomysql://selasaat:s4n%402ooImysql@103.103.20.118:3306/selasaat"
# DATABASE_URL = "mysql+aiomysql://root@localhost:3306/selasaat"

# Engine untuk koneksi async
engine = create_async_engine(
    DATABASE_URL,
    echo=False,                # Set True kalau mau debug query
    pool_pre_ping=True,        # Cek koneksi sebelum dipakai
    pool_recycle=3600,         # Recycle koneksi tiap 1 jam
    pool_size=10,              # Maksimal koneksi dalam pool
    max_overflow=20,           # Koneksi ekstra jika pool penuh
    pool_timeout=30            # Timeout saat ambil koneksi
)

# Factory untuk session
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Base untuk model
Base = declarative_base()


# Dependency untuk FastAPI
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
