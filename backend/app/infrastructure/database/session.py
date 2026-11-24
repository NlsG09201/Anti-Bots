from collections.abc import AsyncGenerator
from asyncio import to_thread

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.infrastructure.database.azure_postgres import (
    create_managed_identity_connector,
    create_passwordless_url,
)
from app.infrastructure.database.url import prepare_asyncpg_url

settings = get_settings()
_db_url, _connect_args = prepare_asyncpg_url(settings.database_url)
_azure_credential = None

_engine_kwargs: dict = {"echo": settings.app_debug, "connect_args": _connect_args}
if "sqlite" not in settings.database_url:
    _engine_kwargs.update(
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_pre_ping=True,
        pool_recycle=settings.database_pool_recycle_seconds,
    )

if settings.database_auth_mode == "managed_identity":
    from azure.identity import DefaultAzureCredential

    _azure_credential = DefaultAzureCredential()
    _engine_kwargs.pop("connect_args")
    _engine_kwargs["async_creator"] = create_managed_identity_connector(
        settings.database_url,
        _azure_credential,
    )
    _db_url = create_passwordless_url(_db_url)

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


async def dispose_database() -> None:
    await engine.dispose()
    if _azure_credential is not None:
        await to_thread(_azure_credential.close)
