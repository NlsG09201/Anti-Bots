"""Run the tenant-scoped PostgreSQL warehouse refresh."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, text

from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger("bi_refresh")


async def main() -> None:
    failed_tenants: list[str] = []
    async with AsyncSessionLocal() as db:
        # Keep the load window aligned with PostgreSQL current_date, regardless
        # of the container or workstation timezone.
        cutoff = (await db.execute(text("SELECT current_date - 90"))).scalar_one()
        tenant_ids = list(
            (await db.execute(select(Stream.tenant_id).distinct())).scalars()
        )
        for tenant_id in tenant_ids:
            tenant = str(tenant_id)
            logger.info("warehouse refresh started tenant=%s", tenant)
            try:
                await db.execute(
                    text(
                        "CALL bi.refresh_warehouse("
                        "CAST(:tenant_id AS uuid), CAST(:from_date AS date))"
                    ),
                    {"tenant_id": tenant_id, "from_date": cutoff},
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
