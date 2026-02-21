import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, engine, get_db
from app.main import app

# Ensure tests run with testing env configuration (if handled by config.py)
os.environ["APP_ENV"] = "testing"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fixture for an isolated database session.
    Rolls back the transaction after the test to keep the DB clean.

    Also overrides the app's get_db dependency so that HTTP calls made
    through async_client share this same connection and transaction.
    Any commits inside the app during a test create/release savepoints
    instead of real commits, so all writes are fully rolled back at the end.
    """
    connection = await engine.connect()
    transaction = await connection.begin()

    # We bind the sessionmaker to the specific connection we opened
    # so we can roll back the outermost transaction at the end.
    session = AsyncSessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture for an async HTTPX test client hooked to the FastAPI app.
    Depends on db_session so the get_db override is active before the
    client is created and the app handles requests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
