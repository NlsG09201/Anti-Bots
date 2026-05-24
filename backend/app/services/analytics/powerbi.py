from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

import httpx
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_intel.orchestrator import get_ai_orchestrator
from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    AlertSeverity,
    Attack,
    Platform,
    Stream,
    StreamEvent,
    User,
    ViewerSession,
)
from app.infrastructure.mongodb.client import get_mongo_db
from app.live_intel.mongo_store import LiveIntelMongoStore
from app.threat_intel_engine.mongo_store import (
    COL_ENGAGEMENT,
    COL_ENTITIES,
    COL_PREDICTIONS,
)

logger = get_logger(__name__)
settings = get_settings()

FOLLOW_EVENT_TYPES = {"follow", "user_follow", "followbot_follow"}
CHAT_EVENT_TYPES = {"chat_message", "message"}
JOIN_EVENT_TYPES = {"viewer_join", "join", "viewer_pulse"}

EXPORT_DATASETS = (
    "platforms",
    "streamers",
    "streams",
    "viewers",
    "suspicious_viewers",
    "attacks",
    "follows",
    "engagement_metrics",
    "ai_predictions",
    "threat_scores",
    "chat_activity",
    "bot_profiles",
)

POWERBI_TABLE_DEFINITIONS: Dict[str, List[Dict[str, str]]] = {
    "platforms": [
        {"name": "platform_key", "dataType": "string"},
        {"name": "platform_name", "dataType": "string"},
        {"name": "streams_total", "dataType": "Int64"},
        {"name": "streams_live", "dataType": "Int64"},
        {"name": "viewer_count", "dataType": "Int64"},
        {"name": "suspicious_viewers", "dataType": "Int64"},
        {"name": "active_attacks", "dataType": "Int64"},
        {"name": "engagement_score", "dataType": "Double"},
        {"name": "threat_score", "dataType": "Double"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "streamers": [
        {"name": "streamer_id", "dataType": "string"},
        {"name": "tenant_id", "dataType": "string"},
        {"name": "email", "dataType": "string"},
        {"name": "username", "dataType": "string"},
        {"name": "role", "dataType": "string"},
        {"name": "streams_total", "dataType": "Int64"},
        {"name": "streams_live", "dataType": "Int64"},
        {"name": "viewer_count", "dataType": "Int64"},
        {"name": "suspicious_viewers", "dataType": "Int64"},
        {"name": "active_attacks", "dataType": "Int64"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "streams": [
        {"name": "stream_id", "dataType": "string"},
        {"name": "tenant_id", "dataType": "string"},
        {"name": "streamer_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "platform_name", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "external_id", "dataType": "string"},
        {"name": "is_live", "dataType": "bool"},
        {"name": "viewer_count", "dataType": "Int64"},
        {"name": "monitor_mode", "dataType": "bool"},
        {"name": "auto_mitigate", "dataType": "bool"},
        {"name": "force_monitor", "dataType": "bool"},
        {"name": "created_at", "dataType": "DateTime"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "viewers": [
        {"name": "viewer_session_id", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "streamer_id", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "platform_user_id", "dataType": "string"},
        {"name": "platform_username", "dataType": "string"},
        {"name": "ip_address", "dataType": "string"},
        {"name": "fingerprint_hash", "dataType": "string"},
        {"name": "is_active", "dataType": "bool"},
        {"name": "is_suspected_bot", "dataType": "bool"},
        {"name": "risk_score", "dataType": "Double"},
        {"name": "chat_messages", "dataType": "Int64"},
        {"name": "watch_duration_seconds", "dataType": "Int64"},
        {"name": "joined_at", "dataType": "DateTime"},
        {"name": "left_at", "dataType": "DateTime"},
        {"name": "source", "dataType": "string"},
    ],
    "suspicious_viewers": [
        {"name": "viewer_session_id", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "platform_username", "dataType": "string"},
        {"name": "risk_score", "dataType": "Double"},
        {"name": "bot_probability", "dataType": "Double"},
        {"name": "confidence", "dataType": "Double"},
        {"name": "reason", "dataType": "string"},
        {"name": "source", "dataType": "string"},
        {"name": "chat_messages", "dataType": "Int64"},
        {"name": "joined_at", "dataType": "DateTime"},
    ],
    "attacks": [
        {"name": "attack_id", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "attack_type", "dataType": "string"},
        {"name": "severity", "dataType": "string"},
        {"name": "status", "dataType": "string"},
        {"name": "risk_score", "dataType": "Double"},
        {"name": "confidence", "dataType": "Double"},
        {"name": "affected_users", "dataType": "Int64"},
        {"name": "source_ip_count", "dataType": "Int64"},
        {"name": "fingerprint_count", "dataType": "Int64"},
        {"name": "mitigation_action", "dataType": "string"},
        {"name": "created_at", "dataType": "DateTime"},
        {"name": "mitigated_at", "dataType": "DateTime"},
        {"name": "resolved_at", "dataType": "DateTime"},
    ],
    "follows": [
        {"name": "event_id", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "platform_user_id", "dataType": "string"},
        {"name": "platform_username", "dataType": "string"},
        {"name": "risk_score", "dataType": "Double"},
        {"name": "is_proxy", "dataType": "bool"},
        {"name": "is_vpn", "dataType": "bool"},
        {"name": "is_tor", "dataType": "bool"},
        {"name": "country_code", "dataType": "string"},
        {"name": "created_at", "dataType": "DateTime"},
    ],
    "engagement_metrics": [
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "viewers_total", "dataType": "Int64"},
        {"name": "viewers_suspected", "dataType": "Int64"},
        {"name": "viewers_real_estimate", "dataType": "Int64"},
        {"name": "engagement_percent", "dataType": "Double"},
        {"name": "active_chatters", "dataType": "Int64"},
        {"name": "unique_chatters", "dataType": "Int64"},
        {"name": "messages_per_minute", "dataType": "Double"},
        {"name": "viewer_to_chat_ratio", "dataType": "Double"},
        {"name": "engagement_health_score", "dataType": "Double"},
        {"name": "growth_anomaly", "dataType": "bool"},
        {"name": "lexical_diversity", "dataType": "Double"},
        {"name": "synthetic_engagement_score", "dataType": "Double"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "ai_predictions": [
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "risk_score", "dataType": "Double"},
        {"name": "attack_probability", "dataType": "Double"},
        {"name": "bot_probability", "dataType": "Double"},
        {"name": "anomaly_score", "dataType": "Double"},
        {"name": "viewbot_probability", "dataType": "Double"},
        {"name": "automation_probability", "dataType": "Double"},
        {"name": "coordination_score", "dataType": "Double"},
        {"name": "classification", "dataType": "string"},
        {"name": "threat_level", "dataType": "string"},
        {"name": "recommended_action", "dataType": "string"},
        {"name": "model_version", "dataType": "string"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "threat_scores": [
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "viewer_count", "dataType": "Int64"},
        {"name": "suspicious_viewers", "dataType": "Int64"},
        {"name": "suspicious_ratio", "dataType": "Double"},
        {"name": "active_attacks", "dataType": "Int64"},
        {"name": "attack_frequency", "dataType": "Double"},
        {"name": "avg_attack_risk", "dataType": "Double"},
        {"name": "max_attack_risk", "dataType": "Double"},
        {"name": "proxy_event_ratio", "dataType": "Double"},
        {"name": "engagement_score", "dataType": "Double"},
        {"name": "ai_risk_score", "dataType": "Double"},
        {"name": "threat_score", "dataType": "Double"},
        {"name": "threat_level", "dataType": "string"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
    "chat_activity": [
        {"name": "activity_key", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "bucket_start", "dataType": "DateTime"},
        {"name": "messages", "dataType": "Int64"},
        {"name": "unique_users", "dataType": "Int64"},
        {"name": "suspicious_messages", "dataType": "Int64"},
        {"name": "message_risk_avg", "dataType": "Double"},
    ],
    "bot_profiles": [
        {"name": "bot_profile_key", "dataType": "string"},
        {"name": "canonical_username", "dataType": "string"},
        {"name": "platform_key", "dataType": "string"},
        {"name": "stream_id", "dataType": "string"},
        {"name": "channel_name", "dataType": "string"},
        {"name": "threat_score", "dataType": "Double"},
        {"name": "bot_probability", "dataType": "Double"},
        {"name": "trust_score", "dataType": "Double"},
        {"name": "source", "dataType": "string"},
        {"name": "flags", "dataType": "string"},
        {"name": "updated_at", "dataType": "DateTime"},
    ],
}

POWERBI_RELATIONSHIPS = [
    {"fromTable": "platforms", "fromColumn": "platform_key", "toTable": "streams", "toColumn": "platform_key"},
    {"fromTable": "streamers", "fromColumn": "streamer_id", "toTable": "streams", "toColumn": "streamer_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "viewers", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "suspicious_viewers", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "attacks", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "follows", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "engagement_metrics", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "ai_predictions", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "threat_scores", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "chat_activity", "toColumn": "stream_id"},
    {"fromTable": "streams", "fromColumn": "stream_id", "toTable": "bot_profiles", "toColumn": "stream_id"},
]

POWERBI_DAX_MEASURES = {
    "Viewers Monitoreados": "Viewers Monitoreados = DISTINCTCOUNT(viewers[viewer_session_id])",
    "Viewers Sospechosos": "Viewers Sospechosos = COUNTROWS(suspicious_viewers)",
    "Ataques Detectados": "Ataques Detectados = COUNTROWS(attacks)",
    "Streams Activos": "Streams Activos = CALCULATE(COUNTROWS(streams), streams[is_live] = TRUE())",
    "Bots Detectados": "Bots Detectados = DISTINCTCOUNT(bot_profiles[canonical_username])",
    "Follows Sospechosos": "Follows Sospechosos = CALCULATE(COUNTROWS(follows), follows[risk_score] >= 60)",
    "Engagement Rate": "Engagement Rate = DIVIDE(SUM(engagement_metrics[active_chatters]), SUM(engagement_metrics[viewers_total]), 0)",
    "Suspicious Ratio": "Suspicious Ratio = DIVIDE([Viewers Sospechosos], [Viewers Monitoreados], 0)",
    "Attack Frequency": "Attack Frequency = DIVIDE(COUNTROWS(attacks), DISTINCTCOUNT(streams[stream_id]), 0)",
    "Viewers Growth": "Viewers Growth = AVERAGE(threat_scores[viewer_count])",
    "Threat Average": "Threat Average = AVERAGE(threat_scores[threat_score])",
    "Anomaly Percentage": "Anomaly Percentage = DIVIDE(CALCULATE(COUNTROWS(ai_predictions), ai_predictions[anomaly_score] >= 60), COUNTROWS(ai_predictions), 0)",
    "Attack Severity": "Attack Severity = AVERAGE(attacks[risk_score])",
    "Retention": "Retention = DIVIDE(SUM(viewers[watch_duration_seconds]), [Viewers Monitoreados], 0)",
    "Viewers Quality": "Viewers Quality = 1 - [Suspicious Ratio]",
    "Threat Score Global": "Threat Score Global = AVERAGE(platforms[threat_score])",
    "Engagement Score": "Engagement Score = AVERAGE(engagement_metrics[engagement_health_score])",
    "Bot Probability": "Bot Probability = AVERAGE(ai_predictions[bot_probability])",
}


def powerbi_model_manifest() -> Dict[str, Any]:
    return {
        "dataset_name": settings.powerbi_dataset_name,
        "tables": POWERBI_TABLE_DEFINITIONS,
        "relationships": POWERBI_RELATIONSHIPS,
        "measures": POWERBI_DAX_MEASURES,
    }


@dataclass
class StreamContext:
    stream: Stream
    owner: User


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _serialize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, default=str)
    return value


def _serialize_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_serialize_payload(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_payload(v) for k, v in value.items()}
    return value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _platform_key(value: Any) -> str:
    if isinstance(value, Platform):
        return value.value
    return str(value or "").lower()


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _severity_rank(value: str) -> int:
    order = {
        AlertSeverity.CRITICAL.value: 4,
        AlertSeverity.HIGH.value: 3,
        AlertSeverity.MEDIUM.value: 2,
        AlertSeverity.LOW.value: 1,
    }
    return order.get(value, 0)


class AnalyticsWarehouseService:
    def __init__(self, db: AsyncSession, tenant_id: UUID, *, hours: int = 168) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.hours = max(1, min(hours, 24 * 90))
        self.since = _now_utc() - timedelta(hours=self.hours)
        self.snapshot_at = _now_utc()
        self._streams: Optional[List[StreamContext]] = None
        self._events: Optional[List[StreamEvent]] = None
        self._attacks: Optional[List[Attack]] = None
        self._viewers: Optional[List[ViewerSession]] = None
        self._engagement_docs: Optional[Dict[str, Dict[str, Any]]] = None
        self._entity_docs: Optional[List[Dict[str, Any]]] = None

    async def build_export_bundle(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "platforms": await self.platform_rows(),
            "streamers": await self.streamer_rows(),
            "streams": await self.stream_rows(),
            "viewers": await self.viewer_rows(),
            "suspicious_viewers": await self.suspicious_viewer_rows(),
            "attacks": await self.attack_rows(),
            "follows": await self.follow_rows(),
            "engagement_metrics": await self.engagement_rows(),
            "ai_predictions": await self.ai_prediction_rows(),
            "threat_scores": await self.threat_score_rows(),
            "chat_activity": await self.chat_activity_rows(),
            "bot_profiles": await self.bot_profile_rows(),
        }

    async def overview(self) -> Dict[str, Any]:
        bundle = await self.build_export_bundle()
        streams = bundle["streams"]
        viewers = bundle["viewers"]
        suspicious = bundle["suspicious_viewers"]
        attacks = bundle["attacks"]
        follows = bundle["follows"]
        engagement = bundle["engagement_metrics"]
        threat_scores = bundle["threat_scores"]
        ai_predictions = bundle["ai_predictions"]

        attack_counter = Counter(row["attack_type"] for row in attacks)
        platform_attacks = Counter(row["platform_key"] for row in attacks)
        suspicious_streams = sorted(
            threat_scores,
            key=lambda row: (-_safe_float(row["threat_score"]), -_safe_int(row["viewer_count"])),
        )[:5]
        top_streamers = sorted(
            bundle["streamers"],
            key=lambda row: (-_safe_int(row["active_attacks"]), -_safe_int(row["viewer_count"])),
        )[:5]

        viewers_per_minute = round(
            len([e for e in await self._load_events() if e.event_type in JOIN_EVENT_TYPES]) / max(self.hours * 60, 1),
            2,
        )
        follows_per_minute = round(len(follows) / max(self.hours * 60, 1), 2)
        messages_per_minute = round(
            sum(row["messages"] for row in bundle["chat_activity"]) / max(self.hours * 60, 1),
            2,
        )
        anomalies = len([row for row in ai_predictions if _safe_float(row["anomaly_score"]) >= 60])
        threat_avg = round(
            sum(_safe_float(row["threat_score"]) for row in threat_scores) / max(len(threat_scores), 1),
            2,
        )
        engagement_avg = round(
            sum(_safe_float(row["engagement_health_score"]) for row in engagement) / max(len(engagement), 1),
            2,
        )

        return {
            "updated_at": self.snapshot_at.isoformat(),
            "window_hours": self.hours,
            "metrics_globales": {
                "viewers_monitoreados": len(viewers),
                "viewers_sospechosos": len(suspicious),
                "ataques_detectados": len(attacks),
                "streams_activos": len([row for row in streams if row["is_live"]]),
                "bots_detectados": len(bundle["bot_profiles"]),
                "follows_sospechosos": len([row for row in follows if _safe_float(row["risk_score"]) >= 60]),
                "engagement_score": engagement_avg,
                "threat_score": threat_avg,
                "riesgo_global": max(threat_avg, round(sum(_safe_float(r["risk_score"]) for r in ai_predictions) / max(len(ai_predictions), 1), 2)),
            },
            "metricas_tiempo_real": {
                "viewers_por_minuto": viewers_per_minute,
                "follows_por_minuto": follows_per_minute,
                "mensajes_por_minuto": messages_per_minute,
                "spikes_sospechosos": len([row for row in attacks if row["attack_type"] in {"viewbot", "coordinated"}]),
                "raids_activas": len([row for row in attacks if row["attack_type"] == "chat_raid" and row["status"] == "active"]),
                "anomalias": anomalies,
            },
            "kpis": {
                "porcentaje_engagement_real": round(
                    (sum(_safe_float(row["engagement_percent"]) for row in engagement) / max(len(engagement), 1)),
                    2,
                ),
                "porcentaje_bots": round((len(suspicious) / max(len(viewers), 1)) * 100, 2),
                "streams_mas_sospechosos": suspicious_streams,
                "plataformas_mas_atacadas": [
                    {"platform": key, "attacks": count}
                    for key, count in platform_attacks.most_common(4)
                ],
                "top_ataques": [
                    {"attack_type": key, "count": count}
                    for key, count in attack_counter.most_common(6)
                ],
                "top_streamers_monitoreados": top_streamers,
            },
        }

    async def live_metrics(self) -> Dict[str, Any]:
        bundle = await self.build_export_bundle()
        anomalies = await LiveIntelMongoStore().recent_anomalies(str(self.tenant_id), limit=20)
        threat_scores = bundle["threat_scores"]
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "window_hours": self.hours,
            "global": {
                "streams_live": len([row for row in bundle["streams"] if row["is_live"]]),
                "viewers_current": sum(_safe_int(row["viewer_count"]) for row in bundle["streams"] if row["is_live"]),
                "active_attacks": len([row for row in bundle["attacks"] if row["status"] == "active"]),
                "suspicious_viewers": len(bundle["suspicious_viewers"]),
            },
            "velocities": {
                "viewers_per_minute": round(
                    len([e for e in await self._load_events() if e.event_type in JOIN_EVENT_TYPES]) / max(self.hours * 60, 1),
                    2,
                ),
                "follows_per_minute": round(len(bundle["follows"]) / max(self.hours * 60, 1), 2),
                "messages_per_minute": round(
                    sum(_safe_int(row["messages"]) for row in bundle["chat_activity"]) / max(self.hours * 60, 1),
                    2,
                ),
            },
            "anomalies": {
                "count": len(anomalies),
                "high_risk": len([row for row in anomalies if _safe_float(row.get("risk_score")) >= 70]),
                "items": [_serialize_payload(row) for row in anomalies[:10]],
            },
            "top_streams": sorted(
                threat_scores,
                key=lambda row: (-_safe_float(row["threat_score"]), -_safe_int(row["viewer_count"])),
            )[:10],
        }

    async def suspicious_activity(self) -> Dict[str, Any]:
        suspicious = await self.suspicious_viewer_rows()
        threats = await self.threat_score_rows()
        by_platform = Counter(row["platform_key"] for row in suspicious)
        by_source = Counter(row["source"] for row in suspicious)
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "count": len(suspicious),
            "by_platform": [{"platform": key, "count": count} for key, count in by_platform.items()],
            "by_source": [{"source": key, "count": count} for key, count in by_source.items()],
            "top_viewers": sorted(suspicious, key=lambda row: (-_safe_float(row["risk_score"]), row["platform_username"]))[:50],
            "top_streams": sorted(threats, key=lambda row: (-_safe_float(row["suspicious_ratio"]), -_safe_float(row["threat_score"])))[:10],
        }

    async def stream_analytics(self) -> Dict[str, Any]:
        streams = await self.stream_rows()
        engagement = {row["stream_id"]: row for row in await self.engagement_rows()}
        threats = {row["stream_id"]: row for row in await self.threat_score_rows()}
        comparison = []
        for row in streams:
            comparison.append({
                **row,
                "engagement_percent": _safe_float(engagement.get(row["stream_id"], {}).get("engagement_percent")),
                "engagement_score": _safe_float(engagement.get(row["stream_id"], {}).get("engagement_health_score")),
                "threat_score": _safe_float(threats.get(row["stream_id"], {}).get("threat_score")),
                "suspicious_ratio": _safe_float(threats.get(row["stream_id"], {}).get("suspicious_ratio")),
            })
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "count": len(comparison),
            "streams": sorted(comparison, key=lambda row: (-row["threat_score"], -_safe_int(row["viewer_count"]))),
            "platform_summary": await self.platform_rows(),
            "streamers": await self.streamer_rows(),
        }

    async def ai_analytics(self) -> Dict[str, Any]:
        predictions = await self.ai_prediction_rows()
        profiles = await self.bot_profile_rows()
        coordinated = len([row for row in predictions if _safe_float(row["coordination_score"]) >= 60])
        synthetic = len([row for row in predictions if _safe_float(row["bot_probability"]) >= 60])
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "summary": {
                "predictions_total": len(predictions),
                "bot_probability_avg": round(sum(_safe_float(row["bot_probability"]) for row in predictions) / max(len(predictions), 1), 2),
                "anomaly_score_avg": round(sum(_safe_float(row["anomaly_score"]) for row in predictions) / max(len(predictions), 1), 2),
                "threat_score_avg": round(sum(_safe_float(row["risk_score"]) for row in predictions) / max(len(predictions), 1), 2),
                "viewers_coordinados": coordinated,
                "comportamiento_sintetico": synthetic,
            },
            "predictions": sorted(predictions, key=lambda row: (-_safe_float(row["risk_score"]), row["channel_name"]))[:100],
            "bot_profiles": sorted(profiles, key=lambda row: (-_safe_float(row["threat_score"]), row["canonical_username"]))[:100],
        }

    async def engagement_analytics(self) -> Dict[str, Any]:
        engagement = await self.engagement_rows()
        follows = await self.follow_rows()
        chat_activity = await self.chat_activity_rows()
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "summary": {
                "engagement_rate_avg": round(sum(_safe_float(row["engagement_percent"]) for row in engagement) / max(len(engagement), 1), 2),
                "engagement_score_avg": round(sum(_safe_float(row["engagement_health_score"]) for row in engagement) / max(len(engagement), 1), 2),
                "follows_total": len(follows),
                "chat_messages_total": sum(_safe_int(row["messages"]) for row in chat_activity),
            },
            "engagement_metrics": engagement,
            "follows": follows[:200],
            "chat_activity": chat_activity[:200],
        }

    async def attack_analytics(self) -> Dict[str, Any]:
        attacks = await self.attack_rows()
        by_type = Counter(row["attack_type"] for row in attacks)
        by_platform = Counter(row["platform_key"] for row in attacks)
        by_severity = Counter(row["severity"] for row in attacks)
        timeline_buckets: Dict[str, Dict[str, Any]] = {}
        for row in attacks:
            bucket = str(row["created_at"])[:13]
            item = timeline_buckets.setdefault(bucket, {"bucket": bucket, "attacks": 0, "avg_risk": 0.0, "risk_samples": []})
            item["attacks"] += 1
            item["risk_samples"].append(_safe_float(row["risk_score"]))
        timeline = []
        for item in sorted(timeline_buckets.values(), key=lambda data: data["bucket"]):
            samples = item.pop("risk_samples")
            item["avg_risk"] = round(sum(samples) / max(len(samples), 1), 2)
            timeline.append(item)
        return {
            "updated_at": self.snapshot_at.isoformat(),
            "summary": {
                "total": len(attacks),
                "active": len([row for row in attacks if row["status"] == "active"]),
                "critical": len([row for row in attacks if row["severity"] == AlertSeverity.CRITICAL.value]),
                "avg_risk": round(sum(_safe_float(row["risk_score"]) for row in attacks) / max(len(attacks), 1), 2),
            },
            "by_type": [{"attack_type": key, "count": count} for key, count in by_type.most_common()],
            "by_platform": [{"platform": key, "count": count} for key, count in by_platform.most_common()],
            "by_severity": [{"severity": key, "count": count, "rank": _severity_rank(key)} for key, count in by_severity.items()],
            "timeline": timeline,
            "attacks": sorted(attacks, key=lambda row: (-_safe_float(row["risk_score"]), str(row["created_at"])))[:200],
        }

    async def stream_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for ctx in await self._load_streams():
            meta = ctx.stream.settings or {}
            rows.append({
                "stream_id": str(ctx.stream.id),
                "tenant_id": str(ctx.stream.tenant_id),
                "streamer_id": str(ctx.stream.owner_id),
                "platform_key": _platform_key(ctx.stream.platform),
                "platform_name": _platform_key(ctx.stream.platform).upper(),
                "channel_name": ctx.stream.channel_name,
                "external_id": ctx.stream.external_id,
                "is_live": bool(ctx.stream.is_live),
                "viewer_count": _safe_int(ctx.stream.viewer_count),
                "monitor_mode": bool(meta.get("monitor_mode")),
                "auto_mitigate": bool(meta.get("auto_mitigate")),
                "force_monitor": bool(meta.get("force_monitor")),
                "created_at": _to_iso(ctx.stream.created_at),
                "updated_at": self.snapshot_at.isoformat(),
            })
        return rows

    async def streamer_rows(self) -> List[Dict[str, Any]]:
        streams = await self.stream_rows()
        viewer_rows = await self.viewer_rows()
        attacks = await self.attack_rows()
        agg: Dict[str, Dict[str, Any]] = {}
        for ctx in await self._load_streams():
            sid = str(ctx.owner.id)
            agg.setdefault(
                sid,
                {
                    "streamer_id": sid,
                    "tenant_id": str(ctx.owner.tenant_id),
                    "email": ctx.owner.email,
                    "username": ctx.owner.username,
                    "role": _enum_value(ctx.owner.role),
                    "streams_total": 0,
                    "streams_live": 0,
                    "viewer_count": 0,
                    "suspicious_viewers": 0,
                    "active_attacks": 0,
                    "updated_at": self.snapshot_at.isoformat(),
                },
            )
        for row in streams:
            entry = agg[row["streamer_id"]]
            entry["streams_total"] += 1
            entry["streams_live"] += 1 if row["is_live"] else 0
            entry["viewer_count"] += _safe_int(row["viewer_count"])
        for row in viewer_rows:
            if row["is_suspected_bot"]:
                agg[row["streamer_id"]]["suspicious_viewers"] += 1
        stream_owner = {row["stream_id"]: row["streamer_id"] for row in streams}
        for row in attacks:
            streamer_id = stream_owner.get(row["stream_id"])
            if streamer_id and row["status"] == "active":
                agg[streamer_id]["active_attacks"] += 1
        return sorted(agg.values(), key=lambda row: (-row["active_attacks"], -row["viewer_count"]))

    async def platform_rows(self) -> List[Dict[str, Any]]:
        streams = await self.stream_rows()
        suspicious = await self.suspicious_viewer_rows()
        attacks = await self.attack_rows()
        engagement = await self.engagement_rows()
        by_platform: Dict[str, Dict[str, Any]] = {}
        for platform in Platform:
            key = platform.value
            by_platform[key] = {
                "platform_key": key,
                "platform_name": key.upper(),
                "streams_total": 0,
                "streams_live": 0,
                "viewer_count": 0,
                "suspicious_viewers": 0,
                "active_attacks": 0,
                "engagement_score": 0.0,
                "engagement_samples": [],
                "threat_score": 0.0,
                "threat_samples": [],
                "updated_at": self.snapshot_at.isoformat(),
            }
        for row in streams:
            entry = by_platform[row["platform_key"]]
            entry["streams_total"] += 1
            entry["streams_live"] += 1 if row["is_live"] else 0
            entry["viewer_count"] += _safe_int(row["viewer_count"])
        for row in suspicious:
            by_platform[row["platform_key"]]["suspicious_viewers"] += 1
        for row in attacks:
            if row["status"] == "active":
                by_platform[row["platform_key"]]["active_attacks"] += 1
                by_platform[row["platform_key"]]["threat_samples"].append(_safe_float(row["risk_score"]))
        for row in engagement:
            by_platform[row["platform_key"]]["engagement_samples"].append(_safe_float(row["engagement_health_score"]))
        out = []
        for entry in by_platform.values():
            engagement_samples = entry.pop("engagement_samples")
            threat_samples = entry.pop("threat_samples")
            entry["engagement_score"] = round(sum(engagement_samples) / max(len(engagement_samples), 1), 2)
            threat_base = sum(threat_samples) / max(len(threat_samples), 1) if threat_samples else 0.0
            entry["threat_score"] = round(min(100.0, threat_base + (entry["suspicious_viewers"] * 1.5)), 2)
            out.append(entry)
        return sorted(out, key=lambda row: (-row["threat_score"], -row["viewer_count"]))

    async def viewer_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        rows = []
        for session in await self._load_viewers():
            ctx = stream_map.get(str(session.stream_id))
            if not ctx:
                continue
            metrics = session.behavior_metrics or {}
            rows.append({
                "viewer_session_id": str(session.id),
                "stream_id": str(session.stream_id),
                "platform_key": _platform_key(ctx.stream.platform),
                "streamer_id": str(ctx.owner.id),
                "channel_name": ctx.stream.channel_name,
                "platform_user_id": session.platform_user_id,
                "platform_username": session.platform_username,
                "ip_address": session.ip_address,
                "fingerprint_hash": session.fingerprint_hash,
                "is_active": bool(session.is_active),
                "is_suspected_bot": bool(session.is_suspected_bot),
                "risk_score": round(_safe_float(session.risk_score), 2),
                "chat_messages": _safe_int(session.chat_messages),
                "watch_duration_seconds": _safe_int(session.watch_duration_seconds),
                "joined_at": _to_iso(session.joined_at),
                "left_at": _to_iso(session.left_at),
                "source": str(metrics.get("source") or "chat"),
            })
        return rows

    async def suspicious_viewer_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for row in await self.viewer_rows():
            if not row["is_suspected_bot"] and _safe_float(row["risk_score"]) < 55:
                continue
            session = next((s for s in await self._load_viewers() if str(s.id) == row["viewer_session_id"]), None)
            verdict = ((session.behavior_metrics or {}).get("ai_verdict") if session else {}) or {}
            rows.append({
                "viewer_session_id": row["viewer_session_id"],
                "stream_id": row["stream_id"],
                "platform_key": row["platform_key"],
                "channel_name": row["channel_name"],
                "platform_username": row["platform_username"],
                "risk_score": row["risk_score"],
                "bot_probability": round(_safe_float(verdict.get("risk_score")) / 100.0, 4),
                "confidence": round(min(1.0, max(row["risk_score"] / 100.0, 0.5 if row["is_suspected_bot"] else 0.0)), 4),
                "reason": str(verdict.get("risk_description") or "Actividad sospechosa detectada"),
                "source": str(verdict.get("source") or row["source"]),
                "chat_messages": row["chat_messages"],
                "joined_at": row["joined_at"],
            })
        return sorted(rows, key=lambda item: (-_safe_float(item["risk_score"]), item["platform_username"] or ""))

    async def attack_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        rows = []
        for attack in await self._load_attacks():
            ctx = stream_map.get(str(attack.stream_id))
            if not ctx:
                continue
            rows.append({
                "attack_id": str(attack.id),
                "stream_id": str(attack.stream_id),
                "platform_key": _platform_key(ctx.stream.platform),
                "channel_name": ctx.stream.channel_name,
                "attack_type": _enum_value(attack.attack_type),
                "severity": _enum_value(attack.severity),
                "status": attack.status,
                "risk_score": round(_safe_float(attack.risk_score), 2),
                "confidence": round(_safe_float(attack.confidence), 4),
                "affected_users": _safe_int(attack.affected_users),
                "source_ip_count": len(attack.source_ips or []),
                "fingerprint_count": len(attack.fingerprints or []),
                "mitigation_action": _enum_value(attack.mitigation_action),
                "created_at": _to_iso(attack.created_at),
                "mitigated_at": _to_iso(attack.mitigated_at),
                "resolved_at": _to_iso(attack.resolved_at),
            })
        return rows

    async def follow_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        rows = []
        for event in await self._load_events():
            if event.event_type not in FOLLOW_EVENT_TYPES:
                continue
            ctx = stream_map.get(str(event.stream_id))
            if not ctx:
                continue
            rows.append({
                "event_id": str(event.id),
                "stream_id": str(event.stream_id),
                "platform_key": _platform_key(ctx.stream.platform),
                "channel_name": ctx.stream.channel_name,
                "platform_user_id": event.platform_user_id,
                "platform_username": event.platform_username,
                "risk_score": round(_safe_float(event.risk_score), 2),
                "is_proxy": bool(event.is_proxy),
                "is_vpn": bool(event.is_vpn),
                "is_tor": bool(event.is_tor),
                "country_code": event.country_code,
                "created_at": _to_iso(event.created_at),
            })
        return rows

    async def engagement_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        viewer_rows = await self.viewer_rows()
        chat_activity = await self.chat_activity_rows()
        viewers_by_stream: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in viewer_rows:
            viewers_by_stream[row["stream_id"]].append(row)
        chat_by_stream: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in chat_activity:
            chat_by_stream[row["stream_id"]].append(row)

        docs = await self._load_engagement_docs()
        rows = []
        for stream_id, ctx in stream_map.items():
            doc = docs.get(stream_id, {})
            viewers = viewers_by_stream.get(stream_id, [])
            unique_chatters = len({(row.get("platform_username") or row.get("platform_user_id") or "").lower() for row in viewers if (row.get("platform_username") or row.get("platform_user_id"))})
            active_chatters = len([row for row in viewers if _safe_int(row["chat_messages"]) > 0])
            suspected = len([row for row in viewers if row["is_suspected_bot"]])
            messages_total = sum(_safe_int(row["messages"]) for row in chat_by_stream.get(stream_id, []))
            messages_per_minute = round(
                _safe_float(doc.get("messages_per_minute"), messages_total / max(self.hours * 60, 1)),
                2,
            )
            viewers_total = _safe_int(doc.get("viewers_total"), ctx.stream.viewer_count)
            engagement_percent = _safe_float(
                doc.get("engagement_percent"),
                (active_chatters / max(viewers_total, 1)) * 100,
            )
            engagement_health = _safe_float(
                doc.get("engagement_health_score"),
                min(100.0, max(0.0, engagement_percent * 1.2)),
            )
            viewer_to_chat_ratio = _safe_float(
                doc.get("viewer_to_chat_ratio"),
                viewers_total / max(active_chatters, 1),
            )
            rows.append({
                "stream_id": stream_id,
                "platform_key": _platform_key(ctx.stream.platform),
                "channel_name": ctx.stream.channel_name,
                "viewers_total": viewers_total,
                "viewers_suspected": _safe_int(doc.get("viewers_suspected"), suspected),
                "viewers_real_estimate": _safe_int(doc.get("viewers_real_estimate"), max(viewers_total - suspected, 0)),
                "engagement_percent": round(engagement_percent, 2),
                "active_chatters": _safe_int(doc.get("active_chatters"), active_chatters),
                "unique_chatters": _safe_int(doc.get("unique_chatters"), unique_chatters),
                "messages_per_minute": messages_per_minute,
                "viewer_to_chat_ratio": round(viewer_to_chat_ratio, 2),
                "engagement_health_score": round(engagement_health, 2),
                "growth_anomaly": bool(doc.get("growth_anomaly", suspected > 10 and viewers_total > 0)),
                "lexical_diversity": round(_safe_float(doc.get("lexical_diversity"), 0.0), 2),
                "synthetic_engagement_score": round(_safe_float(doc.get("synthetic_engagement_score"), min(100.0, suspected * 4.0)), 2),
                "updated_at": _to_iso(doc.get("updated_at")) or self.snapshot_at.isoformat(),
            })
        return rows

    async def ai_prediction_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        rows = []
        orch = get_ai_orchestrator()
        for stream_id, ctx in stream_map.items():
            pred = await orch.get_stream_prediction(ctx.stream.id)
            if not pred:
                continue
            payload = pred.model_dump() if hasattr(pred, "model_dump") else pred
            rows.append({
                "stream_id": stream_id,
                "platform_key": _platform_key(ctx.stream.platform),
                "channel_name": ctx.stream.channel_name,
                "risk_score": round(_safe_float(payload.get("risk_score")), 2),
                "attack_probability": round(_safe_float(payload.get("attack_probability")), 4),
                "bot_probability": round(_safe_float(payload.get("bot_probability")), 4),
                "anomaly_score": round(_safe_float(payload.get("anomaly_score")), 2),
                "viewbot_probability": round(_safe_float(payload.get("viewbot_probability")), 4),
                "automation_probability": round(_safe_float(payload.get("automation_probability")), 4),
                "coordination_score": round(_safe_float(payload.get("coordination_score")), 4),
                "classification": str(payload.get("classification") or "unknown"),
                "threat_level": str(payload.get("threat_level") or "unknown"),
                "recommended_action": str(payload.get("recommended_action") or "monitor"),
                "model_version": str(payload.get("model_version") or "n/a"),
                "updated_at": self.snapshot_at.isoformat(),
            })
        return rows

    async def threat_score_rows(self) -> List[Dict[str, Any]]:
        streams = {row["stream_id"]: row for row in await self.stream_rows()}
        engagement = {row["stream_id"]: row for row in await self.engagement_rows()}
        ai_predictions = {row["stream_id"]: row for row in await self.ai_prediction_rows()}
        viewers = defaultdict(list)
        for row in await self.viewer_rows():
            viewers[row["stream_id"]].append(row)
        attacks = defaultdict(list)
        for row in await self.attack_rows():
            attacks[row["stream_id"]].append(row)
        events = defaultdict(list)
        for event in await self._load_events():
            events[str(event.stream_id)].append(event)

        rows = []
        for stream_id, stream in streams.items():
            stream_viewers = viewers.get(stream_id, [])
            stream_attacks = attacks.get(stream_id, [])
            stream_events = events.get(stream_id, [])
            suspicious = len([row for row in stream_viewers if row["is_suspected_bot"]])
            suspicious_ratio = suspicious / max(len(stream_viewers), 1)
            avg_attack_risk = sum(_safe_float(row["risk_score"]) for row in stream_attacks) / max(len(stream_attacks), 1)
            max_attack_risk = max((_safe_float(row["risk_score"]) for row in stream_attacks), default=0.0)
            proxy_events = len([e for e in stream_events if e.is_proxy or e.is_vpn or e.is_tor])
            proxy_ratio = proxy_events / max(len(stream_events), 1)
            engagement_score = _safe_float(engagement.get(stream_id, {}).get("engagement_health_score"), 0.0)
            ai_risk = _safe_float(ai_predictions.get(stream_id, {}).get("risk_score"), 0.0)
            attack_frequency = len(stream_attacks) / max(self.hours / 24.0, 1.0)
            threat_score = min(
                100.0,
                (suspicious_ratio * 35.0)
                + (avg_attack_risk * 0.35)
                + (proxy_ratio * 20.0)
                + (ai_risk * 0.30)
                + max(0.0, 100.0 - engagement_score) * 0.15,
            )
            if threat_score >= 80:
                threat_level = "critical"
            elif threat_score >= 60:
                threat_level = "high"
            elif threat_score >= 35:
                threat_level = "medium"
            else:
                threat_level = "low"
            rows.append({
                "stream_id": stream_id,
                "platform_key": stream["platform_key"],
                "channel_name": stream["channel_name"],
                "viewer_count": _safe_int(stream["viewer_count"]),
                "suspicious_viewers": suspicious,
                "suspicious_ratio": round(suspicious_ratio, 4),
                "active_attacks": len([row for row in stream_attacks if row["status"] == "active"]),
                "attack_frequency": round(attack_frequency, 4),
                "avg_attack_risk": round(avg_attack_risk, 2),
                "max_attack_risk": round(max_attack_risk, 2),
                "proxy_event_ratio": round(proxy_ratio, 4),
                "engagement_score": round(engagement_score, 2),
                "ai_risk_score": round(ai_risk, 2),
                "threat_score": round(threat_score, 2),
                "threat_level": threat_level,
                "updated_at": self.snapshot_at.isoformat(),
            })
        return sorted(rows, key=lambda row: (-_safe_float(row["threat_score"]), -_safe_int(row["viewer_count"])))

    async def chat_activity_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        buckets: Dict[tuple[str, str], Dict[str, Any]] = {}
        for event in await self._load_events():
            if event.event_type not in CHAT_EVENT_TYPES:
                continue
            key = (str(event.stream_id), event.created_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00+00:00"))
            ctx = stream_map.get(str(event.stream_id))
            if not ctx:
                continue
            entry = buckets.setdefault(
                key,
                {
                    "activity_key": f"{key[0]}:{key[1]}",
                    "stream_id": key[0],
                    "platform_key": _platform_key(ctx.stream.platform),
                    "channel_name": ctx.stream.channel_name,
                    "bucket_start": key[1],
                    "messages": 0,
                    "unique_users_set": set(),
                    "suspicious_messages": 0,
                    "risk_sum": 0.0,
                },
            )
            entry["messages"] += 1
            if event.platform_username:
                entry["unique_users_set"].add(event.platform_username.lower())
            if _safe_float(event.risk_score) >= 60:
                entry["suspicious_messages"] += 1
            entry["risk_sum"] += _safe_float(event.risk_score)

        rows = []
        for entry in sorted(buckets.values(), key=lambda row: (row["bucket_start"], row["channel_name"])):
            unique_users = entry.pop("unique_users_set")
            risk_sum = entry.pop("risk_sum")
            entry["unique_users"] = len(unique_users)
            entry["message_risk_avg"] = round(risk_sum / max(entry["messages"], 1), 2)
            rows.append(entry)
        return rows

    async def bot_profile_rows(self) -> List[Dict[str, Any]]:
        stream_map = {str(ctx.stream.id): ctx for ctx in await self._load_streams()}
        docs = await self._load_entity_docs()
        rows = []
        if docs:
            for doc in docs[:500]:
                stream_id = str(doc.get("stream_id") or "")
                ctx = stream_map.get(stream_id)
                rows.append({
                    "bot_profile_key": str(doc.get("entity_key") or doc.get("_id") or ""),
                    "canonical_username": doc.get("username") or doc.get("canonical_username") or doc.get("entity_key"),
                    "platform_key": doc.get("platform") or (ctx.stream.platform.value if ctx else ""),
                    "stream_id": stream_id,
                    "channel_name": ctx.stream.channel_name if ctx else "",
                    "threat_score": round(_safe_float(doc.get("threat_score")), 2),
                    "bot_probability": round(_safe_float(doc.get("bot_probability")), 4),
                    "trust_score": round(_safe_float(doc.get("trust_score")), 2),
                    "source": "threat_intel",
                    "flags": json.dumps(doc.get("flags") or [], ensure_ascii=True),
                    "updated_at": _to_iso(doc.get("updated_at")) or self.snapshot_at.isoformat(),
                })
        if rows:
            return sorted(rows, key=lambda row: (-_safe_float(row["threat_score"]), row["canonical_username"] or ""))

        for row in await self.suspicious_viewer_rows():
            rows.append({
                "bot_profile_key": row["viewer_session_id"],
                "canonical_username": row["platform_username"],
                "platform_key": row["platform_key"],
                "stream_id": row["stream_id"],
                "channel_name": row["channel_name"],
                "threat_score": row["risk_score"],
                "bot_probability": row["bot_probability"],
                "trust_score": round(max(0.0, 100.0 - _safe_float(row["risk_score"])), 2),
                "source": row["source"],
                "flags": json.dumps([row["reason"]], ensure_ascii=True),
                "updated_at": row["joined_at"],
            })
        return sorted(rows, key=lambda row: (-_safe_float(row["threat_score"]), row["canonical_username"] or ""))

    async def powerbi_metadata(self) -> Dict[str, Any]:
        bundle = await self.build_export_bundle()
        return {
            "generated_at": self.snapshot_at.isoformat(),
            "window_hours": self.hours,
            "dataset_name": settings.powerbi_dataset_name,
            "tables": [
                {
                    "name": name,
                    "rows": len(rows),
                    "columns": POWERBI_TABLE_DEFINITIONS[name],
                }
                for name, rows in bundle.items()
            ],
            "relationships": POWERBI_RELATIONSHIPS,
            "measures": POWERBI_DAX_MEASURES,
            "powerbi_service": {
                "enabled": settings.powerbi_enabled,
                "configured": bool(settings.powerbi_enabled and settings.powerbi_tenant_id and settings.powerbi_client_id and settings.powerbi_client_secret and settings.powerbi_group_id),
                "group_id": settings.powerbi_group_id,
                "dataset_name": settings.powerbi_dataset_name,
            },
        }

    async def _load_streams(self) -> List[StreamContext]:
        if self._streams is not None:
            return self._streams
        result = await self.db.execute(
            select(Stream, User)
            .join(User, Stream.owner_id == User.id)
            .where(Stream.tenant_id == self.tenant_id)
        )
        self._streams = [StreamContext(stream=stream, owner=user) for stream, user in result.all()]
        return self._streams

    async def _load_events(self) -> List[StreamEvent]:
        if self._events is not None:
            return self._events
        stream_ids = [ctx.stream.id for ctx in await self._load_streams()]
        if not stream_ids:
            self._events = []
            return self._events
        result = await self.db.execute(
            select(StreamEvent)
            .where(
                StreamEvent.stream_id.in_(stream_ids),
                StreamEvent.created_at >= self.since,
            )
            .order_by(StreamEvent.created_at.desc())
        )
        self._events = list(result.scalars().all())
        return self._events

    async def _load_attacks(self) -> List[Attack]:
        if self._attacks is not None:
            return self._attacks
        stream_ids = [ctx.stream.id for ctx in await self._load_streams()]
        if not stream_ids:
            self._attacks = []
            return self._attacks
        result = await self.db.execute(
            select(Attack)
            .where(
                Attack.stream_id.in_(stream_ids),
                Attack.created_at >= self.since,
            )
            .order_by(Attack.created_at.desc())
        )
        self._attacks = list(result.scalars().all())
        return self._attacks

    async def _load_viewers(self) -> List[ViewerSession]:
        if self._viewers is not None:
            return self._viewers
        stream_ids = [ctx.stream.id for ctx in await self._load_streams()]
        if not stream_ids:
            self._viewers = []
            return self._viewers
        result = await self.db.execute(
            select(ViewerSession)
            .where(
                ViewerSession.stream_id.in_(stream_ids),
                ViewerSession.joined_at >= self.since,
            )
            .order_by(ViewerSession.joined_at.desc())
        )
        self._viewers = list(result.scalars().all())
        return self._viewers

    async def _load_engagement_docs(self) -> Dict[str, Dict[str, Any]]:
        if self._engagement_docs is not None:
            return self._engagement_docs
        self._engagement_docs = {}
        db = await get_mongo_db()
        if db is None:
            return self._engagement_docs
        try:
            cursor = db[COL_ENGAGEMENT].find({"tenant_id": str(self.tenant_id)})
            async for doc in cursor:
                self._engagement_docs[str(doc.get("stream_id"))] = _serialize_payload(dict(doc))
        except Exception as exc:
            logger.warning("analytics_engagement_docs_failed", tenant_id=str(self.tenant_id), error=str(exc)[:180])
        return self._engagement_docs

    async def _load_entity_docs(self) -> List[Dict[str, Any]]:
        if self._entity_docs is not None:
            return self._entity_docs
        db = await get_mongo_db()
        if db is None:
            self._entity_docs = []
            return self._entity_docs
        try:
            cursor = db[COL_ENTITIES].find({"tenant_id": str(self.tenant_id)}).sort("threat_score", -1).limit(500)
            self._entity_docs = [_serialize_payload(dict(doc)) async for doc in cursor]
        except Exception as exc:
            logger.warning("analytics_entity_docs_failed", tenant_id=str(self.tenant_id), error=str(exc)[:180])
            self._entity_docs = []
        return self._entity_docs


def csv_bytes(rows: Sequence[Dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else []
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    if fieldnames:
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _serialize_cell(v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8")


def json_bytes(payload: Any) -> bytes:
    return json.dumps(_serialize_payload(payload), ensure_ascii=True, indent=2).encode("utf-8")


def excel_bytes(bundle: Dict[str, Sequence[Dict[str, Any]]]) -> bytes:
    workbook = Workbook()
    first = True
    for sheet_name, rows in bundle.items():
        sheet = workbook.active if first else workbook.create_sheet(title=sheet_name[:31])
        if first:
            sheet.title = sheet_name[:31]
            first = False
        headers = list(rows[0].keys()) if rows else []
        if headers:
            sheet.append(headers)
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for row in rows:
                sheet.append([_serialize_cell(row.get(header)) for header in headers])
        else:
            sheet.append(["empty"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def powerbi_package_bytes(
    bundle: Dict[str, Sequence[Dict[str, Any]]],
    *,
    metadata: Dict[str, Any],
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, rows in bundle.items():
            zf.writestr(f"{name}.csv", csv_bytes(rows))
        zf.writestr("powerbi_model.json", json_bytes(metadata))
        dax_text = "\n\n".join(POWERBI_DAX_MEASURES.values())
        zf.writestr("powerbi_measures.dax", dax_text.encode("utf-8"))
        zf.writestr(
            "README.txt",
            (
                "Power BI package generated by StreamShield.\n"
                "Import CSV tables, create relationships from powerbi_model.json,\n"
                "and paste measures from powerbi_measures.dax.\n"
            ).encode("utf-8"),
        )
    return output.getvalue()


class PowerBIService:
    TOKEN_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
    API_BASE = "https://api.powerbi.com/v1.0/myorg"

    @property
    def configured(self) -> bool:
        return bool(
            settings.powerbi_enabled
            and settings.powerbi_tenant_id
            and settings.powerbi_client_id
            and settings.powerbi_client_secret
            and settings.powerbi_group_id
        )

    async def sync_bundle(self, bundle: Dict[str, Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
        if not self.configured:
            return {
                "enabled": settings.powerbi_enabled,
                "configured": False,
                "message": "Power BI credentials not configured",
            }
        token = await self._get_access_token()
        dataset_id = await self._ensure_dataset(token)
        pushed_tables = []
        async with httpx.AsyncClient(timeout=45.0) as client:
            for table_name, rows in bundle.items():
                limited_rows = list(rows)[: settings.powerbi_max_rows_per_table]
                if not limited_rows:
                    continue
                response = await client.post(
                    f"{self.API_BASE}/groups/{settings.powerbi_group_id}/datasets/{dataset_id}/tables/{table_name}/rows",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={"rows": [_serialize_payload(dict(row)) for row in limited_rows]},
                )
                response.raise_for_status()
                pushed_tables.append({"table": table_name, "rows": len(limited_rows)})
        return {
            "enabled": True,
            "configured": True,
            "dataset_id": dataset_id,
            "dataset_name": settings.powerbi_dataset_name,
            "tables_pushed": pushed_tables,
        }

    async def _get_access_token(self) -> str:
        token_url = f"https://login.microsoftonline.com/{settings.powerbi_tenant_id}/oauth2/v2.0/token"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.powerbi_client_id,
                    "client_secret": settings.powerbi_client_secret,
                    "scope": self.TOKEN_SCOPE,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("Power BI access token missing in OAuth response")
            return token

    async def _ensure_dataset(self, token: str) -> str:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        dataset_name = settings.powerbi_dataset_name
        async with httpx.AsyncClient(timeout=30.0) as client:
            list_resp = await client.get(
                f"{self.API_BASE}/groups/{settings.powerbi_group_id}/datasets",
                headers=headers,
            )
            list_resp.raise_for_status()
            for item in list_resp.json().get("value", []):
                if item.get("name") == dataset_name:
                    return str(item["id"])

            create_resp = await client.post(
                f"{self.API_BASE}/groups/{settings.powerbi_group_id}/datasets",
                headers=headers,
                json={
                    "name": dataset_name,
                    "defaultMode": "Push",
                    "tables": [
                        {
                            "name": table_name,
                            "columns": columns,
                        }
                        for table_name, columns in POWERBI_TABLE_DEFINITIONS.items()
                    ],
                },
            )
            create_resp.raise_for_status()
            payload = create_resp.json()
            dataset_id = payload.get("id")
            if not dataset_id:
                raise RuntimeError("Power BI dataset id missing after create")
            return str(dataset_id)
