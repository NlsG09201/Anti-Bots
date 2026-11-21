"""Operations research endpoints backed by tenant operational data."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.infrastructure.database.models import Stream, ViewerSession
from app.services.optimization.review_queue import ReviewCandidate, optimize_review_queue

router = APIRouter(prefix="/operations-research", tags=["Operations Research"])


class ReviewOptimizationRequest(BaseModel):
    capacity_minutes: int = Field(ge=1, le=1440)
    minutes_per_review: int = Field(default=5, ge=1, le=120)
    false_positive_budget: int = Field(default=50, ge=0, le=100)
    false_positive_cost: float = Field(default=1.0, ge=0, le=10)
    stream_id: UUID | None = None
    max_candidates: int = Field(default=500, ge=1, le=2000)


@router.post("/review-queue/optimize")
async def optimize_review_queue_endpoint(
    payload: ReviewOptimizationRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ViewerSession, Stream)
        .join(Stream, Stream.id == ViewerSession.stream_id)
        .where(
            Stream.tenant_id == current_user.tenant_id,
            ViewerSession.is_active.is_(True),
            ViewerSession.is_suspected_bot.is_(True),
        )
        .order_by(ViewerSession.risk_score.desc(), ViewerSession.joined_at.asc())
        .limit(payload.max_candidates)
    )
    if payload.stream_id:
        query = query.where(Stream.id == payload.stream_id)
    result = await db.execute(query)
    pairs = result.all()
    if payload.stream_id and not pairs:
        stream_exists = await db.scalar(
            select(Stream.id).where(
                Stream.id == payload.stream_id,
                Stream.tenant_id == current_user.tenant_id,
            )
        )
        if not stream_exists:
            raise HTTPException(status_code=404, detail="Stream not found")

    candidates = [
        ReviewCandidate(
            session_id=str(session.id),
            stream_name=stream.channel_name,
            username=session.platform_username or "(sin usuario)",
            risk_score=session.risk_score or 0,
        )
        for session, stream in pairs
    ]
    try:
        result = optimize_review_queue(
            candidates,
            payload.capacity_minutes,
            payload.minutes_per_review,
            payload.false_positive_budget,
            payload.false_positive_cost,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["data_source"] = "viewer_sessions activos y sospechosos del tenant autenticado"
    result["truncated"] = len(pairs) == payload.max_candidates
    return result
