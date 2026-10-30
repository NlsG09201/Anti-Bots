"""Schemas for platform monitor health (Kick / YouTube / TikTok)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

HealthStatus = Literal[
    "healthy",
    "degraded",
    "stale",
    "offline",
    "error",
    "starting",
    "unknown",
]

PlatformName = Literal["kick", "youtube", "tiktok"]


class StreamMonitorHealth(BaseModel):
    stream_id: str
    platform: PlatformName
    channel_name: str = ""
    slug: str = ""
    status: HealthStatus = "unknown"
    is_live: bool = False
    viewer_count: int = 0
    messages_per_min: float = 0.0
    viewers_per_min: float = 0.0
    events_total: int = 0
    chat_events_1h: int = 0
    last_poll_at: Optional[str] = None
    last_event_at: Optional[str] = None
    last_chat_at: Optional[str] = None
    poll_latency_ms: Optional[float] = None
    socket_connected: bool = False
    socket_transport: str = ""
    reconnect_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    frozen_viewer_polls: int = 0
    ai_anomaly_score: float = 0.0
    ai_flags: List[str] = Field(default_factory=list)
    uptime_seconds: float = 0.0
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class IntegrationProbeResult(BaseModel):
    platform: PlatformName
    ok: bool = False
    latency_ms: Optional[float] = None
    circuit_state: str = "closed"
    message: str = ""
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SystemHealthSlice(BaseModel):
    redis_ok: bool = False
    redis_latency_ms: Optional[float] = None
    realtime_pubsub_ok: bool = False
    worker_alive: bool = False
    worker_last_seen: Optional[str] = None
    orchestrator_running: bool = False
    active_monitors: int = 0
    api_process: str = "api"


class PlatformHealthOverview(BaseModel):
    enabled: bool = True
    system: SystemHealthSlice = Field(default_factory=SystemHealthSlice)
    integrations: List[IntegrationProbeResult] = Field(default_factory=list)
    streams: List[StreamMonitorHealth] = Field(default_factory=list)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
