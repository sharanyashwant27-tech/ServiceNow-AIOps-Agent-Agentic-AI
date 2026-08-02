from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.infrastructure.db.models import Base

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _ensure_ticket_columns(conn) -> None:
    """Add canonical Ticket entity columns on existing SQLite DBs."""
    url = str(settings.database_url)
    if "sqlite" not in url:
        return
    result = await conn.execute(text("PRAGMA table_info(tickets)"))
    existing = {row[1] for row in result.fetchall()}
    alters = []
    if "embeddings" not in existing:
        alters.append("ALTER TABLE tickets ADD COLUMN embeddings JSON DEFAULT '[]'")
    if "knowledge_links" not in existing:
        alters.append("ALTER TABLE tickets ADD COLUMN knowledge_links JSON DEFAULT '[]'")
    if "related_incidents" not in existing:
        alters.append("ALTER TABLE tickets ADD COLUMN related_incidents JSON DEFAULT '[]'")
    for stmt in alters:
        await conn.execute(text(stmt))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_ticket_columns(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
