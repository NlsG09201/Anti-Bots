"""Compare the BI warehouse with operational PostgreSQL data, per tenant."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, text

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.database.models import Stream  # noqa: E402
from app.infrastructure.database.session import AsyncSessionLocal  # noqa: E402


COUNT_CHECKS = {
    "streams": (
        "SELECT count(*) FROM public.streams WHERE tenant_id = :tenant_id",
        "SELECT count(*) FROM bi.dim_stream WHERE tenant_id = :tenant_id",
    ),
    "viewer_sessions": (
        """SELECT count(*) FROM public.viewer_sessions v
           JOIN public.streams s ON s.id = v.stream_id
           WHERE s.tenant_id = :tenant_id""",
        """SELECT count(*) FROM bi.fact_viewer_session f
           JOIN bi.dim_stream s USING (stream_id)
           WHERE s.tenant_id = :tenant_id""",
    ),
    "attacks": (
        """SELECT count(*) FROM public.attacks a
           JOIN public.streams s ON s.id = a.stream_id
           WHERE s.tenant_id = :tenant_id""",
        """SELECT count(*) FROM bi.fact_attack f
           JOIN bi.dim_stream s USING (stream_id)
           WHERE s.tenant_id = :tenant_id""",
    ),
}


async def validate() -> bool:
    all_ok = True

    async with AsyncSessionLocal() as db:
        # Use PostgreSQL's current_date, matching ETL and avoiding a one-day
        # validation-window mismatch with the workstation timezone.
        from_date = (
            await db.execute(text("SELECT current_date - 90"))
        ).scalar_one()
        tenant_ids = list(
            (await db.execute(select(Stream.tenant_id).distinct())).scalars()
        )
        if not tenant_ids:
            print("FAIL no tenants found in public.streams")
            return False

        for tenant_id in tenant_ids:
            tenant = str(tenant_id)
            params = {"tenant_id": tenant}
            print(f"tenant={tenant}")

            for name, (source_sql, warehouse_sql) in COUNT_CHECKS.items():
                source_count = int((await db.execute(text(source_sql), params)).scalar_one())
                warehouse_count = int(
                    (await db.execute(text(warehouse_sql), params)).scalar_one()
                )
                matches = source_count == warehouse_count
                all_ok &= matches
                status = "PASS" if matches else "FAIL"
                print(
                    f"  {status} {name}: source={source_count} warehouse={warehouse_count}"
                )

            expected_snapshots = int(
                (
                    await db.execute(
                        text(
                            """SELECT count(*) FROM public.streams
                               WHERE tenant_id = :tenant_id"""
                        ),
                        params,
                    )
                ).scalar_one()
            )
            actual_snapshots = int(
                (
                    await db.execute(
                        text(
                            """SELECT count(*) FROM bi.fact_stream_snapshot f
                               JOIN bi.dim_stream s USING (stream_id)
                               WHERE s.tenant_id = :tenant_id
                                 AND f.snapshot_date = current_date"""
                        ),
                        params,
                    )
                ).scalar_one()
            )
            matches = expected_snapshots == actual_snapshots
            all_ok &= matches
            status = "PASS" if matches else "FAIL"
            print(
                f"  {status} today_snapshots: source_streams={expected_snapshots} "
                f"warehouse={actual_snapshots}"
            )

            chat_source_sql = text(
                """SELECT count(*) AS messages,
                          count(DISTINCT (e.stream_id, e.created_at::date,
                                          lower(e.event_type))) AS groups
                   FROM public.stream_events e
                   JOIN public.streams s ON s.id = e.stream_id
                   WHERE s.tenant_id = :tenant_id
                     AND e.created_at >= :from_date
                     AND lower(e.event_type) IN
                       ('chat_message', 'message', 'follow', 'user_follow',
                        'viewer_join', 'join')"""
            )
            chat_warehouse_sql = text(
                """SELECT coalesce(sum(c.messages), 0) AS messages, count(*) AS groups
                   FROM bi.fact_chat_activity c
                   JOIN bi.dim_stream s USING (stream_id)
                   WHERE s.tenant_id = :tenant_id AND c.activity_date >= :from_date"""
            )
            chat_params = {**params, "from_date": from_date}
            source_chat = (await db.execute(chat_source_sql, chat_params)).one()
            warehouse_chat = (await db.execute(chat_warehouse_sql, chat_params)).one()
            matches = (
                int(source_chat.messages) == int(warehouse_chat.messages)
                and int(source_chat.groups) == int(warehouse_chat.groups)
            )
            all_ok &= matches
            status = "PASS" if matches else "FAIL"
            print(
                f"  {status} chat_activity_since_{from_date}: "
                f"source_messages={source_chat.messages} "
                f"warehouse_messages={warehouse_chat.messages} "
                f"source_groups={source_chat.groups} "
                f"warehouse_groups={warehouse_chat.groups}"
            )

    print("VALIDATION PASS" if all_ok else "VALIDATION FAIL")
    return all_ok


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(validate()) else 1)
