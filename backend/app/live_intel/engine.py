"""Live Stream Intelligence Monitor — sampling, analysis, realtime broadcast."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import publish_realtime
from app.infrastructure.cache.redis_client import optional_get_redis
from app.infrastructure.database.models import AttackType, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.live_intel.analyzer import LiveIntelAnalyzer
from app.live_intel.comparator import compare_streams, detect_comparison_anomalies
from app.live_intel.mongo_store import LiveIntelMongoStore
from app.live_intel.rankings import build_rankings
from app.live_intel.schemas import LiveIntelOverview, LiveStreamSnapshot
from app.live_intel.tracker import get_live_intel_tracker
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)
_settings = get_settings()

REDIS_CACHE_PREFIX = "live_intel:tenant:"
CACHE_TTL = 30


def is_competitive_stream(stream: Stream) -> bool:
    meta = stream.settings or {}
    return bool(
        meta.get("competitive_intel")
        or meta.get("soc_monitor")
        or meta.get("monitor_mode")
        or (meta.get("is_owned") and bool(stream.oauth_token_encrypted))
    )


class LiveIntelEngine:
    def __init__(self) -> None:
        self._analyzer = LiveIntelAnalyzer()
        self._store = LiveIntelMongoStore()
        self._snapshots: Dict[str, LiveStreamSnapshot] = {}
        self._prev_viewers: Dict[str, int] = {}
        self._was_live: Dict[str, bool] = {}
        self._last_sample_at: Dict[str, float] = {}
        self._sample_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return bool(_settings.live_intel_enabled)

    def get_snapshot(self, stream_id: str) -> Optional[LiveStreamSnapshot]:
        return self._snapshots.get(stream_id)

    async def record_platform_event(
        self,
        stream_id: str,
        event_type: str,
        *,
        username: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        get_live_intel_tracker().record_event(
            stream_id, event_type, username=username
        )

    async def sample_stream(
        self,
        stream: Stream,
        *,
        db: Any = None,
        live_status: Any = None,
    ) -> Optional[LiveStreamSnapshot]:
        if not self.enabled:
            return None

        sid = str(stream.id)
        tid = str(stream.tenant_id)
        adapter = get_platform_adapter(stream.platform)

        try:
            live = live_status or await adapter.fetch_live_status(stream)
        except Exception as exc:
            logger.debug("live_intel_fetch_failed", stream_id=sid, error=str(exc)[:120])
            return self._snapshots.get(sid)

        prev = self._prev_viewers.get(sid, live.viewer_count)
        was_live = self._was_live.get(sid, False)
        stream.is_live = live.is_live
        stream.viewer_count = live.viewer_count if live.is_live else 0
        stream_meta = dict(stream.settings or {})
        stream_meta["stream_title"] = live.title
        if live.is_live:
            history = (
                list(stream_meta.get("viewer_history", [])) if was_live else []
            )
            history.append(
                {"count": live.viewer_count, "at": datetime.now(timezone.utc).isoformat()}
            )
            stream_meta["viewer_history"] = history[-120:]
        stream.settings = stream_meta

        if live.is_live and not was_live:
            await self._store.start_session(
                tid,
                sid,
                {
                    "platform": stream.platform.value,
                    "channel_name": stream.channel_name,
                    "title": live.title,
                },
            )
            get_live_intel_tracker().mark_live(sid, viewers=live.viewer_count)

        if not live.is_live and was_live:
            get_live_intel_tracker().mark_offline(sid)
            await self._store.end_session(tid, sid)
            self._was_live[sid] = False
            self._prev_viewers.pop(sid, None)
            self._last_sample_at.pop(sid, None)
            snap = self._snapshots.get(sid)
            if snap:
                snap.is_live = False
                snap.viewers = 0
            await self._broadcast_tenant(tid)
            return snap

        if not live.is_live:
            self._was_live[sid] = False
            return None

        self._was_live[sid] = True
        history = list((stream.settings or {}).get("viewer_history", []))
        vpm = 0.0
        if len(history) >= 2:
            try:
                c0 = int(history[-2].get("count", 0))
                c1 = int(history[-1].get("count", live.viewer_count))
                vpm = float(max(0, c1 - c0)) * (60.0 / max(_settings.live_intel_sample_seconds, 10))
            except (TypeError, ValueError):
                vpm = float(max(0, live.viewer_count - prev))

        rates = get_live_intel_tracker().compute_rates(sid)
        sampled_at = time.monotonic()
        elapsed = max(sampled_at - self._last_sample_at.get(sid, sampled_at), 1.0)
        self._last_sample_at[sid] = sampled_at
        viewer_delta = live.viewer_count - prev
        joins_per_minute = max(0.0, viewer_delta) * 60.0 / elapsed
        growth_rate = abs(viewer_delta) * 60.0 / elapsed
        partial, flags = self._analyzer.analyze(
            viewers=live.viewer_count,
            prev_viewers=prev,
            viewers_per_minute=vpm,
            messages_per_minute=float(rates["messages_per_minute"]),
            follows_per_minute=float(rates["follows_per_minute"]),
            chatters=int(rates["active_chatters"]),
            viewer_history=history,
            rates=rates,
        )

        meta = stream.settings or {}
        snap = partial.model_copy(
            update={
                "stream_id": sid,
                "tenant_id": tid,
                "platform": stream.platform.value,
                "channel_name": stream.channel_name,
                "is_live": True,
                "title": live.title or meta.get("stream_title"),
                "category": meta.get("category"),
                "viewers": live.viewer_count,
                "likes": int(meta.get("likes", 0)),
                "follows_total": int(meta.get("follows_total", 0)),
                "chatters": int(rates["active_chatters"]),
                "duration_seconds": int(rates["duration_seconds"]),
            }
        )

        self._prev_viewers[sid] = live.viewer_count
        self._snapshots[sid] = snap

        doc = snap.model_dump()
        await self._store.upsert_snapshot(tid, sid, doc)
        await self._store.append_history(
            tid,
            sid,
            {
                "viewers": snap.viewers,
                "engagement_score": snap.engagement_score,
                "bot_probability": snap.bot_probability,
                "messages_per_minute": snap.messages_per_minute,
            },
        )

        if db is not None and prev > 0 and abs(viewer_delta) >= max(20, int(prev * 0.15)):
            await self._assess_viewer_change(
                db,
                stream,
                snap,
                flags,
                viewer_delta=viewer_delta,
                joins_per_minute=joins_per_minute,
                growth_rate=growth_rate,
                rates=rates,
            )

        if snap.suspicious_growth or snap.viewbot_probability > 0.65:
            await self._store.record_anomaly(
                tid,
                sid,
                {
                    "type": "viewbot_risk" if snap.viewbot_probability > 0.65 else "growth_spike",
                    "viewbot_probability": snap.viewbot_probability,
                    "flags": flags,
                    "channel_name": stream.channel_name,
                },
            )
            if snap.viewbot_probability >= 0.7:
                await publish_realtime(
                    tid,
                    "alert",
                    {
                        "title": "Viewbot risk — competitive intel",
                        "message": (
                            f"{stream.channel_name} ({stream.platform.value}): "
                            f"viewbot {(snap.viewbot_probability * 100):.0f}%"
                        ),
                        "severity": "high",
                        "stream_id": sid,
                    },
                )

        return snap

    async def _assess_viewer_change(
        self,
        db: Any,
        stream: Stream,
        snap: LiveStreamSnapshot,
        flags: List[str],
        *,
        viewer_delta: int,
        joins_per_minute: float,
        growth_rate: float,
        rates: Dict[str, float | int],
    ) -> None:
        """Assess material viewer-count changes and persist actionable alerts."""
        from app.ai_intel.orchestrator import get_ai_orchestrator
        from app.services.correlation.service import CorrelationService
        from app.services.dashboard.metrics import get_tenant_stream_ids
        from app.services.realtime.notify import push_dashboard_realtime

        active_chatters = int(rates["active_chatters"])
        metadata = {
            "joins_per_minute": joins_per_minute,
            "viewer_growth_rate": growth_rate,
            "follow_velocity": float(rates["follows_per_minute"]),
            "chat_message_rate": float(rates["messages_per_minute"]),
            "silent_viewer_ratio": max(0.0, 1.0 - active_chatters / max(snap.viewers, 1)),
            "viewer_delta": viewer_delta,
            "viewer_count": snap.viewers,
            "heuristic_risk": snap.suspicious_activity_score,
            "heuristic_flags": flags,
        }
        assessment = await get_ai_orchestrator().assess_event(
            db,
            stream_id=stream.id,
            tenant_id=stream.tenant_id,
            event_type="viewer_pulse",
            metadata=metadata,
        )
        score = max(float(assessment.risk_score), float(snap.suspicious_activity_score))
        if viewer_delta < 0:
            drop_ratio = abs(viewer_delta) / max(snap.viewers - viewer_delta, 1)
            if drop_ratio >= 0.25:
                score = max(score, min(90.0, 65.0 + (drop_ratio - 0.25) * 100))
        if score < 65 and not assessment.early_warning:
            return

        correlation = CorrelationService(db)
        attack = await correlation.get_active_attack(stream.id, AttackType.VIEWBOT)
        should_broadcast = attack is None
        alert_payload = None
        evidence = {
            "source": "viewer_flow_ai",
            "viewer_delta": viewer_delta,
            "viewer_count": snap.viewers,
            "risk_score": score,
            "ai_assessment": assessment.to_dict(),
            "heuristic_flags": flags,
            "channel_name": stream.channel_name,
        }
        if attack:
            should_broadcast = score >= float(attack.risk_score) + 10
            attack.risk_score = max(float(attack.risk_score), score)
            attack.confidence = max(float(attack.confidence), float(assessment.confidence))
            attack.evidence = {**(attack.evidence or {}), **evidence}
            attack.severity = correlation._score_to_severity(attack.risk_score)
        else:
            attack = await correlation.create_attack_record(
                stream_id=stream.id,
                attack_type=AttackType.VIEWBOT,
                risk_score=score,
                confidence=float(assessment.confidence),
                evidence=evidence,
                source_ips=[],
                fingerprints=[],
            )
            alert = await correlation.create_alert(
                stream.tenant_id,
                attack,
                "Anomalía en el flujo de viewers",
                (
                    f"{stream.channel_name}: cambio de {viewer_delta:+d} viewers "
                    f"en el último intervalo; riesgo estimado {score:.0f}/100."
                ),
            )
            alert.source = "live_intel"
            alert_payload = {
                "id": str(alert.id),
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity.value,
                "status": alert.status,
                "created_at": alert.created_at.isoformat(),
            }

        await db.flush()
        if should_broadcast:
            await push_dashboard_realtime(
                db,
                stream.tenant_id,
                await get_tenant_stream_ids(db, stream.tenant_id),
                alert=alert_payload,
                attack={"attack_id": str(attack.id), "stream_id": str(stream.id)},
            )
    async def reconcile_tenant(self, tenant_id: UUID) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Stream).where(Stream.tenant_id == tenant_id)
            )
            streams = [s for s in result.scalars().all() if is_competitive_stream(s)]
            for stream in streams[: _settings.live_intel_max_streams]:
                try:
                    await self.sample_stream(stream, db=db)
                except Exception as exc:
                    logger.debug(
                        "live_intel_sample_skip",
                        stream_id=str(stream.id),
                        error=str(exc)[:100],
                    )
            await db.commit()

    async def sample_all(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Stream))
            streams = [s for s in result.scalars().all() if is_competitive_stream(s)]
            streams.sort(key=lambda s: (not s.is_live, s.channel_name))
            for stream in streams[: _settings.live_intel_max_streams]:
                try:
                    snap = await self.sample_stream(stream, db=db)
                    if snap:
                        await self._broadcast_tenant(str(stream.tenant_id))
                except Exception as exc:
                    logger.warning(
                        "live_intel_sample_error",
                        stream_id=str(stream.id),
                        error=str(exc)[:150],
                    )
            await db.commit()

    async def get_overview(
        self, tenant_id: UUID, *, refresh: bool = False
    ) -> LiveIntelOverview:
        tid = str(tenant_id)
        try:
            return await self._build_overview(tenant_id, tid, refresh=refresh)
        except Exception as exc:
            logger.warning(
                "live_intel_get_overview_failed",
                tenant_id=tid,
                error=str(exc)[:200],
            )
            return LiveIntelOverview(tenant_id=tid)

    async def _build_overview(
        self, tenant_id: UUID, tid: str, *, refresh: bool
    ) -> LiveIntelOverview:
        if refresh:
            try:
                await self.reconcile_tenant(tenant_id)
            except Exception as exc:
                logger.warning(
                    "live_intel_reconcile_failed",
                    tenant_id=tid,
                    error=str(exc)[:200],
                )
        snaps = [
            s
            for s in self._snapshots.values()
            if s.tenant_id == tid and s.is_live
        ]
        if not snaps:
            try:
                docs = await self._store.list_snapshots(tid)
            except Exception as exc:
                logger.warning(
                    "live_intel_overview_snapshots_failed",
                    tenant_id=tid,
                    error=str(exc)[:150],
                )
                docs = []
            for d in docs:
                if d.get("is_live"):
                    try:
                        snaps.append(LiveStreamSnapshot(**d))
                    except Exception:
                        pass

        rankings = build_rankings(snaps)
        heatmap = self._build_heatmap(snaps)
        suspicious = sum(1 for s in snaps if s.suspicious_activity_score >= 55)
        avg_eng = (
            sum(s.engagement_score for s in snaps) / len(snaps) if snaps else 0.0
        )

        overview = LiveIntelOverview(
            tenant_id=tid,
            live_count=len(snaps),
            monitored_count=len(
                [s for s in self._snapshots.values() if s.tenant_id == tid]
            ),
            suspicious_live=suspicious,
            avg_engagement=round(avg_eng, 2),
            rankings_suspicious=rankings["most_suspicious"],
            rankings_organic=rankings["most_organic"],
            rankings_anomaly_growth=rankings["abnormal_growth"],
            snapshots=snaps,
            heatmap=heatmap,
        )
        await self._cache_overview(tid, overview)
        return overview

    def compare(
        self, tenant_id: str, stream_ids: List[str]
    ) -> Dict[str, Any]:
        tenant_snaps = {
            s.stream_id: s
            for s in self._snapshots.values()
            if s.tenant_id == tenant_id
        }
        rows = compare_streams(tenant_snaps, stream_ids)
        insights = detect_comparison_anomalies(rows)
        return {"rows": [r.model_dump() for r in rows], "insights": insights}

    def _build_heatmap(self, snaps: List[LiveStreamSnapshot]) -> List[Dict[str, Any]]:
        heat: List[Dict[str, Any]] = []
        for s in snaps:
            intensity = min(
                100,
                int(s.suspicious_activity_score * 0.5 + s.viewbot_probability * 50),
            )
            heat.append(
                {
                    "stream_id": s.stream_id,
                    "channel": s.channel_name,
                    "platform": s.platform,
                    "intensity": intensity,
                    "viewers": s.viewers,
                }
            )
        return heat

    async def _cache_overview(self, tenant_id: str, overview: LiveIntelOverview) -> None:
        redis = await optional_get_redis()
        if not redis:
            return
        try:
            await redis.setex(
                f"{REDIS_CACHE_PREFIX}{tenant_id}",
                CACHE_TTL,
                json.dumps(overview.model_dump(), default=str),
            )
        except Exception as exc:
            logger.debug(
                "live_intel_cache_skip",
                tenant_id=tenant_id,
                error=str(exc)[:120],
            )

    async def _broadcast_tenant(self, tenant_id: str) -> None:
        snaps = [
            s.model_dump()
            for s in self._snapshots.values()
            if s.tenant_id == tenant_id and s.is_live
        ]
        await publish_realtime(
            tenant_id,
            "live_intel_update",
            {"snapshots": snaps, "count": len(snaps)},
        )

    async def _sample_loop(self) -> None:
        interval = max(_settings.live_intel_sample_seconds, 15)
        while self._running:
            try:
                await self.sample_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("live_intel_loop_error", error=str(exc)[:200])
            await asyncio.sleep(interval)

    async def start(self) -> None:
        if not self.enabled or self._running:
            return
        self._running = True
        await self.sample_all()
        self._sample_task = asyncio.create_task(self._sample_loop())
        logger.info("live_intel_engine_started")

    async def stop(self) -> None:
        self._running = False
        if self._sample_task and not self._sample_task.done():
            self._sample_task.cancel()
            try:
                await self._sample_task
            except asyncio.CancelledError:
                pass
        logger.info("live_intel_engine_stopped")


_engine: LiveIntelEngine | None = None


def get_live_intel_engine() -> LiveIntelEngine:
    global _engine
    if _engine is None:
        _engine = LiveIntelEngine()
    return _engine
