"""Enrich viewer API responses with J48 predictions."""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import ViewerSessionResponse
from app.core.config import get_settings
from app.infrastructure.database.models import ViewerSession
from app.ml.weka_j48.service import get_weka_j48_service


async def enrich_viewer_responses(
    db: AsyncSession,
    sessions: List[ViewerSession],
) -> List[ViewerSessionResponse]:
    settings = get_settings()
    if not settings.viewbot_ml_enabled or not settings.weka_j48_enabled:
        return [ViewerSessionResponse.model_validate(s) for s in sessions]

    svc = get_weka_j48_service()
    if not svc.enabled or not svc.engine.is_loaded():
        return [ViewerSessionResponse.model_validate(s) for s in sessions]

    out: List[ViewerSessionResponse] = []
    for session in sessions:
        pred = await svc.predict_session(db, session)
        base = ViewerSessionResponse.model_validate(session).model_dump()
        base["j48_is_bot"] = pred.get("is_bot")
        base["j48_probability"] = pred.get("probability")
        base["j48_backend"] = pred.get("backend")
        out.append(ViewerSessionResponse(**base))
    return out
