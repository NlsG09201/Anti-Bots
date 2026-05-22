"""Orquestador de monitores Kick / YouTube / TikTok (Render-safe, límites de concurrencia)."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional, Union
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.platform_health.registry import drop_tracker
from app.services.monitoring.kick_live import KickLiveMonitor, resolve_kick_chatroom
from app.services.monitoring.tiktok_live import TikTokLiveMonitor
from app.services.monitoring.youtube_live import YouTubeLiveMonitor
from app.services.streams.helpers import stream_monitor_mode

logger = get_logger(__name__)
settings = get_settings()

MonitorHandle = Union[KickLiveMonitor, YouTubeLiveMonitor, TikTokLiveMonitor]


class PlatformMonitorOrchestrator:
    def __init__(self) -> None:
        self._monitors: Dict[str, MonitorHandle] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._reconcile_task: Optional[asyncio.Task] = None
        self._running = False

    def _should_monitor(self, stream: Stream) -> bool:
        if stream.platform == Platform.TWITCH:
            return False
        if stream.platform not in (Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK):
            return False
        meta = stream.settings or {}
        if not stream_monitor_mode(stream) and not meta.get("soc_monitor"):
            return False
        return stream.is_live or meta.get("force_monitor")

    async def _start_monitor(self, stream: Stream) -> None:
        sid = str(stream.id)
        if sid in self._monitors:
            # Check if monitor task is still alive
            monitor = self._monitors[sid]
            # Simple check for Kick monitor pusher task
            if hasattr(monitor, "_pusher_task") and monitor._pusher_task and monitor._pusher_task.done():
                 logger.warning("monitor_task_dead_restarting", stream_id=sid)
                 await self._stop_monitor(sid)
            else:
                return

        slug = (stream.settings or {}).get("login") or stream.channel_name
        slug = slug.strip().lstrip("@").lower()

        try:
            if stream.platform == Platform.KICK:
                chatroom_id = (stream.settings or {}).get("kick_chatroom_id")
                if not chatroom_id:
                    chatroom_id = await resolve_kick_chatroom(slug)
                if not chatroom_id:
                    logger.warning("kick_chatroom_missing", slug=slug)
                    return
                monitor = KickLiveMonitor(sid, slug, int(chatroom_id))
            elif stream.platform == Platform.YOUTUBE:
                monitor = YouTubeLiveMonitor(
                    sid,
                    stream.channel_name,
                    video_id=stream.external_id or None,
                )
            elif stream.platform == Platform.TIKTOK:
                monitor = TikTokLiveMonitor(sid, slug)
            else:
                return

            await monitor.start()
            self._monitors[sid] = monitor
            logger.info(
                "platform_monitor_started",
                stream_id=sid,
                platform=stream.platform.value,
                channel=stream.channel_name,
            )
        except Exception as exc:
            logger.warning(
                "platform_monitor_start_failed",
                stream_id=sid,
                platform=stream.platform.value,
                error=str(exc)[:300],
            )

    async def _stop_monitor(self, stream_id: str) -> None:
        monitor = self._monitors.pop(stream_id, None)
        if monitor:
            await monitor.stop()
            drop_tracker(stream_id)
            logger.info("platform_monitor_stopped", stream_id=stream_id)

    async def reconcile(self) -> None:
        if not settings.platform_monitor_enabled:
            return
        
        from app.services.monitoring.discovery_engine import get_live_discovery_engine
        from app.services.monitoring.validation_engine import get_stream_validation_engine
        
        engine = get_live_discovery_engine()
        validator = get_stream_validation_engine()

        async with AsyncSessionLocal() as db:
            # Only select streams that are marked as live or force_monitor
            result = await db.execute(
                select(Stream).where(
                    Stream.platform.in_(
                        [Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK]
                    )
                )
            )
            streams = list(result.scalars().all())
            
        candidates = []
        for s in streams:
            if self._should_monitor(s):
                # Double check live status if not force_monitor
                if not (s.settings or {}).get("force_monitor"):
                    is_live, _ = await validator.validate_live_status(str(s.id))
                    if not is_live:
                        continue
                candidates.append(s)

        candidates.sort(key=lambda s: (not s.is_live, s.channel_name))
        active_ids = {str(s.id) for s in candidates[: settings.platform_monitor_max_streams]}

        for sid in list(self._monitors.keys()):
            if sid not in active_ids:
                await self._stop_monitor(sid)

        for stream in candidates[: settings.platform_monitor_max_streams]:
            await self._start_monitor(stream)

    async def _reconcile_loop(self) -> None:
        interval = max(settings.platform_monitor_poll_seconds, 15)
        while self._running:
            try:
                await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("platform_reconcile_error", error=str(exc)[:200])
            await asyncio.sleep(interval)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.reconcile()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        logger.info("platform_monitor_orchestrator_started")

    async def stop(self) -> None:
        self._running = False
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        for sid in list(self._monitors.keys()):
            await self._stop_monitor(sid)
        logger.info("platform_monitor_orchestrator_stopped")


_orchestrator: Optional[PlatformMonitorOrchestrator] = None


def get_platform_monitor_orchestrator() -> PlatformMonitorOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PlatformMonitorOrchestrator()
    return _orchestrator
