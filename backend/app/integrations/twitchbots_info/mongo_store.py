"""MongoDB persistence for TwitchBots.info verifications and SOC detections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.mongodb.client import get_mongo_db
from app.integrations.twitchbots_info.schemas import (
    TwitchBotsBotRecord,
    TwitchBotsOverviewStats,
    TwitchBotsVerificationResult,
)

logger = get_logger(__name__)

COL_PROFILES = "twitchbots_profiles"
COL_VERIFICATIONS = "twitchbots_verifications"
COL_DETECTIONS = "twitchbots_detections"
COL_STATS = "twitchbots_tenant_stats"


async def ensure_twitchbots_info_indexes() -> None:
    db = await get_mongo_db()
    if db is None:
        return
    await db[COL_PROFILES].create_index("twitch_id", unique=True)
    await db[COL_PROFILES].create_index("username")
    await db[COL_VERIFICATIONS].create_index(
        [("tenant_id", 1), ("username", 1), ("verified_at", -1)]
    )
    await db[COL_DETECTIONS].create_index(
        [("tenant_id", 1), ("detected_at", -1)]
    )
    await db[COL_DETECTIONS].create_index(
        "detected_at", expireAfterSeconds=60 * 60 * 24 * 90
    )
    logger.info("twitchbots_info_mongo_indexes_ready")


class TwitchBotsInfoMongoStore:
    async def upsert_profile(self, record: TwitchBotsBotRecord) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        await db[COL_PROFILES].update_one(
            {"twitch_id": record.twitch_id},
            {
                "$set": {
                    "twitch_id": record.twitch_id,
                    "username": record.username,
                    "type_id": record.type_id,
                    "type_name": record.type_name,
                    "channel_id": record.channel_id,
                    "channel_name": record.channel_name,
                    "last_update": record.last_update,
                    "canonical_url": record.canonical_url,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def record_verification(
        self,
        tenant_id: str,
        result: TwitchBotsVerificationResult,
        *,
        stream_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        doc: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "stream_id": stream_id,
            "event_type": event_type,
            "username": result.username,
            "twitch_id": result.twitch_id,
            "is_known_bot": result.is_known_bot,
            "cache_hit": result.cache_hit,
            "verified_at": datetime.now(timezone.utc),
            "reputation": result.reputation.model_dump(),
        }
        if result.record:
            doc["bot_profile"] = result.record.model_dump()
        await db[COL_VERIFICATIONS].insert_one(doc)

    async def record_detection(
        self,
        tenant_id: str,
        result: TwitchBotsVerificationResult,
        *,
        stream_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        threat_level: str = "high",
    ) -> None:
        if not result.is_known_bot:
            return
        db = await get_mongo_db()
        if db is None:
            return
        rec = result.record
        await db[COL_DETECTIONS].insert_one(
            {
                "tenant_id": tenant_id,
                "stream_id": stream_id,
                "channel_name": channel_name,
                "username": result.username,
                "twitch_id": result.twitch_id,
                "bot_type": rec.type_name if rec else result.reputation.bot_type,
                "type_id": rec.type_id if rec else None,
                "threat_level": threat_level,
                "suspicious_score": result.reputation.suspicious_score,
                "bot_known_score": result.reputation.bot_known_score,
                "source_detection": result.reputation.source_detection,
                "detected_at": datetime.now(timezone.utc),
            }
        )
        await db[COL_STATS].update_one(
            {"tenant_id": tenant_id},
            {
                "$inc": {
                    "known_bots_detected": 1,
                    "total_verifications": 1,
                },
                "$set": {"last_detection_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    async def bump_verification_count(self, tenant_id: str, *, known: bool) -> None:
        db = await get_mongo_db()
        if db is None:
            return
        inc: Dict[str, int] = {"total_verifications": 1}
        if known:
            inc["known_bots_detected"] = 1
        await db[COL_STATS].update_one(
            {"tenant_id": tenant_id},
            {"$inc": inc},
            upsert=True,
        )

    async def list_recent_detections(
        self, tenant_id: str, *, limit: int = 40
    ) -> List[Dict[str, Any]]:
        db = await get_mongo_db()
        if db is None:
            return []
        cursor = (
            db[COL_DETECTIONS]
            .find({"tenant_id": tenant_id})
            .sort("detected_at", -1)
            .limit(limit)
        )
        out: List[Dict[str, Any]] = []
        async for doc in cursor:
            d = dict(doc)
            d.pop("_id", None)
            if d.get("detected_at"):
                d["detected_at"] = d["detected_at"].isoformat()
            out.append(d)
        return out

    async def overview(self, tenant_id: str) -> TwitchBotsOverviewStats:
        db = await get_mongo_db()
        if db is None:
            return TwitchBotsOverviewStats(enabled=False)
        stats = await db[COL_STATS].find_one({"tenant_id": tenant_id}) or {}
        recent = await self.list_recent_detections(tenant_id, limit=25)
        type_counts: Dict[str, int] = {}
        for row in recent:
            bt = str(row.get("bot_type") or "unknown")
            type_counts[bt] = type_counts.get(bt, 0) + 1
        top_types = [
            {"bot_type": k, "count": v}
            for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:8]
        ]
        last_at = stats.get("last_detection_at")
        return TwitchBotsOverviewStats(
            enabled=True,
            total_verifications=int(stats.get("total_verifications", 0)),
            known_bots_detected=int(stats.get("known_bots_detected", 0)),
            last_detection_at=last_at.isoformat() if last_at else None,
            recent_detections=recent,
            top_bot_types=top_types,
        )

    async def global_profile_count(self) -> int:
        db = await get_mongo_db()
        if db is None:
            return 0
        return await db[COL_PROFILES].count_documents({})
