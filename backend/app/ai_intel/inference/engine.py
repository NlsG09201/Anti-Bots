"""Multi-model inference engine — anomaly, classification, prediction."""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.ai_intel.features.extractor import StreamFeatureVector
from app.ai_intel.models.base import (
    ANOMALY_HEURISTIC,
    AUTOMATION_HEURISTIC,
    BOT_HEURISTIC,
    RAID_HEURISTIC,
    VIEWBOT_HEURISTIC,
)
from app.ai_intel.models.registry import ModelRegistry
from app.ai_intel.schemas import AIAssessment, ThreatClassification, ThreatLevel
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class InferenceEngine:
    """Runs all AI models and fuses outputs into AIAssessment."""

    def __init__(self) -> None:
        self._registry = ModelRegistry.get()

    def _sklearn_proba(self, model_name: str, features: List[float]) -> Optional[float]:
        model = self._registry.get_model(model_name)
        if model is None:
            return None
        try:
            X = np.array([features])
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)[0]
                return float(proba[-1]) if len(proba) > 1 else float(proba[0])
            if hasattr(model, "decision_function"):
                raw = float(model.decision_function(X)[0])
                return float(1 / (1 + np.exp(-raw)))
            pred = model.predict(X)[0]
            return 1.0 if pred == -1 or pred == 1 else 0.0
        except Exception as exc:
            logger.debug("sklearn_infer_skip", model=model_name, error=str(exc))
            return None

    def _fuse(
        self, name: str, features: List[float], heuristic
    ) -> Tuple[float, str]:
        ml = self._sklearn_proba(name, features)
        heur = heuristic.predict_proba(features)
        if ml is not None:
            # Reduce false positives: require agreement for high scores
            blended = 0.65 * ml + 0.35 * heur
            source = "ml+heuristic"
        else:
            blended = heur
            source = "heuristic"
        return min(1.0, blended), source

    def infer(
        self,
        vector: StreamFeatureVector,
        *,
        coordination_score: float = 0.0,
        reputation_penalty: float = 0.0,
    ) -> AIAssessment:
        t0 = time.perf_counter()
        feats = vector.as_list()

        anomaly_p, anomaly_src = self._fuse("anomaly", feats, ANOMALY_HEURISTIC)
        bot_p, bot_src = self._fuse("bot_classifier", feats, BOT_HEURISTIC)
        raid_p, _ = self._fuse("raid_predictor", feats, RAID_HEURISTIC)
        viewbot_p, _ = self._fuse("viewbot_predictor", feats, VIEWBOT_HEURISTIC)
        auto_p, _ = self._fuse("automation_detector", feats, AUTOMATION_HEURISTIC)

        contributions = {
            "anomaly": round(anomaly_p, 4),
            "bot": round(bot_p, 4),
            "raid": round(raid_p, 4),
            "viewbot": round(viewbot_p, 4),
            "automation": round(auto_p, 4),
            "coordination": round(coordination_score, 4),
        }

        known_public = float(vector.extra.get("known_public_bot", 0))
        if known_public > 0:
            bot_p = max(bot_p, 0.92)
            viewbot_p = max(viewbot_p, 0.35)
            contributions["twitchbots_info"] = 1.0

        attack_probability = min(
            1.0,
            max(anomaly_p, bot_p, raid_p, viewbot_p, auto_p) * 0.85
            + coordination_score * 0.15
            + reputation_penalty * 0.1
            + known_public * 0.12,
        )

        risk_score = min(
            100.0,
            attack_probability * 70
            + vector.historical_risk_avg * 0.2
            + coordination_score * 30,
        )

        classification = self._classify(
            viewbot_p, raid_p, auto_p, bot_p, coordination_score
        )
        threat_level = self._threat_level(risk_score, attack_probability)
        early_warning = (
            attack_probability >= settings.ai_intel_early_warning_threshold
            and risk_score >= 40
            and threat_level in (ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL)
        )

        fp_likelihood = self._false_positive_score(vector, attack_probability)

        recommendations = self._recommendations(
            classification, threat_level, risk_score, early_warning
        )
        action, auto_mit = self._mitigation_action(
            threat_level, risk_score, fp_likelihood
        )

        flags = []
        if early_warning:
            flags.append("early_warning")
        if anomaly_p > 0.6:
            flags.append("anomaly_detected")
        if coordination_score > 0.5:
            flags.append("coordinated_behavior")
        if vector.proxy_ratio > 0.3:
            flags.append("high_proxy_ratio")
        if vector.silent_viewer_ratio > 0.6:
            flags.append("silent_viewers")

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return AIAssessment(
            risk_score=round(risk_score, 2),
            attack_probability=round(attack_probability, 4),
            threat_level=threat_level,
            classification=classification,
            early_warning=early_warning,
            confidence=round(1.0 - fp_likelihood, 3),
            false_positive_likelihood=round(fp_likelihood, 3),
            anomaly_score=round(anomaly_p * 100, 2),
            bot_probability=round(bot_p, 4),
            raid_probability=round(raid_p, 4),
            viewbot_probability=round(viewbot_p, 4),
            automation_probability=round(auto_p, 4),
            coordination_score=round(coordination_score, 4),
            flags=flags,
            model_contributions=contributions,
            features_snapshot=vector.to_dict(),
            recommended_action=action,
            recommendations=recommendations,
            auto_mitigate=auto_mit,
            model_version=self._registry.version,
            inference_ms=round(elapsed_ms, 2),
        )

    def _classify(
        self,
        viewbot_p: float,
        raid_p: float,
        auto_p: float,
        bot_p: float,
        coord: float,
    ) -> ThreatClassification:
        scores = {
            ThreatClassification.VIEWBOT: viewbot_p,
            ThreatClassification.RAID: raid_p,
            ThreatClassification.AUTOMATION: auto_p,
            ThreatClassification.COORDINATED: coord,
            ThreatClassification.FOLLOW_BOT: bot_p * 0.5,
        }
        best = max(scores, key=scores.get)
        if scores[best] < 0.35:
            return ThreatClassification.NONE
        return best

    def _threat_level(self, risk: float, attack_p: float) -> ThreatLevel:
        if risk >= 85 or attack_p >= 0.9:
            return ThreatLevel.CRITICAL
        if risk >= 65 or attack_p >= 0.75:
            return ThreatLevel.HIGH
        if risk >= 40 or attack_p >= 0.5:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def _false_positive_score(
        self, vector: StreamFeatureVector, attack_p: float
    ) -> float:
        """Higher = more likely false positive (reduce auto-ban)."""
        fp = 0.2
        if vector.chat_message_rate > 0.3 and vector.joins_per_minute < 50:
            fp -= 0.1
        if vector.unique_ip_ratio > 0.7:
            fp -= 0.05
        if vector.historical_risk_avg < 20 and attack_p > 0.5:
            fp += 0.15
        if vector.asn_diversity > 0.8:
            fp -= 0.05
        return max(0.05, min(0.85, fp))

    def _recommendations(
        self,
        classification: ThreatClassification,
        level: ThreatLevel,
        risk: float,
        early: bool,
    ) -> List[str]:
        recs = []
        if early:
            recs.append("Early warning: elevated attack probability — increase monitoring.")
        if classification == ThreatClassification.VIEWBOT:
            recs.append("Run full viewer sync and screen suspected sessions.")
        if classification == ThreatClassification.RAID:
            recs.append("Enable follower-only or slow mode; correlate IP clusters.")
        if classification == ThreatClassification.AUTOMATION:
            recs.append("Enforce widget fingerprint checks and captcha on join.")
        if level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            recs.append("Consider auto-mitigation for top-risk targets.")
        if risk < 40:
            recs.append("Continue baseline learning — no action required.")
        return recs

    def _mitigation_action(
        self, level: ThreatLevel, risk: float, fp: float
    ) -> Tuple[str, bool]:
        if fp > 0.55:
            return "monitor", False
        if level == ThreatLevel.CRITICAL and risk >= 85:
            auto = settings.ai_intel_auto_mitigate
            return ("ban" if auto else "quarantine"), auto
        if level == ThreatLevel.HIGH:
            return "quarantine", False
        if level == ThreatLevel.MEDIUM:
            return "challenge", False
        return "monitor", False
