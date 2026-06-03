"""API endpoints for alert management."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.infrastructure.repositories.alert_repository import AlertRepository
from app.services.alert_engine import AlertEngine

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/{stream_id}")
async def get_stream_alerts(
    stream_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    dismissed: Optional[bool] = Query(None),
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get alerts for a stream with filtering and pagination."""
    try:
        repo = AlertRepository(session)
        alerts, total = await repo.get_stream_alerts(
            stream_id=stream_id,
            limit=limit,
            offset=offset,
            dismissed=dismissed,
            severity=severity,
            alert_type=alert_type,
        )

        return {
            "items": [alert.to_dict() for alert in alerts],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.error("get_stream_alerts_failed", stream=stream_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch alerts")


@router.get("/stream/{stream_id}/active")
async def get_active_alerts(
    stream_id: str,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get active (non-dismissed) alerts for a stream."""
    try:
        repo = AlertRepository(session)
        alerts, total = await repo.get_stream_alerts(
            stream_id=stream_id,
            dismissed=False,
            limit=limit,
        )

        return {
            "items": [alert.to_dict() for alert in alerts],
            "total": total,
        }
    except Exception as exc:
        logger.error("get_active_alerts_failed", stream=stream_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch active alerts")


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    reason: Optional[str] = None,
    dismissed_by: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Dismiss an alert."""
    try:
        repo = AlertRepository(session)
        alert = await repo.dismiss_alert(
            alert_id=UUID(alert_id),
            reason=reason,
            dismissed_by=dismissed_by,
        )

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        await session.commit()
        return alert.to_dict()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")
    except Exception as exc:
        logger.error("dismiss_alert_failed", alert=alert_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to dismiss alert")


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acked_by: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Acknowledge an alert."""
    try:
        repo = AlertRepository(session)
        alert = await repo.acknowledge_alert(
            alert_id=UUID(alert_id),
            acked_by=acked_by,
        )

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        await session.commit()
        return alert.to_dict()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")
    except Exception as exc:
        logger.error("acknowledge_alert_failed", alert=alert_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert")


@router.get("/{alert_id}")
async def get_alert_detail(
    alert_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get detailed information about an alert including history."""
    try:
        repo = AlertRepository(session)
        alert = await repo.get_alert_by_id(UUID(alert_id))

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        history = await repo.get_alert_history(UUID(alert_id))

        return {
            **alert.to_dict(),
            "history": [h.to_dict() for h in history],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")
    except Exception as exc:
        logger.error("get_alert_detail_failed", alert=alert_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch alert details")


@router.get("/tenant/{tenant_id}")
async def get_tenant_alerts(
    tenant_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    dismissed: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all alerts for a tenant across all streams."""
    try:
        repo = AlertRepository(session)
        alerts, total = await repo.get_tenant_alerts(
            tenant_id=UUID(tenant_id),
            limit=limit,
            offset=offset,
            dismissed=dismissed,
        )

        return {
            "items": [alert.to_dict() for alert in alerts],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID")
    except Exception as exc:
        logger.error("get_tenant_alerts_failed", tenant=tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch tenant alerts")


@router.get("/stream/{stream_id}/recent")
async def get_recent_alerts(
    stream_id: str,
    minutes: int = Query(60, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
):
    """Get recent alerts for a stream (within N minutes)."""
    try:
        repo = AlertRepository(session)
        alerts = await repo.get_recent_alerts_for_stream(
            stream_id=stream_id,
            minutes=minutes,
        )

        return {
            "items": [alert.to_dict() for alert in alerts],
            "total": len(alerts),
            "minutes": minutes,
        }
    except Exception as exc:
        logger.error("get_recent_alerts_failed", stream=stream_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch recent alerts")
