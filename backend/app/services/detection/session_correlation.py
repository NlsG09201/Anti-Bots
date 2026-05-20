"""Correlación de sesiones por device_hash y session_key (Redis + DB)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import Fingerprint, StreamEvent


class FingerprintSessionCorrelator:
    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix="fp")

    def _device_key(self, tenant_id: str, device_hash: str) -> str:
        return f"tenant:{tenant_id}:device:{device_hash}"

    def _session_key(self, tenant_id: str, session_key: str) -> str:
        return f"tenant:{tenant_id}:session:{session_key}"

    async def register_session(
        self,
        *,
        tenant_id: str,
        device_hash: str,
        session_key: str,
        fingerprint_hash: str,
        risk_score: float,
        ttl: int = 86400 * 7,
    ) -> Dict[str, Any]:
        device_k = self._device_key(tenant_id, device_hash)
        existing_raw = await self._cache.get(device_k)
        sessions: List[str] = []
        if existing_raw:
            try:
                import json

                sessions = json.loads(existing_raw)
            except Exception:
                sessions = []
        if session_key not in sessions:
            sessions.append(session_key)
        sessions = sessions[-50:]
        import json

        await self._cache.set(device_k, json.dumps(sessions), ttl=ttl)

        meta = {
            "device_hash": device_hash,
            "fingerprint_hash": fingerprint_hash,
            "risk_score": risk_score,
        }
        await self._cache.set(
            self._session_key(tenant_id, session_key),
            json.dumps(meta),
            ttl=ttl,
        )

        correlated = [s for s in sessions if s != session_key]
        return {
            "device_hash": device_hash,
            "session_key": session_key,
            "linked_session_count": len(sessions),
            "correlated_sessions": correlated,
            "correlation_strength": min(1.0, len(correlated) / 10.0),
        }

    async def get_linked_sessions(
        self, tenant_id: str, device_hash: str
    ) -> List[str]:
        raw = await self._cache.get(self._device_key(tenant_id, device_hash))
        if not raw:
            return []
        try:
            import json

            return json.loads(raw)
        except Exception:
            return []

    async def correlate_from_db(
        self,
        db: AsyncSession,
        *,
        fingerprint_hash: str,
        stream_ids: Optional[List[UUID]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Correlación histórica vía eventos y tabla fingerprints."""
        fp_result = await db.execute(
            select(Fingerprint).where(Fingerprint.hash == fingerprint_hash)
        )
        fp_row = fp_result.scalar_one_or_none()

        event_count = 0
        unique_ips: set[str] = set()
        if stream_ids:
            ev_result = await db.execute(
                select(StreamEvent)
                .where(
                    StreamEvent.fingerprint_hash == fingerprint_hash,
                    StreamEvent.stream_id.in_(stream_ids),
                )
                .limit(limit)
            )
            events = ev_result.scalars().all()
            event_count = len(events)
            for ev in events:
                if ev.ip_address:
                    unique_ips.add(ev.ip_address)

        return {
            "fingerprint_hash": fingerprint_hash,
            "occurrence_count": fp_row.occurrence_count if fp_row else 0,
            "historical_risk": fp_row.risk_score if fp_row else 0.0,
            "event_count_in_streams": event_count,
            "unique_ips": list(unique_ips)[:20],
            "is_blocked": fp_row.is_blocked if fp_row else False,
        }
