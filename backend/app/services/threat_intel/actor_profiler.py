import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Attack,
    AttackType,
    Incident,
    ThreatActor,
)

logger = get_logger(__name__)


class ActorProfile:
    """Represents a threat actor profile."""

    def __init__(self, tenant_id: UUID, name: str):
        self.id = None
        self.tenant_id = tenant_id
        self.name = name
        self.tactics: Set[str] = set()
        self.confidence = 0.0
        self.last_seen = datetime.now(timezone.utc)
        self.incident_count = 0
        self.target_count = 0
        self.common_asns: Set[str] = set()
        self.common_fingerprints: Set[str] = set()

    def update_from_attack(self, attack: Attack):
        """Update profile with new attack data."""
        self.incident_count += 1
        self.last_seen = max(self.last_seen, attack.created_at)

        attack_type_str = attack.attack_type.value
        if attack_type_str not in self.tactics:
            self.tactics.add(attack_type_str)

        self.common_asns.update(set(attack.source_ips or []))
        self.common_fingerprints.update(set(attack.fingerprints or []))


class ThreatActorProfiler:
    """Profiles and clusters threat actors based on attack patterns."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.similarity_threshold = 0.7

    async def profile_actor(
        self,
        tenant_id: UUID,
        incident: Incident,
        incident_window_hours: int = 72,
    ) -> Optional[ThreatActor]:
        """Find or create threat actor profile from incident."""

        similar_incidents = await self._find_similar_incidents(
            tenant_id,
            incident,
            hours=incident_window_hours,
        )

        actor_name = self._generate_actor_name(tenant_id, incident, similar_incidents)
        profile = await self._get_or_create_profile(
            tenant_id,
            actor_name,
            incident,
            similar_incidents,
        )

        return profile

    async def _find_similar_incidents(
        self,
        tenant_id: UUID,
        incident: Incident,
        hours: int = 72,
    ) -> List[Incident]:
        """Find incidents with similar characteristics."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(Incident).where(
                Incident.stream_id.in_(
                    select(Incident.stream_id).where(
                        Incident.stream_id.in_(
                            select(Incident.stream_id).where(
                                Incident.threat_actor_id == None
                            )
                        )
                    )
                ),
                Incident.created_at >= cutoff,
                Incident.id != incident.id,
            )
        )
        candidates = list(result.scalars().all())

        similar = []
        for candidate in candidates:
            similarity = self._calculate_similarity(incident, candidate)
            if similarity >= self.similarity_threshold:
                similar.append(candidate)

        return similar

    def _calculate_similarity(self, incident1: Incident, incident2: Incident) -> float:
        """Calculate similarity between two incidents (0-1)."""

        ips1 = set(incident1.related_ips or [])
        ips2 = set(incident2.related_ips or [])
        ip_overlap = len(ips1 & ips2) / max(len(ips1 | ips2), 1)

        fps1 = set(incident1.related_fingerprints or [])
        fps2 = set(incident2.related_fingerprints or [])
        fp_overlap = len(fps1 & fps2) / max(len(fps1 | fps2), 1)

        timing_diff = abs(
            (incident1.created_at - incident2.created_at).total_seconds()
        )
        timing_sim = 1.0 if timing_diff < 3600 else max(0.0, 1.0 - (timing_diff / 86400))

        total_similarity = (ip_overlap + fp_overlap + timing_sim) / 3.0
        return total_similarity

    def _generate_actor_name(
        self,
        tenant_id: UUID,
        incident: Incident,
        similar_incidents: List[Incident],
    ) -> str:
        """Generate actor name from characteristics."""

        all_ips = set(incident.related_ips or [])
        for sim_incident in similar_incidents:
            all_ips.update(sim_incident.related_ips or [])

        if all_ips:
            ip_hash = hashlib.md5(
                "|".join(sorted(all_ips)).encode()
            ).hexdigest()[:6]
            return f"Actor-{ip_hash.upper()}"

        fps = set(incident.related_fingerprints or [])
        if fps:
            fp_hash = hashlib.md5(
                "|".join(sorted(fps)).encode()
            ).hexdigest()[:6]
            return f"Actor-FP{fp_hash.upper()}"

        return f"Actor-{incident.id.hex[:6].upper()}"

    async def _get_or_create_profile(
        self,
        tenant_id: UUID,
        actor_name: str,
        incident: Incident,
        similar_incidents: List[Incident],
    ) -> ThreatActor:
        """Get existing actor or create new one."""

        result = await self.db.execute(
            select(ThreatActor).where(
                ThreatActor.tenant_id == tenant_id,
                ThreatActor.name == actor_name,
            )
        )
        actor = result.scalar_one_or_none()

        all_incidents = similar_incidents + [incident]
        all_tactics = set()
        all_asns = set()
        all_fps = set()
        total_targets = 0

        for inc in all_incidents:
            all_asns.update(inc.related_ips or [])
            all_fps.update(inc.related_fingerprints or [])
            total_targets += len(inc.related_ips or []) + len(inc.related_fingerprints or [])

        avg_severity = sum((i.severity for i in all_incidents)) / len(all_incidents) if all_incidents else 0.0

        if actor:
            actor.incident_count = len(all_incidents)
            actor.target_count = total_targets
            actor.last_seen = datetime.now(timezone.utc)
            actor.common_asns = list(all_asns)[:10]
            actor.common_fingerprints = list(all_fps)[:10]
            actor.confidence = min(avg_severity / 100.0, 1.0)
            await self.db.flush()
        else:
            actor = ThreatActor(
                tenant_id=tenant_id,
                name=actor_name,
                tactics=list(all_tactics),
                confidence=min(avg_severity / 100.0, 1.0),
                incident_count=len(all_incidents),
                target_count=total_targets,
                common_asns=list(all_asns)[:10],
                common_fingerprints=list(all_fps)[:10],
            )
            self.db.add(actor)
            await self.db.flush()

        return actor

    async def get_threat_actors(
        self,
        tenant_id: UUID,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> List[ThreatActor]:
        """Get threat actor profiles for tenant."""

        result = await self.db.execute(
            select(ThreatActor)
            .where(
                and_(
                    ThreatActor.tenant_id == tenant_id,
                    ThreatActor.confidence >= min_confidence,
                )
            )
            .order_by(ThreatActor.last_seen.desc())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def link_incident_to_actor(
        self,
        incident: Incident,
        actor: ThreatActor,
    ):
        """Link an incident to a threat actor."""
        incident.threat_actor_id = actor.id
        actor.incident_count += 1
        actor.last_seen = max(actor.last_seen, incident.created_at)
        await self.db.flush()
