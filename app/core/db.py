from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from .config import settings


def async_url() -> str:
    """Return the DATABASE_URL with the asyncpg driver scheme for SQLAlchemy."""
    url = settings.database_url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgres+asyncpg://" + url[len("postgres://"):]
    return url


# NullPool mirrors the fresh-connection-per-operation pattern used by the Redis
# store: asyncpg connections are bound to the loop that created them, and loops
# may differ across requests (e.g. under test clients).
engine = create_async_engine(async_url(), poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_all() -> None:
    """Create all tables from the SQLModel metadata (used by tests, not the app)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session