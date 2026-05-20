"""Offline / scheduled training pipeline for sklearn models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.ai_intel.learning.feedback import FeedbackStore
from app.ai_intel.models.registry import MODEL_FILES, ModelRegistry
from app.core.logging import get_logger

logger = get_logger(__name__)


class TrainingPipeline:
    """Trains or refreshes models from feedback + synthetic bootstrap data."""

    def __init__(self) -> None:
        self._feedback = FeedbackStore()
        self._registry = ModelRegistry.get()

    async def run(self, *, min_samples: int = 30) -> Dict[str, Any]:
        samples = await self._feedback.get_training_samples()
        X, y_bot, y_raid = self._build_dataset(samples)

        if len(X) < min_samples:
            X, y_bot, y_raid = self._bootstrap_synthetic(min_samples)
            source = "synthetic_bootstrap"
        else:
            source = "feedback"

        results: Dict[str, Any] = {"source": source, "n_samples": len(X), "models": {}}

        try:
            from sklearn.ensemble import (
                GradientBoostingClassifier,
                IsolationForest,
                RandomForestClassifier,
            )
        except ImportError:
            return {"status": "skipped", "reason": "sklearn_not_installed"}

        # Anomaly — unsupervised
        iso = IsolationForest(contamination=0.1, random_state=42, n_estimators=64)
        iso.fit(X)
        self._registry.save_model("anomaly", iso)

        # Supervised when labels exist
        if sum(y_bot) > 5:
            bot_clf = RandomForestClassifier(n_estimators=64, random_state=42)
            bot_clf.fit(X, y_bot)
            self._registry.save_model("bot_classifier", bot_clf)

            view_clf = GradientBoostingClassifier(random_state=42)
            view_clf.fit(X, y_bot)
            self._registry.save_model("viewbot_predictor", view_clf)

            auto_clf = RandomForestClassifier(n_estimators=48, random_state=43)
            auto_clf.fit(X, y_bot)
            self._registry.save_model("automation_detector", auto_clf)

        if sum(y_raid) > 3:
            raid_clf = GradientBoostingClassifier(random_state=44)
            raid_clf.fit(X, y_raid)
            self._registry.save_model("raid_predictor", raid_clf)

        self._registry.save_model("anomaly", iso, version="1.1.0")
        results["models"] = list(MODEL_FILES.keys())
        results["status"] = "ok"
        logger.info("ai_training_complete", **results)
        return results

    def _build_dataset(
        self, samples: List[Dict[str, Any]]
    ) -> tuple[List[List[float]], List[int], List[int]]:
        X, y_bot, y_raid = [], [], []
        for s in samples:
            feats = s.get("features") or {}
            if not feats:
                continue
            vec = [
                float(feats.get("joins_per_minute", 0)),
                float(feats.get("viewer_growth_rate", 0)),
                float(feats.get("follow_velocity", 0)),
                float(feats.get("chat_message_rate", 0)),
                float(feats.get("silent_viewer_ratio", 0)),
                float(feats.get("proxy_ratio", 0)),
                float(feats.get("vpn_ratio", 0)),
                float(feats.get("datacenter_ratio", 0)),
                float(feats.get("fingerprint_collision_ratio", 0)),
                float(feats.get("session_duration_avg_sec", 0)),
                float(feats.get("mouse_entropy", 0.5)),
                float(feats.get("connection_sync_score", 0)),
                float(feats.get("historical_risk_avg", 0)),
                float(feats.get("cross_stream_activity", 0)),
                float(feats.get("unique_ip_ratio", 1)),
                float(feats.get("asn_diversity", 1)),
            ]
            X.append(vec)
            label = int(s.get("label", 0))
            y_bot.append(label)
            y_raid.append(1 if feats.get("follow_velocity", 0) > 15 else label)
        return X, y_bot, y_raid

    def _bootstrap_synthetic(self, n: int) -> tuple:
        rng = np.random.default_rng(42)
        X = rng.uniform(0, 1, (n, 16)).tolist()
        y_bot = (rng.random(n) > 0.7).astype(int).tolist()
        y_raid = (rng.random(n) > 0.85).astype(int).tolist()
        return X, y_bot, y_raid
