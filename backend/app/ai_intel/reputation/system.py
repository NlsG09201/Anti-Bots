"""Adaptive reputation for IPs, fingerprints, and users."""

from __future__ import annotations

from typing import Optional

from app.infrastructure.cache.redis_client import RedisCache


class ReputationSystem:
    """
    Rolling reputation 0-100 (100 = trusted, 0 = malicious).
    Used to tune risk scores and reduce false positives for known-good entities.
    """

    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss:ai:rep")

    def _key(self, entity_type: str, value: str) -> str:
        return f"{entity_type}:{value[:64]}"

    async def get_score(
        self,
        *,
        ip: Optional[str] = None,
        fingerprint: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> float:
        scores = []
        for etype, val in (
            ("ip", ip),
            ("fp", fingerprint),
            ("uid", user_id),
        ):
            if not val:
                continue
            raw = await self._cache.get(self._key(etype, val))
            if raw is not None:
                scores.append(float(raw))
        if not scores:
            return 50.0
        return sum(scores) / len(scores)

    async def update(
        self,
        *,
        ip: Optional[str] = None,
        fingerprint: Optional[str] = None,
        user_id: Optional[str] = None,
        delta: float = 0.0,
        ttl: int = 86400 * 7,
    ) -> None:
        for etype, val in (
            ("ip", ip),
            ("fp", fingerprint),
            ("uid", user_id),
        ):
            if not val:
                continue
            key = self._key(etype, val)
            current = await self._cache.get(key)
            base = float(current) if current is not None else 50.0
            new_score = max(0.0, min(100.0, base - delta))
            await self._cache.set(key, new_score, ttl=ttl)

    async def penalty_factor(self, **kwargs) -> float:
        """0-1 penalty added to attack probability."""
        score = await self.get_score(**kwargs)
        if score <= 20:
            return 0.25
        if score <= 40:
            return 0.12
        if score >= 80:
            return -0.05
        return 0.0
