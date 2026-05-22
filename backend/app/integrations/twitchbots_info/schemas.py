"""Schemas for TwitchBots.info public bot directory API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TwitchBotsTypeInfo(BaseModel):
    id: int
    name: str = ""
    multi_channel: bool = False
    description: str = ""
    active: bool = True


class TwitchBotsBotRecord(BaseModel):
    twitch_id: str
    username: str
    type_id: Optional[int] = None
    type_name: str = ""
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    last_update: Optional[str] = None
    is_known_bot: bool = True
    canonical_url: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Dict[str, Any], type_name: str = "") -> "TwitchBotsBotRecord":
        return cls(
            twitch_id=str(payload.get("id") or ""),
            username=str(payload.get("username") or ""),
            type_id=int(payload["type"]) if payload.get("type") is not None else None,
            type_name=type_name,
            channel_id=str(payload["channelID"]) if payload.get("channelID") else None,
            channel_name=str(payload["channelName"]) if payload.get("channelName") else None,
            last_update=str(payload.get("lastUpdate") or "") or None,
            is_known_bot=True,
            canonical_url=(payload.get("_links") or {}).get("alternate"),
            raw=payload,
        )


class UserReputationScores(BaseModel):
    bot_known_score: float = 0.0
    trust_score: float = 100.0
    suspicious_score: float = 0.0
    bot_type: Optional[str] = None
    source_detection: str = "twitchbots_info"

    @classmethod
    def for_known_bot(cls, record: TwitchBotsBotRecord, *, base_risk: float) -> "UserReputationScores":
        type_label = record.type_name or (f"type_{record.type_id}" if record.type_id else "bot")
        suspicious = min(100.0, max(base_risk, 88.0))
        return cls(
            bot_known_score=100.0,
            trust_score=max(0.0, 100.0 - suspicious),
            suspicious_score=suspicious,
            bot_type=type_label,
            source_detection="twitchbots_info",
        )

    @classmethod
    def for_unknown(cls) -> "UserReputationScores":
        return cls(
            bot_known_score=0.0,
            trust_score=85.0,
            suspicious_score=5.0,
            bot_type=None,
            source_detection="twitchbots_info",
        )


class TwitchBotsVerificationResult(BaseModel):
    username: str
    twitch_id: Optional[str] = None
    is_known_bot: bool = False
    record: Optional[TwitchBotsBotRecord] = None
    reputation: UserReputationScores = Field(default_factory=UserReputationScores.for_unknown)
    cache_hit: bool = False
    verified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_verdict_dict(self) -> Dict[str, Any]:
        if not self.is_known_bot or not self.record:
            return {
                "is_malicious": False,
                "risk_score": float(self.reputation.suspicious_score),
                "risk_description": (
                    "No aparece en el directorio publico TwitchBots.info."
                ),
                "source": "twitchbots_info",
                "needs_ai": False,
                "twitchbots_info": {
                    "is_known_bot": False,
                    "twitch_id": self.twitch_id,
                },
            }
        rec = self.record
        return {
            "is_malicious": True,
            "risk_score": float(self.reputation.suspicious_score),
            "risk_description": (
                f"Bot publico conocido ({rec.type_name or 'catalogado'}): "
                f"{rec.username} en TwitchBots.info."
            ),
            "source": "twitchbots_info",
            "needs_ai": False,
            "twitchbots_info": {
                "is_known_bot": True,
                "twitch_id": rec.twitch_id,
                "username": rec.username,
                "type_id": rec.type_id,
                "type_name": rec.type_name,
                "canonical_url": rec.canonical_url,
                "bot_known_score": self.reputation.bot_known_score,
                "trust_score": self.reputation.trust_score,
                "suspicious_score": self.reputation.suspicious_score,
                "bot_type": self.reputation.bot_type,
                "source_detection": self.reputation.source_detection,
            },
        }


class TwitchBotsOverviewStats(BaseModel):
    enabled: bool = True
    total_verifications: int = 0
    known_bots_detected: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    last_detection_at: Optional[str] = None
    recent_detections: List[Dict[str, Any]] = Field(default_factory=list)
    top_bot_types: List[Dict[str, Any]] = Field(default_factory=list)
