"""Métricas SOC agregadas por plataforma y threat level."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Attack,
    Platform,
    Stream,
    StreamEvent,
    ViewerSession,
)


async def compute_soc_overview(
    db: AsyncSession,
    tenant_id: UUID,
    stream_ids: List[UUID],
) -> Dict[str, Any]:
    since_1h = datetime.now(timezone.utc) - timedelta(hours=1)
    platforms = {
        p.value: {
            "live_streams": 0,
            "viewers": 0,
            "suspected": 0,
            "events_1h": 0,
            "active_attacks": 0,
        }
        for p in Platform
    }

    if stream_ids:
        stream_rows = await db.execute(
            select(Stream.platform, Stream.is_live, Stream.viewer_count).where(
                Stream.id.in_(stream_ids)
            )
        )
        for platform, is_live, viewer_count in stream_rows.all():
            key = platform.value if hasattr(platform, "value") else str(platform)
            if key not in platforms:
                continue
            if is_live:
                platforms[key]["live_streams"] += 1
            platforms[key]["viewers"] += int(viewer_count or 0)

        suspected_rows = await db.execute(
            select(Stream.platform, func.count(ViewerSession.id))
            .join(Stream, ViewerSession.stream_id == Stream.id)
            .where(
                ViewerSession.stream_id.in_(stream_ids),
                ViewerSession.is_suspected_bot == True,
                ViewerSession.is_active == True,
            )
            .group_by(Stream.platform)
        )
        for platform, count in suspected_rows.all():
            key = platform.value if hasattr(platform, "value") else str(platform)
            if key in platforms:
                platforms[key]["suspected"] = int(count or 0)

        event_rows = await db.execute(
            select(Stream.platform, func.count(StreamEvent.id))
            .join(Stream, StreamEvent.stream_id == Stream.id)
            .where(
                StreamEvent.stream_id.in_(stream_ids),
                StreamEvent.created_at >= since_1h,
            )
            .group_by(Stream.platform)
        )
        for platform, count in event_rows.all():
            key = platform.value if hasattr(platform, "value") else str(platform)
            if key in platforms:
                platforms[key]["events_1h"] = int(count or 0)

        attack_rows = await db.execute(
            select(Stream.platform, func.count(Attack.id))
            .join(Stream, Attack.stream_id == Stream.id)
            .where(
                Attack.stream_id.in_(stream_ids),
                Attack.status == "active",
            )
            .group_by(Stream.platform)
        )
        for platform, count in attack_rows.all():
            key = platform.value if hasattr(platform, "value") else str(platform)
            if key in platforms:
                platforms[key]["active_attacks"] = int(count or 0)

    total_suspected = sum(p["suspected"] for p in platforms.values())
    total_viewers = sum(p["viewers"] for p in platforms.values())
    total_attacks = sum(p["active_attacks"] for p in platforms.values())
    threat_score = min(
        100.0,
        (total_attacks * 18)
        + (total_suspected * 2.5)
        + max(0, total_viewers - 500) * 0.02,
    )
    if threat_score >= 75:
        threat_level = "critical"
    elif threat_score >= 50:
        threat_level = "high"
    elif threat_score >= 25:
        threat_level = "medium"
    else:
        threat_level = "low"

    return {
        "platforms": platforms,
        "threat_score": round(threat_score, 1),
        "threat_level": threat_level,
        "global": {
            "live_viewers": total_viewers,
            "suspected_bots": total_suspected,
            "active_attacks": total_attacks,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def recent_live_feed(
    db: AsyncSession,
    stream_ids: List[UUID],
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if not stream_ids:
        return []
    rows = await db.execute(
        select(
            StreamEvent,
            Stream.platform,
            Stream.channel_name,
        )
        .join(Stream, StreamEvent.stream_id == Stream.id)
        .where(StreamEvent.stream_id.in_(stream_ids))
        .order_by(StreamEvent.created_at.desc())
        .limit(limit)
    )
    feed = []
    for event, platform, channel in rows.all():
        feed.append({
            "id": str(event.id),
            "platform": platform.value if hasattr(platform, "value") else str(platform),
            "channel_name": channel,
            "event_type": event.event_type,
            "platform_username": event.platform_username,
            "risk_score": float(event.risk_score or 0),
            "created_at": event.created_at.isoformat(),
            "is_proxy": bool(event.is_proxy),
        })
    return feed
