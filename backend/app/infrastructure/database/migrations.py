"""Migraciones SQL ligeras ejecutadas en startup (compatible Render)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

logger = get_logger(__name__)


async def run_startup_migrations(engine: AsyncEngine) -> None:
    from app.core.config import get_settings

    if get_settings().database_url.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum e
                        JOIN pg_type t ON e.enumtypid = t.oid
                        WHERE t.typname = 'platform' AND e.enumlabel = 'tiktok'
                    ) THEN
                        ALTER TYPE platform ADD VALUE 'tiktok';
                    END IF;
                END $$;
                """
            )
        )
    logger.info("startup_migrations_applied", migrations=["platform_tiktok"])
