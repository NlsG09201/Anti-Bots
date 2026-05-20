"""Pydantic schemas for AI intelligence outputs."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatClassification(str, Enum):
    NONE = "none"
    VIEWBOT = "viewbot"
    RAID = "raid"
    AUTOMATION = "automation"
    COORDINATED = "coordinated"
    FOLLOW_BOT = "follow_bot"
    CHAT_SPAM = "chat_spam"


class AIAssessment(BaseModel):
    """Unified real-time AI assessment for a stream or event."""

    risk_score: float = Field(ge=0, le=100, description="Dynamic composite risk 0-100")
    attack_probability: float = Field(ge=0, le=1, description="P(attack in next window)")
    threat_level: ThreatLevel = ThreatLevel.LOW
    classification: ThreatClassification = ThreatClassification.NONE
    early_warning: bool = False
    confidence: float = Field(ge=0, le=1, default=0.5)
    false_positive_likelihood: float = Field(
        ge=0, le=1, default=0.3, description="Lower = more confident threat"
    )

    anomaly_score: float = 0.0
    bot_probability: float = 0.0
    raid_probability: float = 0.0
    viewbot_probability: float = 0.0
    automation_probability: float = 0.0
    coordination_score: float = 0.0

    flags: List[str] = Field(default_factory=list)
    model_contributions: Dict[str, float] = Field(default_factory=dict)
    features_snapshot: Dict[str, float] = Field(default_factory=dict)

    recommended_action: str = "monitor"
    recommendations: List[str] = Field(default_factory=list)
    auto_mitigate: bool = False
    mitigation_targets: List[Dict[str, str]] = Field(default_factory=list)

    reputation_delta: float = 0.0
    model_version: str = "1.0.0"
    inference_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
