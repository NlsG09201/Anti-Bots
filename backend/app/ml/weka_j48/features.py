"""Feature vectors for per-viewer bot classification (Weka J48 / compatible trees)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.infrastructure.database.models import ViewerSession

ATTRIBUTE_NAMES: List[str] = [
    "chat_messages",
    "watch_duration_sec",
    "risk_score",
    "has_fingerprint",
    "event_count",
    "proxy_event_ratio",
    "vpn_event_ratio",
    "datacenter_event_ratio",
    "username_length",
    "msgs_per_watch_min",
    "lurker_score",
]

NOMINAL_CLASS = "is_bot"


def sanitize_feature_vector(features: List[float]) -> List[float]:
    """Weka/sklearn fallan con NaN/Inf; normaliza a floats finitos."""
    out: List[float] = []
    for v in features:
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        if not math.isfinite(f):
            f = 0.0
        out.append(f)
    return out


def sanitize_rows(rows: List["ViewerMLRow"]) -> List["ViewerMLRow"]:
    return [
        ViewerMLRow(
            features=sanitize_feature_vector(r.features),
            label=r.label,
            session_id=r.session_id,
            platform_username=r.platform_username,
        )
        for r in rows
    ]


@dataclass
class ViewerMLRow:
    """One labeled or unlabeled training / inference row."""

    features: List[float]
    label: Optional[str] = None  # "yes" | "no"
    session_id: Optional[str] = None
    platform_username: Optional[str] = None

    @property
    def is_bot_label(self) -> Optional[bool]:
        if self.label is None:
            return None
        return self.label == "yes"


def _lurker_score(chat_messages: int, watch_duration_seconds: int) -> float:
    if watch_duration_seconds <= 0:
        return 1.0 if chat_messages == 0 else 0.0
    minutes = max(watch_duration_seconds / 60.0, 0.1)
    if chat_messages == 0 and minutes >= 3:
        return min(1.0, minutes / 30.0)
    return max(0.0, 1.0 - (chat_messages / max(minutes, 1.0)))


def session_to_features(
    session: ViewerSession,
    event_stats: Optional[Dict[str, Any]] = None,
) -> List[float]:
    stats = event_stats or {}
    event_count = int(stats.get("event_count", 0))
    proxy_ratio = float(stats.get("proxy_ratio", 0.0))
    vpn_ratio = float(stats.get("vpn_ratio", 0.0))
    dc_ratio = float(stats.get("datacenter_ratio", 0.0))

    chat = int(session.chat_messages or 0)
    watch = int(session.watch_duration_seconds or 0)
    username = session.platform_username or ""
    msgs_per_min = chat / max(watch / 60.0, 0.1)

    return [
        float(chat),
        float(watch),
        float(session.risk_score or 0.0),
        1.0 if session.fingerprint_hash else 0.0,
        float(event_count),
        proxy_ratio,
        vpn_ratio,
        dc_ratio,
        float(min(len(username), 64)),
        float(msgs_per_min),
        _lurker_score(chat, watch),
    ]


def aggregate_flow_to_features(
    *,
    chat_messages: int = 0,
    watch_duration_seconds: int = 0,
    risk_score: float = 0.0,
    has_fingerprint: bool = False,
    event_stats: Optional[Dict[str, Any]] = None,
    username: str = "",
) -> List[float]:
    stats = event_stats or {}
    watch = max(int(watch_duration_seconds), 0)
    chat = int(chat_messages)
    msgs_per_min = chat / max(watch / 60.0, 0.1)
    return [
        float(chat),
        float(watch),
        float(risk_score),
        1.0 if has_fingerprint else 0.0,
        float(stats.get("event_count", 0)),
        float(stats.get("proxy_ratio", 0.0)),
        float(stats.get("vpn_ratio", 0.0)),
        float(stats.get("datacenter_ratio", 0.0)),
        float(min(len(username), 64)),
        float(msgs_per_min),
        _lurker_score(chat, watch),
    ]


def insights_record_to_features(rec: Any) -> List[float]:
    """Features sintéticas para bots de Twitch Insights sin sesión local."""
    from app.integrations.twitchinsights.bot_database import TwitchInsightsBotRecord

    if not isinstance(rec, TwitchInsightsBotRecord):
        return aggregate_flow_to_features(risk_score=92.0, watch_duration_seconds=600)
    channel_factor = min(float(rec.channel_count), 500.0) / 500.0
    risk = 98.0 if rec.is_online_now else 90.0 + channel_factor * 5
    return aggregate_flow_to_features(
        chat_messages=0,
        watch_duration_seconds=600,
        risk_score=risk,
        has_fingerprint=False,
        event_stats={
            "event_count": float(rec.channel_count),
            "proxy_ratio": 0.3,
            "vpn_ratio": 0.2,
            "datacenter_ratio": 0.4,
        },
        username=rec.username,
    )


def label_from_session(session: ViewerSession, *, force_bot: bool = False) -> str:
    if force_bot or session.is_suspected_bot or (session.risk_score or 0) >= 80:
        return "yes"
    if (session.risk_score or 0) < 35 and not session.is_suspected_bot:
        return "no"
    return "yes" if session.is_suspected_bot else "no"
