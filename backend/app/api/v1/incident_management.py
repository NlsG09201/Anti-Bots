from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Incident,
    IncidentStatus,
    Playbook,
    PlaybookExecution,
    Stream,
)
from app.infrastructure.database.session import get_db
from app.services.correlation.incident_correlator import IncidentCorrelator
from app.services.incident.orchestrator import PlaybookExecutor

router = APIRouter(prefix="/soc", tags=["SOC - Incidents"])
logger = get_logger(__name__)


class IncidentResponse:
    """Schema for incident response."""
    pass


class PlaybookRequest:
    """Schema for playbook creation/update."""
    pass


@router.post("/incidents/{stream_id}/correlate")
async def correlate_incident(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger incident correlation for a stream."""
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")

    result = await db.execute(
        select(Incident).where(Incident.stream_id == stream_id)
    )
    incidents = list(result.scalars().all())

    return {
        "incidents_count": len(incidents),
        "active_incidents": [
            i for i in incidents if i.status == IncidentStatus.ACTIVE
        ],
        "message": f"Found {len(incidents)} total incidents for this stream",
    }


@router.get("/incidents/{stream_id}/timeline")
async def get_incident_timeline(
    stream_id: UUID,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get chronological timeline of incidents and related events."""
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")

    result = await db.execute(
        select(Incident)
        .where(Incident.stream_id == stream_id)
        .order_by(desc(Incident.created_at))
        .limit(limit)
        .offset(offset)
    )
    incidents = list(result.scalars().all())

    timeline = []
    for incident in incidents:
        timeline.append({
            "id": str(incident.id),
            "type": "incident",
            "created_at": incident.created_at.isoformat(),
            "status": incident.status.value,
            "severity": incident.severity,
            "confidence": incident.confidence,
            "attack_count": len(incident.attack_ids or []),
            "affected_ips": len(incident.related_ips or []),
            "related_fingerprints": len(incident.related_fingerprints or []),
            "threat_actor_id": str(incident.threat_actor_id) if incident.threat_actor_id else None,
            "notes": incident.notes,
        })

    return {
        "stream_id": str(stream_id),
        "total_incidents": len(incidents),
        "timeline": timeline,
    }


@router.get("/incidents")
async def list_incidents(
    current_user: CurrentUser,
    status: Optional[str] = Query(None, description="Filter by status"),
    severity_min: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all incidents for tenant."""
    query = select(Incident).where(
        Incident.stream_id.in_(
            select(Stream.id).where(Stream.tenant_id == current_user.tenant_id)
        )
    )

    if status:
        try:
            status_enum = IncidentStatus(status)
            query = query.where(Incident.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if severity_min is not None:
        query = query.where(Incident.severity >= severity_min)

    result = await db.execute(
        query.order_by(desc(Incident.created_at)).limit(limit).offset(offset)
    )
    incidents = list(result.scalars().all())

    return {
        "count": len(incidents),
        "incidents": [
            {
                "id": str(i.id),
                "stream_id": str(i.stream_id),
                "status": i.status.value,
                "severity": i.severity,
                "confidence": i.confidence,
                "created_at": i.created_at.isoformat(),
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in incidents
        ],
    }


@router.post("/playbooks")
async def create_playbook(
    name: str,
    conditions: dict,
    actions: list,
    description: Optional[str] = None,
    enabled: bool = True,
    current_user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Create a new incident response playbook."""
    playbook = Playbook(
        tenant_id=current_user.tenant_id,
        name=name,
        description=description,
        conditions=conditions,
        actions=actions,
        enabled=enabled,
    )
    db.add(playbook)
    await db.flush()

    return {
        "id": str(playbook.id),
        "name": playbook.name,
        "enabled": playbook.enabled,
        "actions_count": len(actions),
    }


@router.get("/playbooks")
async def list_playbooks(
    current_user: CurrentUser,
    enabled_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List playbooks for tenant."""
    query = select(Playbook).where(Playbook.tenant_id == current_user.tenant_id)

    if enabled_only:
        query = query.where(Playbook.enabled == True)

    result = await db.execute(
        query.order_by(desc(Playbook.created_at)).limit(limit).offset(offset)
    )
    playbooks = list(result.scalars().all())

    return {
        "count": len(playbooks),
        "playbooks": [
            {
                "id": str(p.id),
                "name": p.name,
                "enabled": p.enabled,
                "execution_count": p.execution_count,
                "last_executed_at": p.last_executed_at.isoformat() if p.last_executed_at else None,
            }
            for p in playbooks
        ],
    }


@router.get("/playbooks/{playbook_id}")
async def get_playbook(
    playbook_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Get playbook details."""
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.tenant_id == current_user.tenant_id,
        )
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    return {
        "id": str(playbook.id),
        "name": playbook.name,
        "description": playbook.description,
        "conditions": playbook.conditions,
        "actions": playbook.actions,
        "enabled": playbook.enabled,
        "execution_count": playbook.execution_count,
        "created_at": playbook.created_at.isoformat(),
    }


@router.put("/playbooks/{playbook_id}")
async def update_playbook(
    playbook_id: UUID,
    name: Optional[str] = None,
    conditions: Optional[dict] = None,
    actions: Optional[list] = None,
    enabled: Optional[bool] = None,
    current_user: CurrentUser = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Update playbook."""
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.tenant_id == current_user.tenant_id,
        )
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    if name is not None:
        playbook.name = name
    if conditions is not None:
        playbook.conditions = conditions
    if actions is not None:
        playbook.actions = actions
    if enabled is not None:
        playbook.enabled = enabled

    await db.flush()

    return {"id": str(playbook.id), "updated": True}


@router.delete("/playbooks/{playbook_id}")
async def delete_playbook(
    playbook_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Delete playbook."""
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.tenant_id == current_user.tenant_id,
        )
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    await db.delete(playbook)
    await db.flush()

    return {"deleted": True}


@router.post("/playbooks/{playbook_id}/execute")
async def execute_playbook(
    playbook_id: UUID,
    incident_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Manually execute a playbook against an incident."""
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.tenant_id == current_user.tenant_id,
        )
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.stream_id.in_(
                select(Stream.id).where(Stream.tenant_id == current_user.tenant_id)
            ),
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    executor = PlaybookExecutor(db)
    execution = await executor.execute_playbook(
        playbook,
        incident,
        current_user.tenant_id,
    )
    await db.commit()

    return {
        "execution_id": str(execution.id),
        "status": execution.status,
        "executed_actions": len(execution.executed_actions or []),
        "failed_actions": len(execution.failed_actions or []),
        "duration_ms": execution.execution_duration_ms,
    }
