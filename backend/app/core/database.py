from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log SQL queries if in debug mode
    future=True,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that yields an async database session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
