"""AI Intelligence module tests."""

import pytest

from app.ai_intel.features.extractor import FeatureExtractor
from app.ai_intel.inference.engine import InferenceEngine
from app.ai_intel.models.base import ANOMALY_HEURISTIC
from app.ai_intel.schemas import ThreatClassification, ThreatLevel


def test_feature_extractor_viewbot_pattern():
    ext = FeatureExtractor()
    vec = ext.extract(
        event_type="viewer_join",
        metadata={
            "joins_per_minute": 250,
            "unique_ip_ratio": 0.2,
            "chat_participation_ratio": 0.02,
        },
        ip_intel={"is_proxy": True, "is_datacenter": True},
    )
    assert vec.joins_per_minute == 250
    assert vec.proxy_ratio >= 1.0
    assert len(vec.as_list()) == 16


def test_inference_engine_high_risk():
    ext = FeatureExtractor()
    vec = ext.extract(
        event_type="viewer_join",
        metadata={
            "joins_per_minute": 300,
            "viewer_growth_rate": 0.9,
            "silent_viewer_ratio": 0.8,
            "connection_sync_score": 0.75,
        },
        ip_intel={"is_proxy": True, "is_vpn": True, "is_datacenter": True},
    )
    engine = InferenceEngine()
    assessment = engine.infer(vec, coordination_score=0.6, reputation_penalty=0.2)
    assert assessment.risk_score >= 40
    assert assessment.attack_probability > 0.3
    assert assessment.classification in (
        ThreatClassification.VIEWBOT,
        ThreatClassification.COORDINATED,
        ThreatClassification.RAID,
        ThreatClassification.AUTOMATION,
    )


def test_heuristic_anomaly():
    feats = [200, 0.8, 5, 0.1, 0.7, 0.5, 0, 0.5, 0.3, 10, 0.2, 0.6, 30, 0, 0.2, 0.5]
    p = ANOMALY_HEURISTIC.predict_proba(feats)
    assert p > 0.2


@pytest.mark.asyncio
async def test_training_pipeline_bootstrap():
    from app.ai_intel.training.pipeline import TrainingPipeline

    result = await TrainingPipeline().run(min_samples=40)
    assert result["status"] == "ok"
    assert result["n_samples"] >= 40
