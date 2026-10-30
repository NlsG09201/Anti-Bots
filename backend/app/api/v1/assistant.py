"""Tenant-scoped, read-only SOC assistant API."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser
from app.api.v1.schemas import AssistantChatRequest, AssistantChatResponse
from app.core.exceptions import NotFoundError
from app.infrastructure.database.models import Attack, Stream, StreamEvent
from app.infrastructure.database.session import get_db
from app.services.assistant.service import StreamShieldAssistant

router = APIRouter(prefix="/assistant", tags=["SOC Assistant"])
assistant_service = StreamShieldAssistant()


def _safe_attack_context(attack: Attack) -> dict:
    evidence = attack.evidence or {}
    return {
        "type": attack.attack_type.value,
        "status": attack.status,
        "severity": attack.severity.value,
        "risk_score": attack.risk_score,
        "confidence": attack.confidence,
        "created_at": attack.created_at.isoformat() if attack.created_at else None,
        "evidence_summary": str(
            (evidence.get("ai_insight") or {}).get("summary")
            or evidence.get("summary")
            or ""
        )[:500],
        "correlation_id": attack.correlation_id,
    }


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Query only records belonging to the caller's tenant; never executes actions."""
    context: dict = {}
    stream_id = payload.stream_id
    if payload.attack_id:
        result = await db.execute(
            select(Attack, Stream)
            .join(Stream, Attack.stream_id == Stream.id)
            .where(
                Attack.id == payload.attack_id,
                Stream.tenant_id == current_user.tenant_id,
            )
        )
        row = result.first()
        if not row:
            raise NotFoundError("Incident")
        attack, stream = row
        if stream_id and stream_id != stream.id:
            raise NotFoundError("Incident")
        stream_id = stream.id
        context["incident"] = _safe_attack_context(attack)

    if stream_id:
        stream = await db.scalar(
            select(Stream).where(
                Stream.id == stream_id,
                Stream.tenant_id == current_user.tenant_id,
            )
        )
        if not stream:
            raise NotFoundError("Stream")
        context["channel"] = {
            "name": stream.channel_name[:100],
            "platform": stream.platform.value,
            "is_live": stream.is_live,
            "viewer_count": stream.viewer_count,
        }
        attacks = list(
            (
                await db.scalars(
                    select(Attack)
                    .where(Attack.stream_id == stream.id)
                    .order_by(Attack.created_at.desc())
                    .limit(5)
                )
            ).all()
        )
        if attacks:
            context["recent_incidents"] = [_safe_attack_context(attack) for attack in attacks]
        events = list(
            (
                await db.scalars(
                    select(StreamEvent)
                    .where(StreamEvent.stream_id == stream.id)
                    .order_by(StreamEvent.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
        context["recent_activity"] = [
            {
                "event_type": event.event_type,
                "risk_score": event.risk_score,
                "created_at": event.created_at.isoformat() if event.created_at else None,
                "ai_chat_analysis": (event.event_metadata or {}).get("openai_chat_analysis"),
                "ai_intel": (event.event_metadata or {}).get("ai_intel"),
            }
            for event in events
        ]

    answer, source = await assistant_service.answer(
        payload.message,
        [message.model_dump() for message in payload.history],
        security_context=context,
        db=db,
        tenant_id=current_user.tenant_id,
        stream_id=stream_id,
    )
    await db.commit()
    return AssistantChatResponse(
        answer=answer,
        source=source,
        disclaimer="Orientación SOC; valida la evidencia antes de aplicar medidas permanentes.",
    )
