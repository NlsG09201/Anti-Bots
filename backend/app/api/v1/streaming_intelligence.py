"""Streaming Threat Intelligence API — engagement, graphs, global TI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.infrastructure.database.models import Stream
from app.threat_intel_engine import get_threat_intel_engine
from app.threat_intel_engine.mongo_store import ThreatIntelMongoStore

router = APIRouter(
    prefix="/streaming-intelligence",
    tags=["Streaming Threat Intelligence"],
)


@router.get("/overview")
async def intelligence_overview(
    current_user: AnalystUser,
) -> Dict[str, Any]:
    from app.core.config import get_settings

    engine = get_threat_intel_engine()
    cfg = get_settings()
    if not engine.enabled:
        return {"enabled": False, "message": "THREAT_INTEL_ENGINE_ENABLED=false"}
    data = await engine.overview(current_user.tenant_id)
    return {
        "enabled": True,
        "mongodb": bool(cfg.mongodb_uri),
        **data,
    }


@router.get("/streams/{stream_id}")
async def stream_intelligence(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _assert_stream(db, stream_id, current_user.tenant_id)
    engine = get_threat_intel_engine()
    cached = await engine.get_stream_intel(current_user.tenant_id, stream_id)
    store = ThreatIntelMongoStore()
    engagement = await store.get_engagement(
        str(current_user.tenant_id), str(stream_id)
    )
    edges = await store.get_graph_edges(
        str(current_user.tenant_id), str(stream_id)
    )
    return {
        "stream_id": str(stream_id),
        "cached": cached,
        "engagement": engagement,
        "graph_edge_count": len(edges),
    }


@router.get("/streams/{stream_id}/engagement")
async def stream_engagement(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _assert_stream(db, stream_id, current_user.tenant_id)
    doc = await ThreatIntelMongoStore().get_engagement(
        str(current_user.tenant_id), str(stream_id)
    )
    if not doc:
        live = get_threat_intel_engine().live_engagement(str(stream_id))
        return {"stream_id": str(stream_id), "engagement": live.model_dump(), "source": "live"}
    return {"stream_id": str(stream_id), "engagement": doc, "source": "mongodb"}


@router.get("/streams/{stream_id}/graph")
async def stream_threat_graph(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _assert_stream(db, stream_id, current_user.tenant_id)
    graph = get_threat_intel_engine().live_graph(str(stream_id))
    return {"stream_id": str(stream_id), "graph": graph.model_dump()}


@router.get("/entities/top")
async def top_threat_entities(
    current_user: AnalystUser,
    limit: int = Query(50, ge=1, le=100),
) -> Dict[str, Any]:
    entities = await ThreatIntelMongoStore().top_threat_entities(
        str(current_user.tenant_id), limit=limit
    )
    return {
        "entities": [
            {
                "entity_key": e.get("entity_key"),
                "username": e.get("username"),
                "platform": e.get("platform"),
                "threat_score": e.get("threat_score"),
                "trust_score": e.get("trust_score"),
                "bot_probability": e.get("bot_probability"),
                "engagement_score": e.get("engagement_score"),
                "flags": e.get("flags") or [],
            }
            for e in entities
        ],
        "count": len(entities),
    }


@router.get("/entities/{entity_key}")
async def get_entity_profile(
    entity_key: str,
    current_user: AnalystUser,
) -> Dict[str, Any]:
    doc = await ThreatIntelMongoStore().get_entity(
        str(current_user.tenant_id), entity_key
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"entity": doc}


@router.get("/cross-platform")
async def cross_platform_links(
    current_user: AnalystUser,
    username: str = Query(..., min_length=2, max_length=64),
) -> Dict[str, Any]:
    from app.threat_intel_engine.cross_platform import CrossPlatformCorrelator

    matches = await CrossPlatformCorrelator(ThreatIntelMongoStore()).find_matches(
        str(current_user.tenant_id), username
    )
    return {"username": username, "matches": matches}


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
