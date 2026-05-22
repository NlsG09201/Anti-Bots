"""Schemas for Live Stream Intelligence Monitor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LiveStreamSnapshot(BaseModel):
    stream_id: str
    tenant_id: str
    platform: str
    channel_name: str
    is_live: bool = False
    title: Optional[str] = None
    category: Optional[str] = None
    viewers: int = 0
    likes: int = 0
    follows_total: int = 0
    chatters: int = 0
    duration_seconds: int = 0
    viewers_per_minute: float = 0.0
    follows_per_minute: float = 0.0
    messages_per_minute: float = 0.0
    engagement_score: float = 50.0
    growth_velocity: float = 0.0
    viewer_to_chat_ratio: float = 0.0
    organic_engagement_score: float = 50.0
    suspicious_activity_score: float = 0.0
    synthetic_audience_probability: float = 0.0
    live_trust_score: float = 50.0
    bot_probability: float = 0.0
    viewbot_probability: float = 0.0
    suspicious_growth: bool = False
    flags: List[str] = Field(default_factory=list)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class StreamRankingEntry(BaseModel):
    stream_id: str
    channel_name: str
    platform: str
    rank: int
    score: float
    metric: str
    is_live: bool = False


class StreamComparisonRow(BaseModel):
    stream_id: str
    channel_name: str
    platform: str
    viewers: int
    messages_per_minute: float
    engagement_score: float
    growth_velocity: float
    bot_probability: float
    organic_engagement_score: float
    suspicious_activity_score: float


class LiveIntelOverview(BaseModel):
    tenant_id: str
    live_count: int = 0
    monitored_count: int = 0
    suspicious_live: int = 0
    avg_engagement: float = 0.0
    rankings_suspicious: List[StreamRankingEntry] = Field(default_factory=list)
    rankings_organic: List[StreamRankingEntry] = Field(default_factory=list)
    rankings_anomaly_growth: List[StreamRankingEntry] = Field(default_factory=list)
    snapshots: List[LiveStreamSnapshot] = Field(default_factory=list)
    heatmap: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
