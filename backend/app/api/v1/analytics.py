from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.infrastructure.database.session import get_db
from app.services.analytics.threat_aggregator import ThreatAnalyticsAggregator

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/threats")
async def get_threat_analytics(
    current_user: CurrentUser,
    period: str = Query("30d", description="30d, 7d, 24h, etc."),
    db: AsyncSession = Depends(get_db),
):
    """Get threat intelligence analytics and trends."""

    aggregator = ThreatAnalyticsAggregator(db)
    trends = await aggregator.get_threat_trends(current_user.tenant_id, period=period)

    return {
        "tenant_id": str(current_user.tenant_id),
        **trends,
    }
