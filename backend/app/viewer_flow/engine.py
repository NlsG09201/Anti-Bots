"""Viewer Flow Intelligence Engine — Kick / YouTube / TikTok."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import publish_realtime
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.viewer_flow.analyzer import analyze_stream
from app.viewer_flow.mongo_store import ViewerFlowMongoStore
from app.viewer_flow.schemas import (
    PlatformName,
    ViewerFlowOverview,
    ViewerFlowStreamSnapshot,
    ViewerFlowTimelinePoint,
)
from app.viewer_flow.tracker import get_viewer_flow_tracker

logger = get_logger(__name__)
settings = get_settings()

_ENGINE: Optional["ViewerFlowEngine"] = None

_NON_TWITCH = frozenset({Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK})


class ViewerFlowEngine:
    def __init__(self) -> None:
        self._tracker = get_viewer_flow_tracker()
        self._mongo = ViewerFlowMongoStore()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return bool(settings.viewer_flow_enabled)

    async def start(self) -> None:
        if not self.enabled or self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("viewer_flow_engine_started")

    async def stop(self) -> None:
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

    async def _flush_loop(self) -> None:
        interval = max(settings.viewer_flow_flush_seconds, 20)
        while self._running:
            try:
                await asyncio.sleep(interval)
                await self._flush_all_snapshots()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("viewer_flow_flush_error", error=str(exc)[:150])

    async def _flush_all_snapshots(self) -> None:
        for state in self._tracker.all_states():
            snap = analyze_stream(state)
            try:
                await self._mongo.upsert_snapshot(state.tenant_id, snap)
            except Exception:
                pass

    def _platform_name(self, platform: Platform) -> Optional[PlatformName]:
        val = platform.value if hasattr(platform, "value") else str(platform)
        if val in ("kick", "youtube", "tiktok"):
            return val  # type: ignore[return-value]
        return None

    async def record_viewer_pulse(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        platform: Platform,
        channel_name: str,
        viewer_count: int,
        is_live: bool,
    ) -> None:
        if not self.enabled:
            return
        pname = self._platform_name(platform)
        if not pname:
            return
        state = self._tracker.get_or_create(
            stream_id, tenant_id, pname, channel_name
        )
        state.record_pulse(viewer_count, is_live)
        if not is_live:
            state.mark_offline()
        snap = analyze_stream(state)
        if snap.metrics.ai_flags and "impossible_growth" in snap.metrics.ai_flags:
            state._push_timeline(
                "viewbot_suspected",
                "Viewbotting sospechoso",
                value=snap.metrics.suspicious_growth_score,
                severity="critical",
            )
        await self._broadcast_stream(tenant_id, snap)

    async def record_platform_event(
        self,
        *,
        tenant_id: str,
        stream_id: str,
        platform: Platform,
        channel_name: str,
        event_type: str,
        username: Optional[str] = None,
        platform_user_id: Optional[str] = None,
        risk_hints: Optional[List[str]] = None,
    ) -> None:
        if not self.enabled:
            return
        pname = self._platform_name(platform)
        if not pname:
            return
        state = self._tracker.get_or_create(
            stream_id, tenant_id, pname, channel_name
        )
        state.record_entity_event(
            event_type,
            username=username,
            platform_user_id=platform_user_id,
        )
        if username and risk_hints:
            ent = state.entities.get(username.lower())
            if ent:
                for h in risk_hints:
                    if h not in ent.risk_hints:
                        ent.risk_hints.append(h)
        if username:
            try:
                await self._mongo.upsert_entity_cross(
                    tenant_id,
                    username=username,
                    platform=pname,
                    stream_id=stream_id,
                )
                hits = await self._mongo.cross_platform_usernames(tenant_id, username)
                if hits > 1:
                    ent = state.entities.get(username.lower())
                    if ent and "cross_platform" not in ent.risk_hints:
                        ent.risk_hints.append("cross_platform")
            except Exception:
                pass
        if event_type == "stream.offline":
            state.mark_offline()
        snap = analyze_stream(state)
        await self._broadcast_stream(tenant_id, snap)

    async def _broadcast_stream(
        self, tenant_id: str, snapshot: ViewerFlowStreamSnapshot
    ) -> None:
        await publish_realtime(
            tenant_id,
            "viewer_flow_update",
            {
                "stream_id": snapshot.metrics.stream_id,
                "platform": snapshot.metrics.platform,
                "metrics": snapshot.metrics.model_dump(),
                "timeline": [t.model_dump() for t in snapshot.timeline[-8:]],
                "suspicious_count": len(snapshot.suspicious_viewers),
            },
        )

    async def get_stream_snapshot(
        self, stream_id: str
    ) -> Optional[ViewerFlowStreamSnapshot]:
        state = self._tracker.get(stream_id)
        if state:
            snap = analyze_stream(state)
            for row in snap.suspicious_viewers:
                if row.username:
                    row.cross_platform_hits = await self._mongo.cross_platform_usernames(
                        state.tenant_id, row.username
                    )
            return snap
        return None

    async def build_overview(self, tenant_id: str) -> ViewerFlowOverview:
        if not self.enabled:
            return ViewerFlowOverview(enabled=False, tenant_id=tenant_id)
        streams_metrics = []
        feed: List[ViewerFlowTimelinePoint] = []
        total_suspicious = 0
        max_threat = 0.0

        live_states = self._tracker.all_for_tenant(tenant_id)
        if not live_states:
            stored = await self._mongo.list_snapshots(tenant_id)
            streams_metrics = stored
        else:
            for state in live_states:
                snap = analyze_stream(state)
                streams_metrics.append(snap.metrics)
                total_suspicious += len(snap.suspicious_viewers)
                max_threat = max(max_threat, snap.metrics.threat_score)
                feed.extend(snap.timeline[-3:])

        feed.sort(key=lambda x: x.ts, reverse=True)
        return ViewerFlowOverview(
            enabled=True,
            tenant_id=tenant_id,
            streams=streams_metrics,
            global_threat_score=round(max_threat, 2),
            active_non_twitch=len(streams_metrics),
            total_suspicious=total_suspicious,
            attack_feed=feed[:25],
        )

    async def reconcile_tenant_streams(self, tenant_id: str) -> None:
        """Load live non-Twitch streams from DB for cold start."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Stream).where(
                        Stream.tenant_id == UUID(tenant_id),
                        Stream.platform.in_(
                            [Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK]
                        ),
                        Stream.is_live.is_(True),
                    )
                )
                for stream in result.scalars().all():
                    pname = self._platform_name(stream.platform)
                    if not pname:
                        continue
                    self._tracker.get_or_create(
                        str(stream.id),
                        tenant_id,
                        pname,
                        stream.channel_name,
                    )
                    await self.record_viewer_pulse(
                        tenant_id=tenant_id,
                        stream_id=str(stream.id),
                        platform=stream.platform,
                        channel_name=stream.channel_name,
                        viewer_count=stream.viewer_count or 0,
                        is_live=stream.is_live,
                    )
        except Exception as exc:
            logger.warning("viewer_flow_reconcile_failed", error=str(exc)[:150])


def get_viewer_flow_engine() -> ViewerFlowEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ViewerFlowEngine()
    return _ENGINE
