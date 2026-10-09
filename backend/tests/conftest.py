import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-minimum-32-characters-long")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-minimum-32-chars")
os.environ.setdefault("AES_ENCRYPTION_KEY", "test-aes-encryption-key-32bytes!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")

from app.infrastructure.database.base import Base
from app.main import app
from app.infrastructure.database.session import get_db

# La aplicación exportada envuelve FastAPI con CORS para cubrir también errores 500.
fastapi_app = app.app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from unittest.mock import AsyncMock, patch
    from app.infrastructure.cache.redis_client import RedisCache

    async def override_get_db():
        yield db_session

    async def mock_check_rate_limit(self, identifier, limit, window):
        return True, 1

    async def mock_is_blacklisted(self, jti):
        return False

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with patch.object(RedisCache, "check_rate_limit", mock_check_rate_limit), \
         patch.object(RedisCache, "is_blacklisted", mock_is_blacklisted), \
         patch.object(RedisCache, "get", AsyncMock(return_value=None)), \
         patch.object(RedisCache, "set", AsyncMock()), \
         patch.object(RedisCache, "delete", AsyncMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    fastapi_app.dependency_overrides.clear()
