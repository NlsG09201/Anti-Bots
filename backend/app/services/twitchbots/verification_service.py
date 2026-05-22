"""Automatic bot verification via TwitchBots.info for SOC anti-bot platform."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import publish_realtime
from app.integrations.twitchbots_info.cache import get_twitchbots_info_cache
from app.integrations.twitchbots_info.client import get_twitchbots_info_client
from app.integrations.twitchbots_info.mongo_store import TwitchBotsInfoMongoStore
from app.integrations.twitchbots_info.resolver import get_twitch_id_resolver
from app.integrations.twitchbots_info.schemas import (
    TwitchBotsBotRecord,
    TwitchBotsVerificationResult,
    UserReputationScores,
)
from app.infrastructure.cache.redis_client import redis_is_configured
from app.services.viewers.session import ViewerSessionService

logger = get_logger(__name__)
settings = get_settings()

VERIFY_EVENT_TYPES = frozenset(
    {
        "viewer_join",
        "viewer_pulse",
        "chat_message",
        "message",
        "follow",
        "user_follow",
        "raid",
        "subscription",
        "gift",
    }
)


class TwitchBotsVerificationService:
    def __init__(self) -> None:
        self._client = get_twitchbots_info_client()
        self._cache = get_twitchbots_info_cache()
        self._resolver = get_twitch_id_resolver()
        self._store = TwitchBotsInfoMongoStore()
        self._api_calls = 0

    @property
    def enabled(self) -> bool:
        return bool(settings.twitchbots_info_enabled)

    async def verify_user(
        self,
        *,
        tenant_id: str,
        username: Optional[str] = None,
        platform_user_id: Optional[str] = None,
        stream_id: Optional[str] = None,
        event_type: Optional[str] = None,
        persist: bool = True,
        broadcast: bool = False,
    ) -> TwitchBotsVerificationResult:
        uname = (username or "").strip().lstrip("@")
        if not self.enabled:
            return TwitchBotsVerificationResult(
                username=uname or "unknown",
                twitch_id=platform_user_id,
            )

        twitch_id = await self._resolver.resolve(
            username=uname or None,
            platform_user_id=platform_user_id,
        )
        if not twitch_id:
            return TwitchBotsVerificationResult(
                username=uname or "unknown",
                twitch_id=None,
                reputation=UserReputationScores.for_unknown(),
            )

        cached = await self._cache.get_bot_hit(twitch_id)
        if cached:
            record = TwitchBotsBotRecord.model_validate(cached)
            rep = UserReputationScores.for_known_bot(
                record, base_risk=settings.twitchbots_info_known_bot_risk_score
            )
            result = TwitchBotsVerificationResult(
                username=record.username or uname,
                twitch_id=twitch_id,
                is_known_bot=True,
                record=record,
                reputation=rep,
                cache_hit=True,
            )
        elif await self._cache.is_miss_cached(twitch_id):
            result = TwitchBotsVerificationResult(
                username=uname or "unknown",
                twitch_id=twitch_id,
                is_known_bot=False,
                reputation=UserReputationScores.for_unknown(),
                cache_hit=True,
            )
        else:
            record = await self._client.get_bot_by_id(twitch_id)
            self._api_calls += 1
            if record:
                await self._cache.set_bot_hit(twitch_id, record.model_dump())
                if persist:
                    await self._store.upsert_profile(record)
                rep = UserReputationScores.for_known_bot(
                    record, base_risk=settings.twitchbots_info_known_bot_risk_score
                )
                result = TwitchBotsVerificationResult(
                    username=record.username or uname,
                    twitch_id=twitch_id,
                    is_known_bot=True,
                    record=record,
                    reputation=rep,
                )
            else:
                await self._cache.set_miss(twitch_id)
                result = TwitchBotsVerificationResult(
                    username=uname or "unknown",
                    twitch_id=twitch_id,
                    is_known_bot=False,
                    reputation=UserReputationScores.for_unknown(),
                )

        if persist:
            await self._store.record_verification(
                tenant_id, result, stream_id=stream_id, event_type=event_type
            )
            await self._store.bump_verification_count(
                tenant_id, known=result.is_known_bot
            )
            if result.is_known_bot:
                await self._store.record_detection(
                    tenant_id,
                    result,
                    stream_id=stream_id,
                    threat_level=_threat_level(result.reputation.suspicious_score),
                )

        if broadcast and result.is_known_bot:
            await publish_realtime(
                tenant_id,
                "twitchbots_detection",
                {
                    "username": result.username,
                    "twitch_id": result.twitch_id,
                    "bot_type": result.reputation.bot_type,
                    "threat_level": _threat_level(result.reputation.suspicious_score),
                    "suspicious_score": result.reputation.suspicious_score,
                    "stream_id": stream_id,
                },
            )

        return result

    async def verify_batch(
        self,
        tenant_id: str,
        users: List[Dict[str, Optional[str]]],
        *,
        stream_id: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, TwitchBotsVerificationResult]:
        if not self.enabled or not users:
            return {}

        resolved: Dict[str, Dict[str, str]] = {}
        id_to_keys: Dict[str, List[str]] = {}
        results: Dict[str, TwitchBotsVerificationResult] = {}

        for entry in users:
            uname = str(entry.get("username") or "").strip().lstrip("@")
            uid = entry.get("platform_user_id")
            tid = await self._resolver.resolve(username=uname or None, platform_user_id=uid)
            key = uname.lower() if uname else (str(uid) if uid else "")
            if not key:
                continue
            if not tid:
                results[key] = TwitchBotsVerificationResult(
                    username=uname or key,
                    twitch_id=None,
                )
                continue
            resolved[key] = {"username": uname, "twitch_id": tid}
            id_to_keys.setdefault(tid, []).append(key)

        pending_ids: List[str] = []
        for tid in id_to_keys:
            cached = await self._cache.get_bot_hit(tid)
            if cached:
                record = TwitchBotsBotRecord.model_validate(cached)
                rep = UserReputationScores.for_known_bot(
                    record, base_risk=settings.twitchbots_info_known_bot_risk_score
                )
                for key in id_to_keys[tid]:
                    uname = resolved[key]["username"]
                    results[key] = TwitchBotsVerificationResult(
                        username=record.username or uname,
                        twitch_id=tid,
                        is_known_bot=True,
                        record=record,
                        reputation=rep,
                        cache_hit=True,
                    )
            elif await self._cache.is_miss_cached(tid):
                for key in id_to_keys[tid]:
                    uname = resolved[key]["username"]
                    results[key] = TwitchBotsVerificationResult(
                        username=uname or key,
                        twitch_id=tid,
                        is_known_bot=False,
                        cache_hit=True,
                    )
            else:
                pending_ids.append(tid)

        if pending_ids:
            api_hits = await self._client.get_bots_by_ids(pending_ids)
            self._api_calls += max(1, len(pending_ids) // 100 + 1)
            for tid in pending_ids:
                keys = id_to_keys.get(tid, [])
                record = api_hits.get(tid)
                if record:
                    await self._cache.set_bot_hit(tid, record.model_dump())
                    if persist:
                        await self._store.upsert_profile(record)
                    rep = UserReputationScores.for_known_bot(
                        record, base_risk=settings.twitchbots_info_known_bot_risk_score
                    )
                    for key in keys:
                        uname = resolved[key]["username"]
                        results[key] = TwitchBotsVerificationResult(
                            username=record.username or uname,
                            twitch_id=tid,
                            is_known_bot=True,
                            record=record,
                            reputation=rep,
                        )
                else:
                    await self._cache.set_miss(tid)
                    for key in keys:
                        uname = resolved[key]["username"]
                        results[key] = TwitchBotsVerificationResult(
                            username=uname or key,
                            twitch_id=tid,
                            is_known_bot=False,
                        )

        if persist:
            for key, result in results.items():
                await self._store.record_verification(
                    tenant_id, result, stream_id=stream_id
                )
                await self._store.bump_verification_count(
                    tenant_id, known=result.is_known_bot
                )
                if result.is_known_bot:
                    await self._store.record_detection(tenant_id, result, stream_id=stream_id)

        return results

    async def apply_to_sessions(
        self,
        db: AsyncSession,
        stream_id: UUID,
        results: Dict[str, TwitchBotsVerificationResult],
    ) -> int:
        if not results:
            return 0
        svc = ViewerSessionService(db)
        sessions = await svc.list_active(stream_id, chat_only=True, limit=500)
        updated = 0
        for session in sessions:
            uname = (session.platform_username or "").lower()
            verdict = results.get(uname)
            if not verdict or not verdict.is_known_bot:
                continue
            metrics = dict(session.behavior_metrics or {})
            metrics["ai_verdict"] = verdict.to_verdict_dict()
            metrics["twitchbots_reputation"] = verdict.reputation.model_dump()
            session.behavior_metrics = metrics
            session.is_suspected_bot = True
            session.risk_score = max(
                session.risk_score,
                float(verdict.reputation.suspicious_score),
            )
            updated += 1
        await db.flush()
        return updated

    async def verify_ingest_user(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        event_type: str,
        username: Optional[str],
        platform_user_id: Optional[str],
    ) -> Optional[TwitchBotsVerificationResult]:
        if not self.enabled or not settings.twitchbots_info_verify_on_ingest:
            return None
        if event_type not in VERIFY_EVENT_TYPES:
            return None
        if not username and not platform_user_id:
            return None
        return await self.verify_user(
            tenant_id=tenant_id,
            username=username,
            platform_user_id=platform_user_id,
            stream_id=stream_id,
            event_type=event_type,
            persist=True,
            broadcast=True,
        )

    async def enqueue_batch(
        self,
        tenant_id: str,
        users: List[Dict[str, Optional[str]]],
        *,
        stream_id: Optional[str] = None,
    ) -> Optional[str]:
        if not settings.twitchbots_info_queue_enabled or not redis_is_configured():
            return None
        if not users:
            return None
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            redis_settings = RedisSettings.from_dsn(settings.redis_url)
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job(
                "twitchbots_verify_batch_job",
                tenant_id,
                users,
                stream_id=stream_id,
                _queue_name="ss:queue:events",
            )
            await pool.close()
            return job.job_id if job else None
        except Exception as exc:
            logger.warning("twitchbots_enqueue_failed", error=str(exc)[:150])
            return None

    async def warm_cache_sample(self) -> int:
        """Prefetch popular bots (Nightbot, Moobot) for cache warming."""
        if not self.enabled:
            return 0
        sample_ids = ["19264788", "1564983", "100135110"]
        hits = await self._client.get_bots_by_ids(sample_ids)
        for tid, rec in hits.items():
            await self._cache.set_bot_hit(tid, rec.model_dump())
            await self._store.upsert_profile(rec)
        return len(hits)


def _threat_level(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


_service: Optional[TwitchBotsVerificationService] = None


def get_twitchbots_verification_service() -> TwitchBotsVerificationService:
    global _service
    if _service is None:
        _service = TwitchBotsVerificationService()
    return _service
