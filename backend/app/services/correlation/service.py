import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Alert,
    AlertSeverity,
    Attack,
    AttackType,
    StreamEvent,
)

logger = get_logger(__name__)


class CorrelationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def generate_correlation_id(self) -> str:
        return secrets.token_hex(16)

    async def correlate_events(
        self,
        stream_id: UUID,
        window_minutes: int = 5,
    ) -> List[Dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        result = await self.db.execute(
            select(StreamEvent).where(
                and_(
                    StreamEvent.stream_id == stream_id,
                    StreamEvent.created_at >= since,
                )
            ).order_by(StreamEvent.created_at)
        )
        events = result.scalars().all()

        ip_groups: Dict[str, List] = defaultdict(list)
        fp_groups: Dict[str, List] = defaultdict(list)
        asn_groups: Dict[int, List] = defaultdict(list)

        for event in events:
            if event.ip_address:
                ip_groups[event.ip_address].append(event)
            if event.fingerprint_hash:
                fp_groups[event.fingerprint_hash].append(event)
            if event.asn:
                asn_groups[event.asn].append(event)

        correlations = []

        for ip, group in ip_groups.items():
            if len(group) >= 3:
                correlations.append({
                    "type": "ip_cluster",
                    "key": ip,
                    "event_count": len(group),
                    "avg_risk": sum(e.risk_score for e in group) / len(group),
                    "event_ids": [str(e.id) for e in group],
                })

        for fp, group in fp_groups.items():
            if len(group) >= 5:
                correlations.append({
                    "type": "fingerprint_reuse",
                    "key": fp,
                    "event_count": len(group),
                    "avg_risk": sum(e.risk_score for e in group) / len(group),
                    "event_ids": [str(e.id) for e in group],
                })

        for asn, group in asn_groups.items():
            if len(group) >= 10:
                correlations.append({
                    "type": "asn_cluster",
                    "key": str(asn),
                    "event_count": len(group),
                    "avg_risk": sum(e.risk_score for e in group) / len(group),
                    "event_ids": [str(e.id) for e in group],
                })

        return correlations

    async def get_active_attack(
        self,
        stream_id: UUID,
        attack_type: Optional[AttackType] = None,
    ) -> Optional[Attack]:
        query = select(Attack).where(
            Attack.stream_id == stream_id,
            Attack.status == "active",
        )
        if attack_type is not None:
            query = query.where(Attack.attack_type == attack_type)
        query = query.order_by(Attack.created_at.desc()).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_attack_record(
        self,
        stream_id: UUID,
        attack_type: AttackType,
        risk_score: float,
        confidence: float,
        evidence: Dict[str, Any],
        source_ips: List[str],
        fingerprints: List[str],
        correlation_id: Optional[str] = None,
    ) -> Attack:
        attack = Attack(
            stream_id=stream_id,
            attack_type=attack_type,
            severity=self._score_to_severity(risk_score),
            risk_score=risk_score,
            confidence=confidence,
            source_ips=source_ips,
            fingerprints=fingerprints,
            correlation_id=correlation_id or self.generate_correlation_id(),
            evidence=evidence,
            affected_users=evidence.get("affected_users", 0),
        )
        self.db.add(attack)
        await self.db.flush()
        return attack

    async def create_alert(
        self,
        tenant_id: UUID,
        attack: Attack,
        title: str,
        message: str,
    ) -> Alert:
        alert = Alert(
            tenant_id=tenant_id,
            attack_id=attack.id,
            title=title,
            message=message,
            severity=attack.severity,
            alert_metadata={
                "attack_type": attack.attack_type.value,
                "risk_score": attack.risk_score,
                "correlation_id": attack.correlation_id,
            },
        )
        self.db.add(alert)
        await self.db.flush()
        return alert

    def _score_to_severity(self, score: float) -> AlertSeverity:
        if score >= 85:
            return AlertSeverity.CRITICAL
        if score >= 70:
            return AlertSeverity.HIGH
        if score >= 50:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW

    async def find_coordinated_attacks(
        self,
        stream_id: UUID,
        min_events: int = 20,
        window_seconds: int = 60,
    ) -> Optional[Dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        result = await self.db.execute(
            select(StreamEvent).where(
                and_(
                    StreamEvent.stream_id == stream_id,
                    StreamEvent.created_at >= since,
                )
            )
        )
        events = result.scalars().all()
        if len(events) < min_events:
            return None

        timestamps = [e.created_at for e in events]
        span = (max(timestamps) - min(timestamps)).total_seconds()
        if span > window_seconds:
            return None

        unique_ips = len({e.ip_address for e in events if e.ip_address})
        unique_fps = len({e.fingerprint_hash for e in events if e.fingerprint_hash})

        coordination_score = 0.0
        if unique_ips > 5 and unique_ips / len(events) < 0.5:
            coordination_score += 30
        if unique_fps > 0 and unique_fps < 3:
            coordination_score += 40
        if len(events) / max(span, 1) > 1.0:
            coordination_score += 30

        if coordination_score < 50:
            return None

        return {
            "event_count": len(events),
            "time_span_seconds": span,
            "unique_ips": unique_ips,
            "unique_fingerprints": unique_fps,
            "coordination_score": coordination_score,
            "source_ips": list({e.ip_address for e in events if e.ip_address})[:50],
            "fingerprints": list({e.fingerprint_hash for e in events if e.fingerprint_hash})[:50],
        }
