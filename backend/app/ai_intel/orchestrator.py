"""AI Intelligence orchestrator — single entry for real-time assessment."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_intel.correlation.coordinated import CoordinatedPatternDetector
from app.ai_intel.features.extractor import FeatureExtractor
from app.ai_intel.features.store import FeatureStore
from app.ai_intel.inference.engine import InferenceEngine
from app.ai_intel.learning.adaptive import AdaptiveLearner
from app.ai_intel.reputation.system import ReputationSystem
from app.ai_intel.metrics import AI_ASSESSMENTS_TOTAL, AI_EARLY_WARNINGS_TOTAL, AI_INFERENCE_LATENCY
from app.ai_intel.schemas import AIAssessment
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.correlation.service import CorrelationService

logger = get_logger(__name__)
settings = get_settings()

_orchestrator: Optional["AIIntelligenceOrchestrator"] = None


class AIIntelligenceOrchestrator:
    """
    Coordinates feature extraction, inference, reputation, correlation,
    caching, and optional WebSocket push.
    """

    def __init__(self) -> None:
        self.extractor = FeatureExtractor()
        self.features = FeatureStore()
        self.inference = InferenceEngine()
        self.reputation = ReputationSystem()
        self.coordination = CoordinatedPatternDetector()
        self.adaptive = AdaptiveLearner()

    async def assess_event(
        self,
        db: AsyncSession,
        *,
        stream_id: UUID,
        tenant_id: UUID,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_intel: Optional[Dict[str, Any]] = None,
        fingerprint_risk: float = 0.0,
        platform_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
    ) -> AIAssessment:
        if not settings.ai_intel_enabled:
            return AIAssessment()

        window = await self.features.get_window_stats(str(stream_id))
        vector = self.extractor.extract(
            event_type=event_type,
            metadata=metadata,
            ip_intel=ip_intel,
            window_stats=window,
            fingerprint_risk=fingerprint_risk,
        )

        agg = await self.features.append_event_features(
            str(stream_id),
            vector.to_dict(),
            tenant_id=str(tenant_id),
        )
        vector.historical_risk_avg = float(
            agg.get("historical_risk_avg", agg.get("joins_per_minute_max", 0)) * 2
        )

        entity = platform_user_id or ip_address or fingerprint_hash or "unknown"
        await self.coordination.record_timing(
            str(stream_id), int(time.time()), str(entity)
        )
        coord_score = await self.coordination.score_coordination(str(stream_id))

        correlator = CorrelationService(db)
        raw_corr = await correlator.correlate_events(stream_id, window_minutes=5)
        coord_meta = self.coordination.correlate_attack_clusters(raw_corr)
        coord_score = max(coord_score, coord_meta.get("score", 0.0))

        rep_penalty = await self.reputation.penalty_factor(
            ip=ip_address,
            fingerprint=fingerprint_hash,
            user_id=platform_user_id,
        )

        with AI_INFERENCE_LATENCY.time():
            assessment = self.inference.infer(
                vector,
                coordination_score=coord_score,
                reputation_penalty=rep_penalty,
            )

        AI_ASSESSMENTS_TOTAL.labels(
            threat_level=assessment.threat_level.value,
            classification=assessment.classification.value,
        ).inc()
        if assessment.early_warning:
            AI_EARLY_WARNINGS_TOTAL.inc()

        if coord_meta.get("patterns"):
            assessment.flags.extend(coord_meta["patterns"][:5])

        await self.features.set_prediction(str(stream_id), assessment.to_dict())

        if assessment.risk_score >= 50:
            delta = (assessment.risk_score - 50) / 5
            await self.reputation.update(
                ip=ip_address,
                fingerprint=fingerprint_hash,
                user_id=platform_user_id,
                delta=delta,
            )

        if assessment.early_warning or assessment.threat_level.value in (
            "high",
            "critical",
        ):
            try:
                from app.services.dashboard.metrics import get_tenant_stream_ids
                from app.services.realtime.notify import push_dashboard_realtime

                tenant_streams = await get_tenant_stream_ids(db, tenant_id)
                await push_dashboard_realtime(
                    db,
                    tenant_id,
                    tenant_streams,
                    alert={
                        "type": "ai_prediction",
                        "stream_id": str(stream_id),
                        "assessment": assessment.to_dict(),
                    },
                )
            except Exception as exc:
                logger.debug("ai_ws_push_skip", error=str(exc))

        return assessment

    async def get_stream_prediction(self, stream_id: UUID) -> Optional[Dict[str, Any]]:
        return await self.features.get_prediction(str(stream_id))


def get_ai_orchestrator() -> AIIntelligenceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIIntelligenceOrchestrator()
    return _orchestrator
