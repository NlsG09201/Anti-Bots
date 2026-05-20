"""
Behavioral anomaly detection: rolling baselines, z-scores, optional IsolationForest.
Designed for high-volume viewer join streams (anti-viewbotting).
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.cache.redis_schema import TTL_BASELINE, stream_baseline_key

logger = get_logger(__name__)

# In-process fallback when Redis unavailable
_local_baselines: Dict[str, Deque[float]] = {}


@dataclass
class AnomalyAssessment:
    anomaly_score: float
    is_anomaly: bool
    confidence: float
    flags: List[str] = field(default_factory=list)
    features: Dict[str, float] = field(default_factory=dict)
    baseline: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_score": self.anomaly_score,
            "is_anomaly": self.is_anomaly,
            "confidence": self.confidence,
            "flags": self.flags,
            "features": self.features,
            "baseline": self.baseline,
        }


class AnomalyIntelligenceService:
    """
    Tracks per-stream behavioral baselines and scores incoming windows.
    """

    WINDOW_HISTORY = 30
    Z_ANOMALY_THRESHOLD = 2.8
    SCORE_ANOMALY_THRESHOLD = 55.0

    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss")
        self._isolation_forest = None
        try:
            from sklearn.ensemble import IsolationForest

            self._isolation_forest = IsolationForest(
                contamination=0.08,
                random_state=42,
                n_estimators=64,
            )
        except ImportError:
            pass

    async def _load_history(self, stream_id: str, metric: str) -> List[float]:
        key = f"{stream_baseline_key(stream_id)}:{metric}"
        data = await self._cache.get(key)
        if isinstance(data, list):
            return [float(x) for x in data[-self.WINDOW_HISTORY :]]
        local = _local_baselines.get(key)
        return list(local) if local else []

    async def _save_history(self, stream_id: str, metric: str, values: List[float]) -> None:
        trimmed = values[-self.WINDOW_HISTORY :]
        key = f"{stream_baseline_key(stream_id)}:{metric}"
        await self._cache.set(key, trimmed, ttl=TTL_BASELINE)
        _local_baselines[key] = deque(trimmed, maxlen=self.WINDOW_HISTORY)

    def _zscore(self, value: float, history: List[float]) -> Optional[float]:
        if len(history) < 5:
            return None
        mean = statistics.mean(history)
        stdev = statistics.stdev(history)
        if stdev < 1e-6:
            return 0.0
        return (value - mean) / stdev

    async def assess_window(
        self,
        stream_id: str,
        *,
        joins_per_minute: float,
        unique_ip_ratio: float,
        proxy_ratio: float,
        fingerprint_collision_ratio: float,
        chat_participation_ratio: float,
    ) -> AnomalyAssessment:
        features = {
            "joins_per_minute": joins_per_minute,
            "unique_ip_ratio": unique_ip_ratio,
            "proxy_ratio": proxy_ratio,
            "fingerprint_collision_ratio": fingerprint_collision_ratio,
            "chat_participation_ratio": chat_participation_ratio,
        }

        flags: List[str] = []
        z_scores: List[float] = []
        baseline: Dict[str, float] = {}

        for metric, value in features.items():
            history = await self._load_history(stream_id, metric)
            z = self._zscore(value, history)
            if history:
                baseline[f"{metric}_mean"] = round(statistics.mean(history), 4)
                baseline[f"{metric}_stdev"] = round(
                    statistics.stdev(history) if len(history) > 1 else 0.0, 4
                )
            history.append(value)
            await self._save_history(stream_id, metric, history)
            if z is not None and abs(z) >= self.Z_ANOMALY_THRESHOLD:
                flags.append(f"z_anomaly:{metric}:{z:.2f}")
                z_scores.append(abs(z))

        # Rule-based viewbot patterns
        score = 0.0
        if joins_per_minute > 200 and unique_ip_ratio < 0.3:
            score += 35.0
            flags.append("low_ip_diversity_high_joins")
        if proxy_ratio > 0.4:
            score += 25.0
            flags.append("high_proxy_ratio")
        if fingerprint_collision_ratio > 0.25:
            score += 30.0
            flags.append("fingerprint_clustering")
        if chat_participation_ratio < 0.05 and joins_per_minute > 50:
            score += 20.0
            flags.append("silent_viewers_spike")

        if z_scores:
            score += min(40.0, max(z_scores) * 8.0)

        if self._isolation_forest and len(z_scores) >= 3:
            try:
                vec = [
                    [joins_per_minute, unique_ip_ratio, proxy_ratio,
                     fingerprint_collision_ratio, chat_participation_ratio]
                ]
                pred = self._isolation_forest.fit_predict(vec)
                if pred[0] == -1:
                    score += 15.0
                    flags.append("ml_isolation_anomaly")
            except Exception:
                pass

        score = min(100.0, score)
        is_anomaly = score >= self.SCORE_ANOMALY_THRESHOLD or len(flags) >= 2
        confidence = min(0.95, 0.4 + (score / 100.0) * 0.5)

        return AnomalyAssessment(
            anomaly_score=round(score, 2),
            is_anomaly=is_anomaly,
            confidence=round(confidence, 3),
            flags=flags,
            features=features,
            baseline=baseline,
        )
