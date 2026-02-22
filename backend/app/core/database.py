import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

resolved_database_url = settings.resolved_database_url
resolved_database_url_source = settings.resolved_database_url_source
logger.info(
    "Database URL resolved",
    extra={
        "database_url_source": resolved_database_url_source,
        "database_host": settings.postgres_host if resolved_database_url_source == "postgres_fallback" else None,
        "database_port": settings.postgres_port if resolved_database_url_source == "postgres_fallback" else None,
        "database_name": settings.postgres_db if resolved_database_url_source == "postgres_fallback" else None,
    },
)

engine = create_async_engine(resolved_database_url, future=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
