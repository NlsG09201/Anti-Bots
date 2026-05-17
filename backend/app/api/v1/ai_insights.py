from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import AIInsightResponse
from app.core.exceptions import NotFoundError
from app.infrastructure.database.models import Attack, Stream
from app.infrastructure.database.session import get_db
from app.services.ai.service import AIService
from app.services.streams.helpers import stream_monitor_mode

router = APIRouter(prefix="/ai", tags=["AI Insights"])
ai_service = AIService()


@router.get("/attacks/{attack_id}/insight", response_model=AIInsightResponse)
async def get_attack_insight(
    attack_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attack, Stream)
        .join(Stream, Attack.stream_id == Stream.id)
        .where(Attack.id == attack_id, Stream.tenant_id == current_user.tenant_id)
    )
    row = result.first()
    if not row:
        raise NotFoundError("Attack")
    attack, stream = row

    cached = (attack.evidence or {}).get("ai_insight")
    if cached:
        return AIInsightResponse(**cached)

    insight = await ai_service.analyze_threat(
        attack.attack_type.value,
        attack.risk_score,
        stream.channel_name,
        attack.evidence or {},
        monitor_mode=stream_monitor_mode(stream),
    )
    return AIInsightResponse(**insight)
