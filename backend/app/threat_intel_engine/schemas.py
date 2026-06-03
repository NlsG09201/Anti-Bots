"""Schemas for streaming threat intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EntityReputation(BaseModel):
    entity_key: str
    username: Optional[str] = None
    platform: Optional[str] = None
    trust_score: float = 50.0
    threat_score: float = 0.0
    engagement_score: float = 50.0
    bot_probability: float = 0.0
    coordination_score: float = 0.0
    spam_probability: float = 0.0
    raid_likelihood: float = 0.0
    synthetic_engagement_score: float = 0.0
    activity_count: int = 0
    streams_seen: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EngagementMetrics(BaseModel):
    stream_id: str
    viewers_total: int = 0
    viewers_suspected: int = 0
    viewers_real_estimate: int = 0
    engagement_percent: float = 0.0
    active_chatters: int = 0
    unique_chatters: int = 0
    messages_per_minute: float = 0.0
    viewer_to_chat_ratio: float = 0.0
    engagement_health_score: float = 50.0
    growth_anomaly: bool = False
    lexical_diversity: float = 0.0
    synthetic_engagement_score: float = 0.0
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GraphNode(BaseModel):
    id: str
    label: str
    threat_score: float = 0.0
    bot_probability: float = 0.0
    platform: Optional[str] = None
    cluster_id: Optional[int] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    relation: str = "correlated"


class ThreatGraphSnapshot(BaseModel):
    stream_id: str
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    bot_clusters: List[List[str]] = Field(default_factory=list)
    coordination_score: float = 0.0
    community_count: int = 0
    modularity_score: float = 0.0
    high_centrality_nodes: List[str] = Field(default_factory=list)


class ThreatIntelAssessment(BaseModel):
    entity_key: Optional[str] = None
    reputation: Optional[EntityReputation] = None
    engagement: Optional[EngagementMetrics] = None
    graph: Optional[ThreatGraphSnapshot] = None
    bot_probability: float = 0.0
    attack_severity: float = 0.0
    coordination_score: float = 0.0
    spam_probability: float = 0.0
    raid_likelihood: float = 0.0
    synthetic_audience_score: float = 0.0
    trust_score: float = 50.0
    behavioral: Dict[str, Any] = Field(default_factory=dict)
    network_reputation: Dict[str, Any] = Field(default_factory=dict)
    flags: List[str] = Field(default_factory=list)
    ai_insights: List[str] = Field(default_factory=list)
    cross_platform_matches: List[Dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
