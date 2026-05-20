"""API del panel de métricas de seguridad."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.services.security.dashboard import compute_security_dashboard

router = APIRouter(prefix="/security", tags=["Security"])


@router.get("/dashboard")
async def security_dashboard(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=72),
    stream_id: Optional[UUID] = None,
):
    """
    Métricas SOC: bloqueos 429/403, proxy/VPN, flags y desglose por canal.
    """
    return await compute_security_dashboard(
        db,
        current_user.tenant_id,
        stream_id=stream_id,
        hours=hours,
    )
