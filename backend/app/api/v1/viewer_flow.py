"""Viewer Flow Intelligence API — Kick / YouTube / TikTok."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.services.dashboard.metrics import get_tenant_stream_ids
from app.viewer_flow.engine import get_viewer_flow_engine

logger = get_logger(__name__)
router = APIRouter(prefix="/viewer-flow", tags=["Viewer Flow Intelligence"])


@router.get("/overview")
async def viewer_flow_overview(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    engine = get_viewer_flow_engine()
    if not engine.enabled:
        return {"enabled": False, "message": "VIEWER_FLOW_ENABLED=false"}
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    await engine.reconcile_tenant_streams(str(current_user.tenant_id))
    overview = await engine.build_overview(str(current_user.tenant_id))
    return {"enabled": True, "stream_ids": [str(s) for s in stream_ids], **overview.model_dump()}


@router.get("/streams/{stream_id}")
async def viewer_flow_stream(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    engine = get_viewer_flow_engine()
    if not engine.enabled:
        raise HTTPException(status_code=503, detail="Viewer flow disabled")
    stream = await db.get(Stream, stream_id)
    if not stream or stream.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Stream not found")
    if stream.platform == Platform.TWITCH:
        raise HTTPException(status_code=400, detail="Use Twitch viewers module")
    snap = await engine.get_stream_snapshot(str(stream_id))
    if not snap:
        await engine.record_viewer_pulse(
            tenant_id=str(current_user.tenant_id),
            stream_id=str(stream.id),
            platform=stream.platform,
            channel_name=stream.channel_name,
            viewer_count=stream.viewer_count or 0,
            is_live=stream.is_live,
        )
        snap = await engine.get_stream_snapshot(str(stream_id))
    if not snap:
        raise HTTPException(status_code=404, detail="No flow data yet")
    return {"enabled": True, **snap.model_dump()}


@router.get("/streams/{stream_id}/timeline")
async def viewer_flow_timeline(
    stream_id: UUID,
    current_user: AnalystUser,
    limit: int = Query(60, ge=1, le=200),
) -> Dict[str, Any]:
    engine = get_viewer_flow_engine()
    snap = await engine.get_stream_snapshot(str(stream_id))
    if not snap:
        return {"timeline": [], "count": 0}
    timeline = snap.timeline[-limit:]
    return {"timeline": [t.model_dump() for t in timeline], "count": len(timeline)}


@router.get("/streams/{stream_id}/suspicious")
async def viewer_flow_suspicious(
    stream_id: UUID,
    current_user: AnalystUser,
    limit: int = Query(40, ge=1, le=100),
) -> Dict[str, Any]:
    engine = get_viewer_flow_engine()
    snap = await engine.get_stream_snapshot(str(stream_id))
    if not snap:
        return {"suspicious": [], "count": 0}
    rows = snap.suspicious_viewers[:limit]
    return {
        "suspicious": [r.model_dump() for r in rows],
        "count": len(rows),
    }


@router.get("/cross-platform")
async def viewer_flow_cross_platform(
    current_user: AnalystUser,
    username: str = Query(..., min_length=2, max_length=64),
) -> Dict[str, Any]:
    from app.viewer_flow.mongo_store import ViewerFlowMongoStore

    store = ViewerFlowMongoStore()
    hits = await store.cross_platform_usernames(
        str(current_user.tenant_id), username
    )
    return {
        "username": username,
        "cross_platform_hits": hits,
        "coordinated_risk": hits >= 2,
    }


@router.post("/scan/{stream_id}")
async def viewer_flow_scan_stream(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger platform sync + flow reconcile for one stream."""
    from app.services.platforms.sync_service import PlatformSyncService

    engine = get_viewer_flow_engine()
    stream = await db.get(Stream, stream_id)
    if not stream or stream.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Stream not found")
    if stream.platform == Platform.TWITCH:
        raise HTTPException(status_code=400, detail="Non-Twitch only")
    sync_result = await PlatformSyncService(db).sync_viewers(stream)
    await engine.record_viewer_pulse(
        tenant_id=str(current_user.tenant_id),
        stream_id=str(stream.id),
        platform=stream.platform,
        channel_name=stream.channel_name,
        viewer_count=sync_result.get("viewer_count", stream.viewer_count or 0),
        is_live=sync_result.get("is_live", stream.is_live),
    )
    await db.commit()
    snap = await engine.get_stream_snapshot(str(stream_id))
    return {
        "ok": True,
        "sync": sync_result,
        "flow": snap.model_dump() if snap else None,
    }
