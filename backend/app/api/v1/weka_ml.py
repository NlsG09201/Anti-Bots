"""API: Weka J48 bot classifier — train, health, predict."""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser, get_db
from app.infrastructure.database.models import Stream, ViewerSession
from app.ml.weka_j48.service import get_weka_j48_service
from app.services.dashboard.metrics import get_tenant_stream_ids

router = APIRouter(prefix="/ml/weka-j48", tags=["ml-weka-j48"])


class TrainResponse(BaseModel):
    ok: bool
    samples: int | None = None
    training: Dict[str, Any] | None = None
    error: str | None = None
    required: int | None = None


class PredictResponse(BaseModel):
    enabled: bool
    session_id: str | None = None
    platform_username: str | None = None
    is_bot: bool | None = None
    probability: float | None = None
    class_label: str | None = None
    backend: str | None = None
    error: str | None = None


@router.get("/health")
async def weka_health(
    _current_user: CurrentUser,
) -> Dict[str, Any]:
    return get_weka_j48_service().health()


@router.post("/train", response_model=TrainResponse)
async def train_j48(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5000, ge=100, le=20000),
):
    svc = get_weka_j48_service()
    result = await svc.train_for_tenant(db, current_user.tenant_id, limit=limit)
    return TrainResponse(**result)


@router.get("/predict/session/{session_id}", response_model=PredictResponse)
async def predict_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    if not stream_ids:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(ViewerSession).where(
            ViewerSession.id == session_id,
            ViewerSession.stream_id.in_(stream_ids),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    pred = await get_weka_j48_service().predict_session(db, session)
    return PredictResponse(**pred)


@router.get("/predict/stream/{stream_id}")
async def predict_stream(
    stream_id: UUID,
    current_user: CurrentUser,
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stream = await db.get(Stream, stream_id)
    if not stream or stream.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Stream not found")
    predictions = await get_weka_j48_service().predict_stream_viewers(
        db, stream_id, limit=limit
    )
    bots = sum(1 for p in predictions if p.get("is_bot"))
    return {
        "stream_id": str(stream_id),
        "count": len(predictions),
        "predicted_bots": bots,
        "predictions": predictions,
    }
