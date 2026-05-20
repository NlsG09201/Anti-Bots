"""Human-in-the-loop feedback for model retraining."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.infrastructure.cache.redis_client import RedisCache


class FeedbackStore:
    MAX_SAMPLES = 5000

    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss:ai:fb")

    async def record(
        self,
        *,
        stream_id: str,
        assessment_id: Optional[str] = None,
        was_true_positive: bool,
        features: Dict[str, float],
        classification: str,
        notes: str = "",
    ) -> None:
        key = "global"
        samples: List[Dict[str, Any]] = await self._cache.get(key) or []
        samples.append(
            {
                "stream_id": stream_id,
                "assessment_id": assessment_id,
                "label": 1 if was_true_positive else 0,
                "features": features,
                "classification": classification,
                "notes": notes,
            }
        )
        await self._cache.set(key, samples[-self.MAX_SAMPLES :], ttl=86400 * 30)

    async def get_training_samples(self, limit: int = 2000) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = await self._cache.get("global") or []
        return samples[-limit:]

    async def count(self) -> int:
        samples = await self.get_training_samples()
        return len(samples)
