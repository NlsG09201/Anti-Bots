import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.infrastructure.database.url import prepare_asyncpg_url

settings = get_settings()
_db_url, _connect_args = prepare_asyncpg_url(settings.database_url)

_engine_kwargs: dict = {"echo": settings.app_debug, "connect_args": _connect_args}
if "sqlite" not in settings.database_url:
    # Pool pequeño en Render free + Neon pooler
    pool_size = 5 if os.getenv("RENDER") else 20
    _engine_kwargs.update(
        pool_size=pool_size,
        max_overflow=5 if os.getenv("RENDER") else 10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

engine = create_async_engine(_db_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
