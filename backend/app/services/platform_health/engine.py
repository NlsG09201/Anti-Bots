"""Platform Monitoring Health Engine — audit, alerts, realtime SOC updates."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import publish_realtime
from app.infrastructure.database.models import Alert, AlertSeverity, Platform, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.platform_health.probes import run_all_integration_probes
from app.services.platform_health.registry import all_trackers
from app.services.platform_health.schemas import (
    HealthStatus,
    PlatformHealthOverview,
    StreamMonitorHealth,
    SystemHealthSlice,
)
from app.services.platform_health.store import PlatformHealthStore

logger = get_logger(__name__)
settings = get_settings()

_ENGINE: Optional["PlatformHealthEngine"] = None


def _status_from_tracker(
    snap: StreamMonitorHealth,
    *,
    orchestrator_running: bool,
) -> HealthStatus:
    if snap.ai_flags and snap.ai_anomaly_score >= 50:
        if "stale_poll" in snap.ai_flags or "socket_down" in snap.ai_flags:
            return "stale"
        return "degraded"
    if snap.error_count >= 8:
        return "error"
    if not snap.is_live:
        return "offline"
    if snap.is_live and snap.last_poll_at and orchestrator_running:
        return "healthy"
    if orchestrator_running:
        return "starting"
    return "unknown"


class PlatformHealthEngine:
    def __init__(self) -> None:
        self._store = PlatformHealthStore()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._process_label = "api"

    @property
    def enabled(self) -> bool:
        return bool(settings.platform_health_enabled)

    def set_process_label(self, label: str) -> None:
        self._process_label = label

    async def start(self) -> None:
        if not self.enabled or self._running:
            return
        self._running = True
        await self.audit_once()
        interval = max(settings.platform_health_audit_seconds, 30)
        self._task = asyncio.create_task(self._audit_loop(interval))
        logger.info("platform_health_engine_started", interval=interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("platform_health_engine_stopped")

    async def _audit_loop(self, interval: int) -> None:
        while self._running:
            try:
                await asyncio.sleep(interval)
                await self.audit_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("platform_health_audit_error", error=str(exc)[:200])

    async def audit_once(self) -> PlatformHealthOverview:
        from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator

        orch = get_platform_monitor_orchestrator()
        redis_ok, redis_ms = await self._store.probe_redis_latency()
        worker_alive, worker_ts = await self._store.worker_is_alive(
            settings.platform_health_worker_heartbeat_ttl
        )
        integrations = await run_all_integration_probes()
        await self._store.save_global(
            SystemHealthSlice(
                redis_ok=redis_ok,
                redis_latency_ms=redis_ms,
                realtime_pubsub_ok=redis_ok,
                worker_alive=worker_alive,
                worker_last_seen=worker_ts,
                orchestrator_running=orch._running,
                active_monitors=len(orch._monitors),
                api_process=self._process_label,
            ),
            integrations,
        )

        if self._process_label == "worker":
            await self._store.record_worker_heartbeat(process="worker")
        else:
            await self._store.record_worker_heartbeat(process="api")

        stream_snaps: List[StreamMonitorHealth] = []
        for tracker in all_trackers().values():
            base = tracker.to_snapshot()
            status = _status_from_tracker(
                base,
                orchestrator_running=orch._running,
            )
            snap = tracker.to_snapshot(status=status)
            await self._store.save_stream_health(snap)
            stream_snaps.append(snap)
            await self._evaluate_stream_issues(snap)

        stored = await self._store.load_all_stream_health()
        merged = {s.stream_id: s for s in stored}
        for s in stream_snaps:
            merged[s.stream_id] = s
        streams = list(merged.values())

        summary: Dict[str, int] = {
            "healthy": 0,
            "degraded": 0,
            "stale": 0,
            "offline": 0,
            "error": 0,
            "unknown": 0,
        }
        for s in streams:
            summary[s.status] = summary.get(s.status, 0) + 1

        issues = await self._store.list_issues(30)
        overview = PlatformHealthOverview(
            enabled=True,
            system=SystemHealthSlice(
                redis_ok=redis_ok,
                redis_latency_ms=redis_ms,
                realtime_pubsub_ok=redis_ok,
                worker_alive=worker_alive,
                worker_last_seen=worker_ts,
                orchestrator_running=orch._running,
                active_monitors=len(orch._monitors),
                api_process=self._process_label,
            ),
            integrations=integrations,
            streams=streams,
            issues=issues,
            summary=summary,
        )

        await self._broadcast_overview(overview)
        return overview

    async def _evaluate_stream_issues(self, snap: StreamMonitorHealth) -> None:
        for flag in snap.ai_flags:
            severity = "high" if flag in ("stale_poll", "socket_down") else "medium"
            issue_key = f"{snap.stream_id}:{flag}"
            if await self._store.alert_on_cooldown(
                issue_key, settings.platform_health_alert_cooldown_seconds
            ):
                continue
            issue = {
                "stream_id": snap.stream_id,
                "platform": snap.platform,
                "channel": snap.channel_name,
                "flag": flag,
                "severity": severity,
                "message": f"{snap.channel_name} ({snap.platform}): {flag}",
                "ai_score": snap.ai_anomaly_score,
            }
            await self._store.push_issue(issue)
            await self._maybe_create_alert(snap, flag, severity)

    async def _maybe_create_alert(
        self,
        snap: StreamMonitorHealth,
        flag: str,
        severity: str,
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Stream).where(Stream.id == UUID(snap.stream_id))
                )
                stream = result.scalar_one_or_none()
                if not stream:
                    return
                sev = AlertSeverity.HIGH if severity == "high" else AlertSeverity.MEDIUM
                alert = Alert(
                    tenant_id=stream.tenant_id,
                    attack_id=None,
                    title=f"Monitor {snap.platform}: {flag}",
                    message=(
                        f"Canal {snap.channel_name}: problema de monitoreo ({flag}). "
                        f"Viewers={snap.viewer_count}, reconexiones={snap.reconnect_count}."
                    ),
                    severity=sev,
                    source="platform_health",
                    alert_metadata={
                        "stream_id": snap.stream_id,
                        "platform": snap.platform,
                        "flag": flag,
                        "ai_score": snap.ai_anomaly_score,
                    },
                )
                db.add(alert)
                await db.commit()
                await publish_realtime(
                    str(stream.tenant_id),
                    "alert",
                    {
                        "title": alert.title,
                        "message": alert.message,
                        "severity": alert.severity.value,
                        "source": "platform_health",
                    },
                )
        except Exception as exc:
            logger.warning("platform_health_alert_failed", error=str(exc)[:150])

    async def _broadcast_overview(self, overview: PlatformHealthOverview) -> None:
        tenant_ids = await self._tenant_ids_for_platform_streams()
        payload = overview.model_dump()
        for tid in tenant_ids:
            await publish_realtime(tid, "platform_monitor_health", payload)

    async def _tenant_ids_for_platform_streams(self) -> List[str]:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Stream.tenant_id).where(
                        Stream.platform.in_(
                            [Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK]
                        )
                    )
                )
                return list({str(row[0]) for row in result.all()})
        except Exception:
            return []

    async def build_overview(self) -> PlatformHealthOverview:
        system, integrations = await self._store.load_global()
        streams = await self._store.load_all_stream_health()
        for tracker in all_trackers().values():
            snap = tracker.to_snapshot(status="unknown")
            streams = [s for s in streams if s.stream_id != snap.stream_id]
            streams.append(snap)
        summary: Dict[str, int] = {}
        for s in streams:
            summary[s.status] = summary.get(s.status, 0) + 1
        return PlatformHealthOverview(
            enabled=self.enabled,
            system=system,
            integrations=integrations,
            streams=streams,
            issues=await self._store.list_issues(30),
            summary=summary,
        )


def get_platform_health_engine() -> PlatformHealthEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = PlatformHealthEngine()
    return _ENGINE
