"""MongoDB persistence for live competitive intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.mongodb.client import get_mongo_db

logger = get_logger(__name__)

COL_SNAPSHOTS = "live_intel_snapshots"
COL_SESSIONS = "live_intel_sessions"
COL_HISTORY = "live_intel_metric_history"
COL_ANOMALIES = "live_intel_anomalies"


async def ensure_live_intel_indexes() -> None:
    db = await get_mongo_db()
    if db is None:
        return
    await db[COL_SNAPSHOTS].create_index(
        [("tenant_id", 1), ("stream_id", 1)], unique=True
    )
    await db[COL_HISTORY].create_index(
        [("tenant_id", 1), ("stream_id", 1), ("ts", -1)]
    )
    await db[COL_HISTORY].create_index(
        "ts", expireAfterSeconds=60 * 60 * 24 * 30
    )
    await db[COL_SESSIONS].create_index(
        [("tenant_id", 1), ("stream_id", 1), ("started_at", -1)]
    )
    await db[COL_ANOMALIES].create_index(
        [("tenant_id", 1), ("created_at", -1)]
    )
    logger.info("live_intel_mongo_indexes_ready")


class LiveIntelMongoStore:
    async def upsert_snapshot(
        self, tenant_id: str, stream_id: str, doc: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_SNAPSHOTS].update_one(
            {"tenant_id": tenant_id, "stream_id": stream_id},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "stream_id": stream_id,
                    "updated_at": datetime.now(timezone.utc),
                    **doc,
                }
            },
            upsert=True,
        )

    async def append_history(
        self, tenant_id: str, stream_id: str, point: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_HISTORY].insert_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "ts": datetime.now(timezone.utc),
                **point,
            }
        )

    async def start_session(
        self, tenant_id: str, stream_id: str, meta: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_SESSIONS].insert_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "started_at": datetime.now(timezone.utc),
                "ended_at": None,
                **meta,
            }
        )

    async def end_session(self, tenant_id: str, stream_id: str) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_SESSIONS].update_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "ended_at": None,
            },
            {"$set": {"ended_at": datetime.now(timezone.utc)}},
        )

    async def record_anomaly(
        self, tenant_id: str, stream_id: str, anomaly: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_ANOMALIES].insert_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "created_at": datetime.now(timezone.utc),
                **anomaly,
            }
        )

    async def list_snapshots(self, tenant_id: str) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = db[COL_SNAPSHOTS].find({"tenant_id": tenant_id})
        return [dict(d) async for d in cursor]

    async def get_history(
        self,
        tenant_id: str,
        stream_id: str,
        *,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = (
            db[COL_HISTORY]
            .find({"tenant_id": tenant_id, "stream_id": stream_id})
            .sort("ts", -1)
            .limit(limit)
        )
        return [dict(d) async for d in cursor]

    async def recent_anomalies(
        self, tenant_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = (
            db[COL_ANOMALIES]
            .find({"tenant_id": tenant_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [dict(d) async for d in cursor]
