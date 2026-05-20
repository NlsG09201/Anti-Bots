"""Adaptive threshold tuning from feedback and baselines."""

from __future__ import annotations

from typing import Dict

from app.ai_intel.learning.feedback import FeedbackStore
from app.infrastructure.cache.redis_client import RedisCache


class AdaptiveLearner:
    """Adjusts early-warning threshold based on feedback precision."""

    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss:ai:adapt")
        self._feedback = FeedbackStore()

    async def get_early_warning_threshold(self, default: float) -> float:
        raw = await self._cache.get("ew_threshold")
        return float(raw) if raw is not None else default

    async def tune_from_feedback(self) -> Dict[str, float]:
        samples = await self._feedback.get_training_samples(500)
        if len(samples) < 20:
            return {"adjusted": False, "reason": "insufficient_samples"}

        tp = sum(1 for s in samples if s.get("label") == 1)
        fp = len(samples) - tp
        precision = tp / len(samples) if samples else 0.5

        threshold = 0.65
        if precision < 0.6:
            threshold = min(0.85, threshold + 0.05)
        elif precision > 0.85:
            threshold = max(0.45, threshold - 0.03)

        await self._cache.set("ew_threshold", threshold, ttl=86400 * 7)
        return {
            "adjusted": True,
            "early_warning_threshold": threshold,
            "precision_estimate": round(precision, 3),
            "samples": len(samples),
            "false_positives": fp,
        }
