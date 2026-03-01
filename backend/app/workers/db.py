"""
Database session factory for Celery workers.

Celery tasks use asyncio.run() which creates and DESTROYS event loops.
The main app's connection pool keeps connections tied to dead loops.

Solution: NullPool — no connection recycling. Each task gets a fresh
connection and truly closes it when done. Zero stale references.

Usage in tasks:
    from app.workers.db import worker_session

    async with worker_session() as db:
        result = await db.execute(...)
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

worker_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,  # No recycling — fresh connection per task
)

worker_session = async_sessionmaker(
    worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)