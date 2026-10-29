"""Run the tenant-scoped PostgreSQL warehouse refresh."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select, text

from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger("bi_refresh")


async def main() -> None:
    cutoff = date.today() - timedelta(days=90)
    failed_tenants: list[str] = []
    async with AsyncSessionLocal() as db:
        tenant_ids = list((await db.execute(select(Stream.tenant_id).distinct())).scalars())
        for tenant_id in tenant_ids:
            tenant = str(tenant_id)
            logger.info("warehouse refresh started tenant=%s", tenant)
            try:
                await db.execute(
                    text("CALL bi.refresh_warehouse(CAST(:tenant_id AS uuid), CAST(:from_date AS date))"),
                    {"tenant_id": tenant, "from_date": cutoff.isoformat()},
                )
                await db.commit()
                logger.info("warehouse refresh completed tenant=%s", tenant)
            except Exception:
                failed_tenants.append(tenant)
                await db.rollback()
                logger.exception("warehouse refresh failed tenant=%s", tenant)
    if failed_tenants:
        raise RuntimeError(
            "Warehouse refresh failed for tenant(s): " + ", ".join(failed_tenants)
        )


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("warehouse refresh failed")
        raise
