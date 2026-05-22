"""Live Stream Intelligence Monitor API."""

from __future__ import annotations

import time
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.infrastructure.database.models import Stream
from app.live_intel.engine import get_live_intel_engine, is_competitive_stream
from app.live_intel.mongo_store import LiveIntelMongoStore
from app.live_intel.serialize import overview_to_api_dict

router = APIRouter(prefix="/live-intelligence", tags=["Live Stream Intelligence"])


class CompareRequest(BaseModel):
    stream_ids: List[UUID] = Field(..., min_length=2, max_length=10)


@router.get("/overview")
async def live_intel_overview(
    current_user: AnalystUser,
    refresh: bool = Query(False, description="Sync live status from platforms (slow)"),
) -> Dict[str, Any]:
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    engine = get_live_intel_engine()
    if not engine.enabled:
        return {"enabled": False}
    try:
        overview = await engine.get_overview(
            current_user.tenant_id, refresh=refresh
        )
        return {"enabled": True, "overview": overview_to_api_dict(overview)}
    except Exception as exc:
        logger.exception(
            "live_intel_overview_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc)[:200],
        )
        raise HTTPException(
            status_code=503,
            detail="Live intelligence overview unavailable",
        ) from exc


@router.get("/streams")
async def list_monitored_streams(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    try:
        result = await db.execute(
            select(Stream).where(Stream.tenant_id == current_user.tenant_id)
        )
        streams = [s for s in result.scalars().all() if is_competitive_stream(s)]
    except Exception as exc:
        logger.exception(
            "live_intel_streams_list_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc)[:200],
        )
        raise HTTPException(
            status_code=503,
            detail="Could not load monitored streams",
        ) from exc
    engine = get_live_intel_engine()
    out = []
    for s in streams:
        sid = str(s.id)
        snap = engine.get_snapshot(sid)
        try:
            snap_payload = snap.model_dump(mode="json") if snap else None
        except Exception:
            snap_payload = None
        platform = s.platform.value if hasattr(s.platform, "value") else str(s.platform)
        out.append(
            {
                "stream_id": sid,
                "channel_name": s.channel_name,
                "platform": platform,
                "is_live": s.is_live,
                "viewer_count": s.viewer_count,
                "competitive_intel": bool((s.settings or {}).get("competitive_intel")),
                "snapshot": snap_payload,
            }
        )
    return {"streams": out, "count": len(out)}


@router.get("/streams/{stream_id}")
async def stream_live_intel(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stream = await _assert_stream(db, stream_id, current_user.tenant_id)
    engine = get_live_intel_engine()
    snap = await engine.sample_stream(stream)
    await db.commit()
    history = await LiveIntelMongoStore().get_history(
        str(current_user.tenant_id), str(stream_id), limit=120
    )
    return {
        "stream_id": str(stream_id),
        "snapshot": snap.model_dump() if snap else None,
        "history": history,
    }


@router.get("/streams/{stream_id}/history")
async def stream_history(
    stream_id: UUID,
    current_user: AnalystUser,
    limit: int = Query(200, ge=10, le=500),
) -> Dict[str, Any]:
    points = await LiveIntelMongoStore().get_history(
        str(current_user.tenant_id), str(stream_id), limit=limit
    )
    return {"stream_id": str(stream_id), "points": points, "count": len(points)}


@router.post("/compare")
async def compare_streams_api(
    body: CompareRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    for sid in body.stream_ids:
        await _assert_stream(db, sid, current_user.tenant_id)
    engine = get_live_intel_engine()
    tid = str(current_user.tenant_id)
    for sid in body.stream_ids:
        result = await db.execute(select(Stream).where(Stream.id == sid))
        stream = result.scalar_one_or_none()
        if stream:
            await engine.sample_stream(stream)
    await db.commit()
    return engine.compare(tid, [str(s) for s in body.stream_ids])


@router.get("/anomalies")
async def recent_anomalies(
    current_user: AnalystUser,
    limit: int = Query(40, ge=1, le=100),
) -> Dict[str, Any]:
    items = await LiveIntelMongoStore().recent_anomalies(
        str(current_user.tenant_id), limit=limit
    )
    return {"anomalies": items, "count": len(items)}


@router.get("/health-monitor")
async def get_health_monitor(current_user: AnalystUser) -> Dict[str, Any]:
    from app.services.monitoring.health_engine import get_health_monitoring_engine
    health = get_health_monitoring_engine()
    
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.models import Stream
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Stream).where(
                Stream.tenant_id == current_user.tenant_id,
                Stream.is_live == True
            )
        )
        live_streams = result.scalars().all()
        
    streams_health = []
    for s in live_streams:
        h = await health.get_stream_health(str(s.id))
        streams_health.append({
            "id": s.id,
            "channel": s.channel_name,
            "platform": s.platform.value,
            **h
        })
        
    return {
        "timestamp": time.time(),
        "streams": streams_health,
        "platform_status": await health.get_global_status()
    }


async def _assert_stream(
    db: AsyncSession, stream_id: UUID, tenant_id: UUID
) -> Stream:
    result = await db.execute(
        select(Stream).where(Stream.id == stream_id, Stream.tenant_id == tenant_id)
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    return stream
