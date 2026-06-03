import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Attack,
    Incident,
    IncidentStatus,
    Stream,
    StreamEvent,
)

logger = get_logger(__name__)


class IncidentCorrelator:
    """Correlates related attacks/events into incidents based on IP/ASN/fingerprint/timing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def correlate_incident(
        self,
        stream_id: UUID,
        attack: Attack,
        event_window_hours: int = 24,
    ) -> Incident:
        """Create or update an incident for an attack with related events."""

        related_attacks = await self._find_related_attacks(
            stream_id,
            attack,
            hours=event_window_hours,
        )

        related_events = await self._find_related_events(
            stream_id,
            attack,
            hours=event_window_hours,
        )

        correlation_id = self._generate_correlation_id(
            stream_id,
            related_attacks,
            attack,
        )

        incident = await self._get_or_create_incident(
            stream_id,
            correlation_id,
            attack,
            related_attacks,
            related_events,
        )

        return incident

    async def _find_related_attacks(
        self,
        stream_id: UUID,
        attack: Attack,
        hours: int = 24,
    ) -> List[Attack]:
        """Find attacks with matching IPs, ASNs, or fingerprints within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(Attack).where(
                Attack.stream_id == stream_id,
                Attack.created_at >= cutoff,
                Attack.id != attack.id,
            )
        )
        candidates = list(result.scalars().all())

        related = []
        for candidate in candidates:
            if self._attacks_correlated(attack, candidate):
                related.append(candidate)

        return related

    async def _find_related_events(
        self,
        stream_id: UUID,
        attack: Attack,
        hours: int = 24,
    ) -> List[StreamEvent]:
        """Find events with matching IPs, ASNs, or fingerprints."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        event_ips = attack.source_ips or []
        event_fps = attack.fingerprints or []

        if not event_ips and not event_fps:
            return []

        result = await self.db.execute(
            select(StreamEvent).where(
                StreamEvent.stream_id == stream_id,
                StreamEvent.created_at >= cutoff,
            )
        )
        candidates = list(result.scalars().all())

        related = []
        for event in candidates:
            if (event.ip_address in event_ips) or (event.fingerprint_hash in event_fps):
                related.append(event)

        return related

    def _attacks_correlated(self, attack1: Attack, attack2: Attack) -> bool:
        """Check if two attacks share IP, ASN, or fingerprint."""
        ips1 = set(attack1.source_ips or [])
        ips2 = set(attack2.source_ips or [])

        fps1 = set(attack1.fingerprints or [])
        fps2 = set(attack2.fingerprints or [])

        return bool(ips1 & ips2) or bool(fps1 & fps2)

    def _generate_correlation_id(
        self,
        stream_id: UUID,
        related_attacks: List[Attack],
        primary_attack: Attack,
    ) -> str:
        """Generate deterministic correlation ID from related attack IDs."""
        all_ids = sorted([str(a.id) for a in related_attacks] + [str(primary_attack.id)])
        combined = f"{stream_id}:{'|'.join(all_ids)}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    async def _get_or_create_incident(
        self,
        stream_id: UUID,
        correlation_id: str,
        primary_attack: Attack,
        related_attacks: List[Attack],
        related_events: List[StreamEvent],
    ) -> Incident:
        """Get existing incident or create new one."""
        result = await self.db.execute(
            select(Incident).where(
                Incident.stream_id == stream_id,
                Incident.correlation_id == correlation_id,
            )
        )
        incident = result.scalar_one_or_none()

        all_attacks = related_attacks + [primary_attack]
        max_risk = max((a.risk_score for a in all_attacks), default=0.0)
        avg_confidence = sum((a.confidence for a in all_attacks)) / len(all_attacks) if all_attacks else 0.0

        all_ips = set()
        all_fps = set()
        for attack in all_attacks:
            all_ips.update(attack.source_ips or [])
            all_fps.update(attack.fingerprints or [])

        if incident:
            incident.severity = max_risk
            incident.confidence = min(avg_confidence + 0.1, 1.0)
            incident.attack_ids = [str(a.id) for a in all_attacks]
            incident.related_ips = list(all_ips)
            incident.related_fingerprints = list(all_fps)
            await self.db.flush()
        else:
            incident = Incident(
                stream_id=stream_id,
                correlation_id=correlation_id,
                status=IncidentStatus.ACTIVE,
                severity=max_risk,
                confidence=avg_confidence,
                attack_ids=[str(a.id) for a in all_attacks],
                related_ips=list(all_ips),
                related_fingerprints=list(all_fps),
            )
            self.db.add(incident)
            await self.db.flush()

        return incident
