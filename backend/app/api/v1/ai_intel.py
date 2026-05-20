"""AI Intelligence API — predictions, feedback, training, metrics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_intel.learning.adaptive import AdaptiveLearner
from app.ai_intel.learning.feedback import FeedbackStore
from app.ai_intel.orchestrator import get_ai_orchestrator
from app.ai_intel.training.pipeline import TrainingPipeline
from app.api.dependencies import AnalystUser, CurrentUser, get_db
from app.infrastructure.database.models import Stream

router = APIRouter(prefix="/ai-intel", tags=["AI Intelligence"])


class FeedbackRequest(BaseModel):
    stream_id: UUID
    was_true_positive: bool
    classification: str = "viewbot"
    notes: str = ""
    features: Dict[str, float] = Field(default_factory=dict)


class AssessRequest(BaseModel):
    joins_per_minute: float = 0
    viewer_growth_rate: float = 0
    follow_velocity: float = 0
    chat_message_rate: float = 0
    silent_viewer_ratio: float = 0
    proxy_ratio: float = 0
    unique_ip_ratio: float = 1.0
    fingerprint_collision_ratio: float = 0


@router.get("/health")
async def ai_intel_health():
    from app.ai_intel.models.registry import ModelRegistry

    reg = ModelRegistry.get()
    loaded = [n for n in ("anomaly", "bot_classifier", "viewbot_predictor") if reg.get_model(n)]
    return {
        "status": "ok",
        "models_loaded": loaded,
        "model_version": reg.version,
        "mode": "sklearn+heuristic",
    }


@router.get("/streams/{stream_id}/prediction")
async def get_stream_prediction(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_stream(db, stream_id, current_user.tenant_id)
    pred = await get_ai_orchestrator().get_stream_prediction(stream_id)
    if not pred:
        return {"stream_id": str(stream_id), "prediction": None}
    return {"stream_id": str(stream_id), "prediction": pred}


@router.post("/streams/{stream_id}/assess")
async def assess_stream(
    stream_id: UUID,
    body: AssessRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _assert_stream(db, stream_id, current_user.tenant_id)
    assessment = await get_ai_orchestrator().assess_event(
        db,
        stream_id=stream_id,
        tenant_id=current_user.tenant_id,
        event_type="viewer_join",
        metadata=body.model_dump(),
    )
    return assessment.to_dict()


@router.get("/predictions")
async def list_predictions(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Latest cached AI predictions for tenant streams."""
    result = await db.execute(
        select(Stream).where(Stream.tenant_id == current_user.tenant_id)
    )
    streams = result.scalars().all()
    orch = get_ai_orchestrator()
    out: List[Dict[str, Any]] = []
    for s in streams:
        pred = await orch.get_stream_prediction(s.id)
        if pred:
            out.append(
                {
                    "stream_id": str(s.id),
                    "channel_name": s.channel_name,
                    "platform": s.platform.value,
                    "prediction": pred,
                }
            )
    return {"predictions": out, "count": len(out)}


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_stream(db, body.stream_id, current_user.tenant_id)
    await FeedbackStore().record(
        stream_id=str(body.stream_id),
        was_true_positive=body.was_true_positive,
        features=body.features,
        classification=body.classification,
        notes=body.notes,
    )
    return {"status": "recorded", "total_samples": await FeedbackStore().count()}


@router.post("/train")
async def trigger_training(current_user: AnalystUser):
    """Manual model retrain (admin/analyst). Runs in-process; use worker for production."""
    if current_user.role not in ("admin", "analyst", "owner"):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await TrainingPipeline().run()
    await AdaptiveLearner().tune_from_feedback()
    return result


@router.get("/metrics")
async def ai_metrics():
    from prometheus_client import REGISTRY

    names = []
    for metric in REGISTRY.collect():
        if metric.name.startswith("streamshield_ai"):
            names.append(metric.name)
    return {"prometheus_metrics": names or ["streamshield_events_published_total"]}


async def _assert_stream(db: AsyncSession, stream_id: UUID, tenant_id: UUID) -> Stream:
    result = await db.execute(
        select(Stream).where(Stream.id == stream_id, Stream.tenant_id == tenant_id)
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    return stream
