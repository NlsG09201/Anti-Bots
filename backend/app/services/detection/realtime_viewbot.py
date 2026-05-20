"""
Motor inteligente de detección de viewbots en tiempo real.

Combina heurísticas, detección estadística y ML básico (IsolationForest opcional)
sobre ventana deslizante de eventos por stream.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import StreamEvent, ViewerSession
from app.services.detection.engine import BotDetectionEngine, DetectionResult, EventBatch
from app.services.detection.event_window import EventWindowStore, _parse_ts

logger = get_logger(__name__)
settings = get_settings()

CLASSIFICATION_LABELS = ("clean", "suspicious", "likely_viewbot", "coordinated_bot")


@dataclass
class ViewbotAssessment:
    risk_score: float
    classification: str
    confidence: float
    signals: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "monitor"
    auto_block: bool = False
    alert_recommended: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": round(self.risk_score, 2),
            "classification": self.classification,
            "confidence": round(self.confidence, 3),
            "signals": self.signals,
            "recommended_action": self.recommended_action,
            "auto_block": self.auto_block,
            "alert_recommended": self.alert_recommended,
        }


class RealtimeViewbotEngine:
    WEIGHTS = {
        "join_velocity": 22.0,
        "synchronized_joins": 24.0,
        "fingerprint_collision": 18.0,
        "ip_concentration": 14.0,
        "connection_proxy_dc": 16.0,
        "session_anomaly": 12.0,
        "chat_anomaly": 14.0,
        "event_repetition": 12.0,
        "statistical_anomaly": 15.0,
        "ml_anomaly": 18.0,
        "pattern_engine": 20.0,
    }

    def __init__(self) -> None:
        self._engine = BotDetectionEngine()
        self._window = EventWindowStore()

    async def record_event(
        self,
        stream_id: UUID,
        *,
        event_type: str,
        platform_user_id: Optional[str] = None,
        platform_username: Optional[str] = None,
        ip_address: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
        is_proxy: bool = False,
        is_vpn: bool = False,
        is_tor: bool = False,
        is_datacenter: bool = False,
        chat_messages: int = 0,
        watch_duration_seconds: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        if not settings.viewbot_realtime_enabled:
            return
        await self._window.push(
            stream_id,
            {
                "ts": (timestamp or datetime.now(timezone.utc)).isoformat(),
                "event_type": event_type,
                "platform_user_id": platform_user_id,
                "platform_username": platform_username,
                "ip_address": ip_address,
                "fingerprint_hash": fingerprint_hash,
                "is_proxy": is_proxy,
                "is_vpn": is_vpn,
                "is_tor": is_tor,
                "is_datacenter": is_datacenter,
                "chat_messages": chat_messages,
                "watch_duration_seconds": watch_duration_seconds,
                "metadata": metadata or {},
            },
        )

    async def assess_from_window(self, stream_id: UUID) -> ViewbotAssessment:
        events = await self._window.get_events(stream_id)
        return self._fuse_assessment(self._compute_all_signals(events), events)

    async def assess_ingest_event(
        self,
        stream_id: UUID,
        event_type: str,
        ip_data: Dict[str, Any],
        *,
        platform_user_id: Optional[str] = None,
        platform_username: Optional[str] = None,
        ip_address: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
        fingerprint_risk: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ViewbotAssessment:
        if not settings.viewbot_realtime_enabled:
            return ViewbotAssessment(0.0, "clean", 0.0)

        now = datetime.now(timezone.utc)
        await self.record_event(
            stream_id,
            event_type=event_type,
            platform_user_id=platform_user_id,
            platform_username=platform_username,
            ip_address=ip_address,
            fingerprint_hash=fingerprint_hash,
            is_proxy=bool(ip_data.get("is_proxy")),
            is_vpn=bool(ip_data.get("is_vpn")),
            is_tor=bool(ip_data.get("is_tor")),
            is_datacenter=bool(ip_data.get("is_datacenter") or ip_data.get("is_hosting")),
            metadata=metadata,
            timestamp=now,
        )

        events = await self._window.get_events(stream_id)
        signals = self._compute_all_signals(events)

        if ip_data:
            ip_result = self._engine.analyze_ip(ip_data)
            if ip_result.risk_score > 0:
                signals["ip_reputation_score"] = ip_result.risk_score
                signals["ip_checks"] = ip_result.evidence.get("checks", [])

        if fingerprint_risk > 0:
            signals["fingerprint_risk_ingest"] = fingerprint_risk

        if len(events) >= 3:
            batch = EventBatch(
                stream_id=str(stream_id),
                events=[
                    {
                        "timestamp": e.get("ts"),
                        "ip_address": e.get("ip_address"),
                        "fingerprint_hash": e.get("fingerprint_hash"),
                    }
                    for e in events
                ],
                window_seconds=settings.viewbot_window_seconds,
            )
            pattern = self._engine.analyze_viewbot_pattern(batch)
            if pattern.risk_score > 0:
                signals["pattern_engine_score"] = pattern.risk_score
                signals["pattern_evidence"] = pattern.evidence

        per_viewer = self._assess_single_viewer(events, platform_user_id, platform_username)
        if per_viewer.risk_score > 0:
            signals["viewer_profile_score"] = per_viewer.risk_score
            signals["viewer_profile"] = per_viewer.signals

        assessment = self._fuse_assessment(signals, events)
        return assessment

    async def assess_stream_sessions(
        self,
        db: AsyncSession,
        stream_id: UUID,
        chatters: Optional[List[Dict[str, Any]]] = None,
    ) -> ViewbotAssessment:
        """Análisis por lote tras sincronizar chat (monitor / load-full)."""
        if not settings.viewbot_realtime_enabled:
            return ViewbotAssessment(0.0, "clean", 0.0)

        since_minutes = max(2, settings.viewbot_window_seconds // 60)
        from datetime import timedelta

        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        result = await db.execute(
            select(StreamEvent).where(
                StreamEvent.stream_id == stream_id,
                StreamEvent.created_at >= since,
            ).order_by(StreamEvent.created_at.desc()).limit(400)
        )
        db_events = result.scalars().all()
        for ev in db_events:
            await self.record_event(
                stream_id,
                event_type=ev.event_type,
                platform_user_id=ev.platform_user_id,
                platform_username=ev.platform_username,
                ip_address=ev.ip_address,
                fingerprint_hash=ev.fingerprint_hash,
                is_proxy=ev.is_proxy,
                is_vpn=ev.is_vpn,
                is_tor=ev.is_tor,
                is_datacenter=ev.is_datacenter,
                metadata=dict(ev.event_metadata or {}),
                timestamp=ev.created_at,
            )

        if chatters:
            for c in chatters:
                await self.record_event(
                    stream_id,
                    event_type="chatter_presence",
                    platform_username=c.get("username"),
                    platform_user_id=c.get("user_id"),
                    chat_messages=int(c.get("messages", 0)),
                    metadata={"source": c.get("source", "chat"), "joins": c.get("joins", 1)},
                )

        sessions_result = await db.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream_id,
                ViewerSession.is_active == True,
            )
        )
        sessions = sessions_result.scalars().all()
        session_signals: List[Dict[str, Any]] = []
        lurker_count = 0
        for s in sessions:
            profile = {
                "username": s.platform_username,
                "messages": s.chat_messages,
                "watch_duration": s.watch_duration_seconds,
                "risk": s.risk_score,
                "is_suspected": s.is_suspected_bot,
            }
            if s.chat_messages == 0 and s.watch_duration_seconds < 180:
                lurker_count += 1
            session_signals.append(profile)

        events = await self._window.get_events(stream_id)
        signals = self._compute_all_signals(events)
        signals["active_sessions"] = len(sessions)
        signals["lurker_sessions"] = lurker_count
        if sessions:
            signals["lurker_ratio"] = round(lurker_count / len(sessions), 3)
            if lurker_count / len(sessions) > 0.6 and len(sessions) >= 10:
                signals["lurker_invasion"] = True

        suspected = sum(1 for s in sessions if s.is_suspected_bot)
        signals["suspected_sessions"] = suspected

        return self._fuse_assessment(signals, events)

    def _compute_all_signals(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        signals: Dict[str, Any] = {"event_count": len(events)}
        if not events:
            return signals

        joins = [e for e in events if e.get("event_type") in ("viewer_join", "viewer_pulse", "chatter_presence")]
        signals["join_count"] = len(joins)

        timestamps = [_parse_ts(e.get("ts")) for e in joins]
        if len(timestamps) >= 2:
            window_sec = max((max(timestamps) - min(timestamps)).total_seconds(), 1.0)
            velocity = len(joins) / window_sec * 60.0
            signals["join_velocity_per_min"] = round(velocity, 2)
            if velocity > 25:
                signals["high_join_velocity"] = True
            elif velocity > 12:
                signals["elevated_join_velocity"] = True

            intervals = []
            for i in range(1, len(sorted(timestamps))):
                intervals.append((sorted(timestamps)[i] - sorted(timestamps)[i - 1]).total_seconds())
            if len(intervals) >= 3:
                mean_i = statistics.mean(intervals)
                std_i = statistics.stdev(intervals) if len(intervals) > 1 else 0.0
                cv = (std_i / mean_i) if mean_i > 0 else 0.0
                signals["join_timing_cv"] = round(cv, 4)
                if cv < 0.12 and len(intervals) >= 8:
                    signals["synchronized_joins"] = True

        ips = [e.get("ip_address") for e in events if e.get("ip_address")]
        if len(ips) >= 8:
            unique_ratio = len(set(ips)) / len(ips)
            signals["ip_diversity_ratio"] = round(unique_ratio, 3)
            if unique_ratio < 0.3:
                signals["ip_concentration"] = True

        fps = [e.get("fingerprint_hash") for e in events if e.get("fingerprint_hash")]
        if fps:
            fp_counts = Counter(fps)
            top_fp, top_n = fp_counts.most_common(1)[0]
            signals["top_fingerprint_reuse"] = top_n
            if top_n >= 5:
                signals["fingerprint_collision"] = True
                signals["collision_fingerprint"] = top_fp[:12]

        proxy_n = sum(1 for e in events if e.get("is_proxy") or e.get("is_vpn") or e.get("is_tor"))
        dc_n = sum(1 for e in events if e.get("is_datacenter"))
        if len(events) >= 5:
            signals["proxy_ratio"] = round(proxy_n / len(events), 3)
            signals["datacenter_ratio"] = round(dc_n / len(events), 3)
            if proxy_n / len(events) > 0.35:
                signals["proxy_connection_pattern"] = True
            if dc_n / len(events) > 0.4:
                signals["datacenter_connection_pattern"] = True

        user_joins: Counter[str] = Counter()
        for e in joins:
            uid = e.get("platform_user_id") or e.get("platform_username")
            if uid:
                user_joins[str(uid)] += 1
        repeat_users = [u for u, n in user_joins.items() if n >= 3]
        if repeat_users:
            signals["event_repetition_users"] = repeat_users[:10]
            signals["event_repetition"] = True

        chat_events = [e for e in events if e.get("event_type") == "chat_message" or e.get("chat_messages", 0) > 0]
        signals["chat_active_count"] = len(chat_events)
        silent_joins = len([e for e in joins if e.get("chat_messages", 0) == 0])
        if joins and silent_joins / len(joins) > 0.85 and len(joins) >= 10:
            signals["silent_chat_ratio"] = round(silent_joins / len(joins), 3)
            signals["chat_behavior_anomaly"] = True

        durations = [e.get("watch_duration_seconds", 0) for e in events if e.get("watch_duration_seconds")]
        if len(durations) >= 8:
            mean_d = statistics.mean(durations)
            std_d = statistics.stdev(durations) if len(durations) > 1 else 0.0
            signals["mean_session_duration"] = round(mean_d, 1)
            short = sum(1 for d in durations if d < 90)
            if short / len(durations) > 0.7:
                signals["short_session_pattern"] = True

        stat_score = self._statistical_anomaly_score(events, signals)
        if stat_score > 0:
            signals["statistical_anomaly_score"] = stat_score

        ml_score, ml_ratio = self._ml_anomaly_score(events)
        if ml_score > 0:
            signals["ml_anomaly_score"] = ml_score
            signals["ml_anomaly_ratio"] = ml_ratio

        return signals

    def _statistical_anomaly_score(
        self,
        events: List[Dict[str, Any]],
        signals: Dict[str, Any],
    ) -> float:
        score = 0.0
        velocity = signals.get("join_velocity_per_min", 0.0)
        if velocity > 0:
            baseline = 8.0
            z = (velocity - baseline) / max(baseline * 0.5, 1.0)
            if z > 2.5:
                score += min(z * 6, 25.0)

        cv = signals.get("join_timing_cv")
        if cv is not None and cv < 0.08:
            score += 20.0

        lurker_ratio = signals.get("lurker_ratio", 0.0)
        if lurker_ratio > 0.65:
            score += 15.0

        return min(score, 40.0)

    def _ml_anomaly_score(self, events: List[Dict[str, Any]]) -> Tuple[float, float]:
        if not settings.viewbot_ml_enabled or len(events) < 12:
            return 0.0, 0.0

        vectors: List[List[float]] = []
        for e in events:
            vectors.append([
                float(e.get("chat_messages", 0)),
                float(e.get("watch_duration_seconds", 0)),
                1.0 if e.get("is_proxy") or e.get("is_vpn") else 0.0,
                1.0 if e.get("is_datacenter") else 0.0,
                1.0 if e.get("event_type") == "viewer_join" else 0.0,
            ])

        try:
            flags = self._engine.ml_anomaly_detect(vectors)
        except Exception as exc:
            logger.debug("ml_anomaly_skipped", error=str(exc))
            return 0.0, 0.0

        if not flags:
            return 0.0, 0.0
        ratio = sum(1 for f in flags if f) / len(flags)
        if ratio < 0.2:
            return 0.0, ratio
        return min(ratio * 100.0, 35.0), round(ratio, 3)

    def _assess_single_viewer(
        self,
        events: List[Dict[str, Any]],
        platform_user_id: Optional[str],
        platform_username: Optional[str],
    ) -> ViewbotAssessment:
        if not platform_user_id and not platform_username:
            return ViewbotAssessment(0.0, "clean", 0.0)

        key = str(platform_user_id or platform_username)
        mine = [
            e for e in events
            if str(e.get("platform_user_id") or "") == key
            or str(e.get("platform_username") or "").lower() == key.lower()
        ]
        if not mine:
            return ViewbotAssessment(0.0, "clean", 0.0)

        signals = {
            "viewer_events": len(mine),
            "viewer_proxy": any(e.get("is_proxy") for e in mine),
            "viewer_dc": any(e.get("is_datacenter") for e in mine),
            "viewer_messages": sum(int(e.get("chat_messages", 0)) for e in mine),
        }
        score = 0.0
        if signals["viewer_events"] >= 3:
            score += 15.0
        if signals["viewer_proxy"] or signals["viewer_dc"]:
            score += 20.0
        if signals["viewer_messages"] == 0 and len(mine) >= 2:
            score += 12.0

        return ViewbotAssessment(
            min(score, 100.0),
            self._classify_label(score, signals),
            min(score / 100.0, 0.95),
            signals=signals,
        )

    def _fuse_assessment(
        self,
        signals: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> ViewbotAssessment:
        score = 0.0

        if signals.get("high_join_velocity"):
            score += self.WEIGHTS["join_velocity"] * 1.2
        elif signals.get("elevated_join_velocity"):
            score += self.WEIGHTS["join_velocity"] * 0.65

        if signals.get("synchronized_joins"):
            score += self.WEIGHTS["synchronized_joins"]

        if signals.get("fingerprint_collision"):
            score += self.WEIGHTS["fingerprint_collision"]

        if signals.get("ip_concentration"):
            score += self.WEIGHTS["ip_concentration"]

        if signals.get("proxy_connection_pattern") or signals.get("datacenter_connection_pattern"):
            score += self.WEIGHTS["connection_proxy_dc"]

        if signals.get("short_session_pattern") or signals.get("lurker_invasion"):
            score += self.WEIGHTS["session_anomaly"]

        if signals.get("chat_behavior_anomaly"):
            score += self.WEIGHTS["chat_anomaly"]

        if signals.get("event_repetition"):
            score += self.WEIGHTS["event_repetition"]

        score += float(signals.get("statistical_anomaly_score", 0.0))
        score += float(signals.get("ml_anomaly_score", 0.0))
        score += float(signals.get("pattern_engine_score", 0.0)) * 0.85
        score += float(signals.get("ip_reputation_score", 0.0)) * 0.35
        score += float(signals.get("fingerprint_risk_ingest", 0.0)) * 0.4
        score += float(signals.get("viewer_profile_score", 0.0)) * 0.5

        score = min(score, 100.0)
        label = self._classify_label(score, signals)
        confidence = min(0.35 + (score / 100.0) * 0.55 + (0.1 if len(events) >= 10 else 0), 0.99)

        action = "monitor"
        if score >= 85:
            action = "ban"
        elif score >= 70:
            action = "quarantine"
        elif score >= 50:
            action = "alert"

        return ViewbotAssessment(
            risk_score=score,
            classification=label,
            confidence=confidence,
            signals=signals,
            recommended_action=action,
            auto_block=score >= settings.viewbot_auto_block_threshold,
            alert_recommended=score >= settings.viewbot_alert_threshold,
        )

    def _classify_label(self, score: float, signals: Dict[str, Any]) -> str:
        coordinated = (
            signals.get("synchronized_joins")
            and (signals.get("high_join_velocity") or signals.get("fingerprint_collision"))
        )
        if score >= 83 and coordinated:
            return "coordinated_bot"
        if score >= 65:
            return "likely_viewbot"
        if score >= 40:
            return "suspicious"
        return "clean"


_realtime_engine: Optional[RealtimeViewbotEngine] = None


def get_realtime_viewbot_engine() -> RealtimeViewbotEngine:
    global _realtime_engine
    if _realtime_engine is None:
        _realtime_engine = RealtimeViewbotEngine()
    return _realtime_engine
