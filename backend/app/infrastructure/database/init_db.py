import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger
from app.infrastructure.database.base import Base

logger = get_logger(__name__)


async def init_database(engine: AsyncEngine, *, max_attempts: int = 10) -> None:
    """Conecta a Neon con reintentos (cold start en Render free tier)."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            if attempt > 1:
                logger.info("database_connected_after_retry", attempt=attempt)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "database_connect_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            if attempt < max_attempts:
                await asyncio.sleep(min(3 * attempt, 15))
    assert last_error is not None
    raise last_error
