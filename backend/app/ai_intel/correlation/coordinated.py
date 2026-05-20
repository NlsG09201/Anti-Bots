"""Coordinated attack pattern detection across events."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from app.infrastructure.cache.redis_client import RedisCache


class CoordinatedPatternDetector:
    """Detects synchronized joins, shared fingerprints, and ASN clusters."""

    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss:ai:coord")

    async def record_timing(
        self, stream_id: str, bucket_sec: int, entity_id: str
    ) -> None:
        key = f"{stream_id}:t:{bucket_sec // 5}"
        raw: List[str] = await self._cache.get(key) or []
        raw.append(entity_id)
        await self._cache.set(key, raw[-200:], ttl=120)

    async def score_coordination(self, stream_id: str) -> float:
        """0-1 coordination score from recent timing buckets."""
        keys_pattern = await self._recent_buckets(stream_id)
        if not keys_pattern:
            return 0.0

        max_sync = 0.0
        for entities in keys_pattern:
            if len(entities) < 5:
                continue
            counts: Dict[str, int] = defaultdict(int)
            for e in entities:
                counts[e[:12]] += 1
            peak = max(counts.values()) if counts else 0
            ratio = peak / len(entities)
            max_sync = max(max_sync, ratio)

        return min(1.0, max_sync)

    async def _recent_buckets(self, stream_id: str) -> List[List[str]]:
        import time

        now = int(time.time())
        out = []
        for i in range(12):
            bucket = (now - i * 5) // 5
            key = f"{stream_id}:t:{bucket}"
            data = await self._cache.get(key)
            if data and isinstance(data, list):
                out.append(data)
        return out

    def correlate_attack_clusters(
        self, correlations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Summarize cross-correlations from CorrelationService output."""
        if not correlations:
            return {"score": 0.0, "patterns": []}

        weight = 0.0
        patterns = []
        for c in correlations:
            ctype = c.get("type", "")
            count = c.get("event_count", 0)
            if ctype == "ip_cluster" and count >= 5:
                weight += 0.25
                patterns.append(f"ip_cluster:{c.get('key')}")
            elif ctype == "fingerprint_reuse" and count >= 5:
                weight += 0.35
                patterns.append(f"fp_reuse:{c.get('key')[:8]}")
            elif ctype == "asn_cluster" and count >= 10:
                weight += 0.2
                patterns.append(f"asn:{c.get('key')}")

        return {"score": min(1.0, weight), "patterns": patterns}
