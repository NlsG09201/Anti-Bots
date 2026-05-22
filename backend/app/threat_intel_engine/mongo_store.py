"""MongoDB persistence for global threat intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.mongodb.client import get_mongo_db

logger = get_logger(__name__)

COL_ENTITIES = "threat_entities"
COL_CROSS_LINKS = "cross_platform_links"
COL_ENGAGEMENT = "engagement_metrics"
COL_CHAT_FP = "chat_patterns"
COL_PREDICTIONS = "ai_predictions"
COL_GRAPH_EDGES = "graph_edges"


async def ensure_indexes() -> None:
    db = await get_mongo_db()
    if db is None:
        return
    await db[COL_ENTITIES].create_index(
        [("tenant_id", 1), ("entity_key", 1)], unique=True
    )
    await db[COL_ENTITIES].create_index([("threat_score", -1)])
    await db[COL_ENTITIES].create_index([("bot_probability", -1)])
    await db[COL_CROSS_LINKS].create_index(
        [("tenant_id", 1), ("canonical_username", 1)]
    )
    await db[COL_ENGAGEMENT].create_index(
        [("tenant_id", 1), ("stream_id", 1)], unique=True
    )
    await db[COL_CHAT_FP].create_index(
        [("tenant_id", 1), ("entity_key", 1), ("stream_id", 1)]
    )
    await db[COL_PREDICTIONS].create_index(
        [("tenant_id", 1), ("stream_id", 1), ("created_at", -1)]
    )
    await db[COL_GRAPH_EDGES].create_index(
        [("tenant_id", 1), ("stream_id", 1), ("updated_at", -1)]
    )
    logger.info("threat_intel_mongo_indexes_ready")


class ThreatIntelMongoStore:
    async def upsert_entity(
        self,
        tenant_id: str,
        entity_key: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        db = await get_mongo_db()
        if db is None:
            return patch
        now = datetime.now(timezone.utc)
        doc = {
            "tenant_id": tenant_id,
            "entity_key": entity_key,
            "updated_at": now,
            **patch,
        }
        await db[COL_ENTITIES].update_one(
            {"tenant_id": tenant_id, "entity_key": entity_key},
            {
                "$set": doc,
                "$inc": {"activity_count": 1},
                "$setOnInsert": {"first_seen": now},
            },
            upsert=True,
        )
        result = await db[COL_ENTITIES].find_one(
            {"tenant_id": tenant_id, "entity_key": entity_key}
        )
        return dict(result) if result else doc

    async def get_entity(
        self, tenant_id: str, entity_key: str
    ) -> Optional[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return None
        doc = await db[COL_ENTITIES].find_one(
            {"tenant_id": tenant_id, "entity_key": entity_key}
        )
        return dict(doc) if doc else None

    async def top_threat_entities(
        self, tenant_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = db[COL_ENTITIES].find({"tenant_id": tenant_id}).sort(
            "threat_score", -1
        ).limit(limit)
        return [dict(d) async for d in cursor]

    async def save_engagement(
        self, tenant_id: str, stream_id: str, metrics: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_ENGAGEMENT].update_one(
            {"tenant_id": tenant_id, "stream_id": stream_id},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "stream_id": stream_id,
                    "updated_at": datetime.now(timezone.utc),
                    **metrics,
                }
            },
            upsert=True,
        )

    async def get_engagement(
        self, tenant_id: str, stream_id: str
    ) -> Optional[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return None
        doc = await db[COL_ENGAGEMENT].find_one(
            {"tenant_id": tenant_id, "stream_id": stream_id}
        )
        return dict(doc) if doc else None

    async def append_chat_pattern(
        self,
        tenant_id: str,
        entity_key: str,
        stream_id: str,
        message: str,
        analysis: Dict[str, Any],
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_CHAT_FP].update_one(
            {
                "tenant_id": tenant_id,
                "entity_key": entity_key,
                "stream_id": stream_id,
            },
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "entity_key": entity_key,
                    "stream_id": stream_id,
                    "updated_at": datetime.now(timezone.utc),
                    "last_analysis": analysis,
                },
                "$push": {
                    "recent_messages": {
                        "$each": [message[:500]],
                        "$slice": -30,
                    }
                },
            },
            upsert=True,
        )

    async def save_prediction(
        self, tenant_id: str, stream_id: str, prediction: Dict[str, Any]
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_PREDICTIONS].insert_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "created_at": datetime.now(timezone.utc),
                **prediction,
            }
        )

    async def link_cross_platform(
        self,
        tenant_id: str,
        canonical_username: str,
        platform: str,
        entity_key: str,
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_CROSS_LINKS].update_one(
            {"tenant_id": tenant_id, "canonical_username": canonical_username},
            {
                "$addToSet": {
                    "platforms": platform,
                    "entity_keys": entity_key,
                },
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    async def cross_platform_matches(
        self, tenant_id: str, username: str
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        un = username.lower().strip()
        cursor = db[COL_CROSS_LINKS].find(
            {"tenant_id": tenant_id, "canonical_username": un}
        )
        return [dict(d) async for d in cursor]

    async def replace_graph_edges(
        self,
        tenant_id: str,
        stream_id: str,
        edges: List[Dict[str, Any]],
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        col = db[COL_GRAPH_EDGES]
        await col.delete_many({"tenant_id": tenant_id, "stream_id": stream_id})
        if edges:
            now = datetime.now(timezone.utc)
            await col.insert_many(
                [
                    {
                        "tenant_id": tenant_id,
                        "stream_id": stream_id,
                        "updated_at": now,
                        **e,
                    }
                    for e in edges[:500]
                ]
            )

    async def get_graph_edges(
        self, tenant_id: str, stream_id: str
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = db[COL_GRAPH_EDGES].find(
            {"tenant_id": tenant_id, "stream_id": stream_id}
        ).limit(500)
        return [dict(d) async for d in cursor]

    async def global_stats(self, tenant_id: str) -> Dict[str, Any]:
        db = await get_mongo_db()
        if db is None:
            return {"entities": 0, "high_threat": 0, "cross_platform": 0}
        entities = await db[COL_ENTITIES].count_documents({"tenant_id": tenant_id})
        high = await db[COL_ENTITIES].count_documents(
            {"tenant_id": tenant_id, "threat_score": {"$gte": 70}}
        )
        cross = await db[COL_CROSS_LINKS].count_documents({"tenant_id": tenant_id})
        return {
            "entities": entities,
            "high_threat": high,
            "cross_platform": cross,
        }
