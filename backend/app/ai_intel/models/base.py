"""Base model wrappers with heuristic fallbacks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple

import numpy as np


class BaseAIModel(ABC):
    name: str = "base"

    @abstractmethod
    def predict_proba(self, features: List[float]) -> float:
        ...

    def predict(self, features: List[float], threshold: float = 0.5) -> bool:
        return self.predict_proba(features) >= threshold


class HeuristicModel(BaseAIModel):
    """Rule-based fallback when sklearn model not trained."""

    def __init__(self, name: str, weights: List[Tuple[int, float, float]]) -> None:
        """
        weights: (feature_index, weight, threshold) — score += weight if feature > threshold
        """
        self.name = name
        self._weights = weights

    def predict_proba(self, features: List[float]) -> float:
        score = 0.0
        for idx, w, th in self._weights:
            if idx < len(features) and features[idx] > th:
                score += w
        return min(1.0, score / 100.0)


# Default heuristics aligned with feature vector indices
ANOMALY_HEURISTIC = HeuristicModel(
    "anomaly",
    [(0, 25, 80), (4, 20, 0.6), (7, 15, 0.3), (8, 20, 0.2), (11, 25, 0.5)],
)
BOT_HEURISTIC = HeuristicModel(
    "bot_classifier",
    [(5, 20, 0.5), (6, 15, 0.5), (7, 20, 0.5), (8, 25, 0.25), (10, 15, 0.3)],
)
RAID_HEURISTIC = HeuristicModel(
    "raid_predictor",
    [(0, 30, 150), (2, 25, 20), (11, 30, 0.7), (14, 20, 0.4)],
)
VIEWBOT_HEURISTIC = HeuristicModel(
    "viewbot_predictor",
    [(0, 25, 100), (1, 30, 0.5), (4, 25, 0.7), (13, 20, 0.35)],
)
AUTOMATION_HEURISTIC = HeuristicModel(
    "automation_detector",
    [(8, 30, 0.3), (10, 25, 0.4), (5, 15, 0.3), (7, 15, 0.3)],
)
