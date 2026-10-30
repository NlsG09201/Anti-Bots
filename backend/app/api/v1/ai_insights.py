from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.api.v1.schemas import AIInsightResponse
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.infrastructure.database.models import AIUsageRecord, Attack, AuditLog, Stream, UserRole
from app.infrastructure.database.session import get_db
from app.services.ai.service import AIService
from app.services.streams.helpers import stream_monitor_mode

router = APIRouter(prefix="/ai", tags=["AI Insights"])
ai_service = AIService()
logger = get_logger(__name__)


class AIModerationModeInput(BaseModel):
    mode: Literal["monitor", "assisted", "automatic"]


@router.get("/streams/{stream_id}/moderation-mode")
async def get_ai_moderation_mode(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await db.scalar(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    if not stream:
        raise NotFoundError("Stream")
    return {
        "stream_id": str(stream.id),
        "mode": (stream.settings or {}).get("ai_moderation_mode", "monitor"),
        "automatic_available": bool((stream.settings or {}).get("auto_mitigate")),
        "can_manage": stream.owner_id == current_user.id
        or current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN),
    }


@router.put("/streams/{stream_id}/moderation-mode")
async def set_ai_moderation_mode(
    stream_id: UUID,
    body: AIModerationModeInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await db.scalar(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    if not stream:
        raise NotFoundError("Stream")
    if stream.owner_id != current_user.id and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Solo el propietario o administrador puede cambiar el modo.")
    if body.mode == "automatic":
        meta = stream.settings or {}
        if not meta.get("auto_mitigate"):
            raise HTTPException(
                status_code=409,
                detail="Activa primero la mitigación automática existente del canal. La IA no ejecuta sanciones por sí sola.",
            )
        if meta.get("is_owned") and not stream.oauth_token_encrypted:
            raise HTTPException(status_code=409, detail="Conecta el broadcaster para habilitar el flujo automático autorizado.")
    meta = dict(stream.settings or {})
    meta["ai_moderation_mode"] = body.mode
    stream.settings = meta
    db.add(
        AuditLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="ai.moderation_mode.updated",
            resource_type="stream",
            resource_id=str(stream.id),
            details={"mode": body.mode},
        )
    )
    await db.commit()
    return {"stream_id": str(stream.id), "mode": body.mode}


@router.post("/openai/validate")
async def validate_openai_connection(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    """Verify configured credentials/model access without sending user content."""
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise HTTPException(status_code=503, detail="OpenAI no está configurado.")
    from app.services.ai.openai_engine import (
        get_openai_client,
        reserve_openai_calls,
        track_openai_request,
    )

    if not await reserve_openai_calls(current_user.tenant_id):
        raise HTTPException(status_code=429, detail="Límite de validaciones OpenAI alcanzado.")
    try:
        model = await track_openai_request(
            "connection_check",
            get_openai_client().models.retrieve(settings.openai_model),
        )
        db.add(
            AIUsageRecord(
                tenant_id=current_user.tenant_id,
                operation="connection_check",
                model=settings.openai_model,
                input_tokens=0,
                output_tokens=0,
                status="ok",
            )
        )
        await db.commit()
        return {"connected": True, "model": getattr(model, "id", settings.openai_model)}
    except Exception as exc:
        logger.warning("openai_connection_check_failed", error_type=type(exc).__name__)
        db.add(
            AIUsageRecord(
                tenant_id=current_user.tenant_id,
                operation="connection_check",
                model=settings.openai_model,
                status="error",
                error_code=type(exc).__name__[:80],
            )
        )
        await db.commit()
        raise HTTPException(status_code=503, detail="OpenAI no pudo validar la clave o el modelo configurado.") from exc


@router.get("/usage")
async def get_ai_usage(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    """Return usage and configured cost estimates scoped to the current tenant."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    row = (
        await db.execute(
            select(
                func.count(AIUsageRecord.id),
                func.coalesce(func.sum(AIUsageRecord.input_tokens), 0),
                func.coalesce(func.sum(AIUsageRecord.output_tokens), 0),
                func.sum(AIUsageRecord.estimated_cost_usd),
            ).where(
                AIUsageRecord.tenant_id == current_user.tenant_id,
                AIUsageRecord.created_at >= cutoff,
            )
        )
    ).one()
    settings = get_settings()
    cost_configured = bool(
        settings.openai_input_cost_per_million > 0
        and settings.openai_output_cost_per_million > 0
    )
    return {
        "days": days,
        "request_count": int(row[0] or 0),
        "input_tokens": int(row[1] or 0),
        "output_tokens": int(row[2] or 0),
        "estimated_cost_usd": float(row[3]) if row[3] is not None else None,
        "cost_estimation_configured": cost_configured,
        "openai_configured": bool(settings.ai_enabled and settings.openai_api_key and settings.openai_model),
    }


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
        db=db,
        tenant_id=current_user.tenant_id,
        stream_id=stream.id,
        platform=stream.platform.value,
        incident_reference=attack.correlation_id,
    )
    await db.commit()
    return AIInsightResponse(**insight)
