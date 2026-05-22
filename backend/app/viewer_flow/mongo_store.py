"""MongoDB persistence for viewer flow snapshots (optional)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.mongodb.client import get_mongo_db
from app.viewer_flow.schemas import ViewerFlowMetrics, ViewerFlowStreamSnapshot

logger = get_logger(__name__)

COL_SNAPSHOTS = "viewer_flow_snapshots"
COL_EVENTS = "viewer_flow_events"
COL_ENTITIES = "viewer_flow_entities"


async def ensure_viewer_flow_indexes() -> None:
    db = await get_mongo_db()
    if db is None:
        return
    await db[COL_SNAPSHOTS].create_index(
        [("tenant_id", 1), ("stream_id", 1)], unique=True
    )
    await db[COL_EVENTS].create_index(
        [("tenant_id", 1), ("stream_id", 1), ("ts", -1)]
    )
    await db[COL_ENTITIES].create_index(
        [("tenant_id", 1), ("canonical_username", 1)]
    )
    logger.info("viewer_flow_mongo_indexes_ready")


class ViewerFlowMongoStore:
    async def upsert_snapshot(
        self,
        tenant_id: str,
        snapshot: ViewerFlowStreamSnapshot,
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        doc = {
            "tenant_id": tenant_id,
            "stream_id": snapshot.metrics.stream_id,
            "platform": snapshot.metrics.platform,
            "metrics": snapshot.metrics.model_dump(),
            "suspicious_count": len(snapshot.suspicious_viewers),
            "updated_at": datetime.now(timezone.utc),
        }
        await db[COL_SNAPSHOTS].update_one(
            {"tenant_id": tenant_id, "stream_id": snapshot.metrics.stream_id},
            {"$set": doc},
            upsert=True,
        )

    async def list_snapshots(self, tenant_id: str) -> List[ViewerFlowMetrics]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = db[COL_SNAPSHOTS].find({"tenant_id": tenant_id}).limit(50)
        out: List[ViewerFlowMetrics] = []
        async for doc in cursor:
            m = doc.get("metrics")
            if m:
                out.append(ViewerFlowMetrics.model_validate(m))
        return out

    async def cross_platform_usernames(
        self, tenant_id: str, username: str
    ) -> int:
        db = await get_mongo_db()
        if db is None:
            return 0
        key = username.lower().strip()
        count = await db[COL_ENTITIES].count_documents(
            {"tenant_id": tenant_id, "canonical_username": key}
        )
        return int(count)

    async def upsert_entity_cross(
        self,
        tenant_id: str,
        *,
        username: str,
        platform: str,
        stream_id: str,
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        key = username.lower().strip()
        await db[COL_ENTITIES].update_one(
            {"tenant_id": tenant_id, "canonical_username": key},
            {
                "$addToSet": {
                    "platforms": platform,
                    "stream_ids": stream_id,
                },
                "$set": {"updated_at": datetime.now(timezone.utc)},
                "$setOnInsert": {"canonical_username": key, "tenant_id": tenant_id},
            },
            upsert=True,
        )
