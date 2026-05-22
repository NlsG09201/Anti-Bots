"""Viewer Flow Intelligence — schemas (Kick / YouTube / TikTok)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PlatformName = Literal["kick", "youtube", "tiktok"]
FlowEventKind = Literal[
    "viewer_pulse",
    "viewer_join",
    "viewer_leave",
    "chat",
    "follow",
    "gift",
    "spike",
    "raid_suspected",
    "viewbot_suspected",
    "offline",
]


class ViewerFlowMetrics(BaseModel):
    stream_id: str
    platform: PlatformName
    channel_name: str = ""
    is_live: bool = False
    viewers_current: int = 0
    viewers_per_minute: float = 0.0
    viewers_new_estimated: int = 0
    viewers_lost_estimated: int = 0
    messages_per_minute: float = 0.0
    follows_per_minute: float = 0.0
    gifts_per_minute: float = 0.0
    engagement_ratio: float = 0.0
    growth_velocity: float = 0.0
    suspicious_growth_score: float = 0.0
    bot_probability: float = 0.0
    trust_score: float = 100.0
    threat_score: float = 0.0
    raid_likelihood: float = 0.0
    suspicious_score: float = 0.0
    active_chatters: int = 0
    silent_viewers_estimated: int = 0
    coordinated_burst_score: float = 0.0
    ai_flags: List[str] = Field(default_factory=list)
    updated_at: str = ""


class ViewerFlowTimelinePoint(BaseModel):
    ts: str
    kind: FlowEventKind
    label: str
    value: float = 0.0
    username: Optional[str] = None
    severity: str = "info"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SuspiciousViewerFlow(BaseModel):
    username: str
    platform_user_id: Optional[str] = None
    platform: PlatformName
    stream_id: str
    bot_probability: float = 0.0
    suspicious_score: float = 0.0
    trust_score: float = 50.0
    reasons: List[str] = Field(default_factory=list)
    message_count: int = 0
    is_silent: bool = False
    cross_platform_hits: int = 0


class ViewerFlowStreamSnapshot(BaseModel):
    metrics: ViewerFlowMetrics
    timeline: List[ViewerFlowTimelinePoint] = Field(default_factory=list)
    suspicious_viewers: List[SuspiciousViewerFlow] = Field(default_factory=list)
    viewer_history: List[Dict[str, Any]] = Field(default_factory=list)


class ViewerFlowOverview(BaseModel):
    enabled: bool = True
    tenant_id: str = ""
    streams: List[ViewerFlowMetrics] = Field(default_factory=list)
    global_threat_score: float = 0.0
    active_non_twitch: int = 0
    total_suspicious: int = 0
    attack_feed: List[ViewerFlowTimelinePoint] = Field(default_factory=list)
