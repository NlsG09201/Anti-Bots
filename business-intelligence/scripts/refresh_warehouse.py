"""Daily tenant-scoped PostgreSQL warehouse ETL."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select, text

from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bi_refresh")


async def main() -> None:
    cutoff = date.today() - timedelta(days=90)
    async with AsyncSessionLocal() as db:
        tenant_ids = list((await db.execute(select(Stream.tenant_id).distinct())).scalars())
        for tenant_id in tenant_ids:
            tenant = str(tenant_id)
            logger.info("warehouse refresh started tenant=%s", tenant)
            await db.execute(
                text("CALL bi.refresh_warehouse(CAST(:tenant_id AS uuid), CAST(:from_date AS date))"),
                {"tenant_id": tenant, "from_date": cutoff.isoformat()},
            )
            await db.commit()
            logger.info("warehouse refresh completed tenant=%s", tenant)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("warehouse refresh failed")
        raise
