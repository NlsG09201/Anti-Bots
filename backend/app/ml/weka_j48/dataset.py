"""Load viewer feature rows from PostgreSQL for J48 training."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Ban, Stream, StreamEvent, ViewerSession
from app.ml.weka_j48.features import ViewerMLRow, label_from_session, session_to_features
from app.services.dashboard.metrics import get_tenant_stream_ids


async def _event_stats_for_streams(
    db: AsyncSession,
    stream_ids: List[UUID],
) -> Dict[UUID, Dict[str, float]]:
    if not stream_ids:
        return {}

    by_user: Dict[UUID, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"event_count": 0, "proxy": 0, "vpn": 0, "dc": 0})
    )

    result = await db.execute(
        select(
            StreamEvent.stream_id,
            StreamEvent.platform_username,
            StreamEvent.platform_user_id,
            StreamEvent.is_proxy,
            StreamEvent.is_vpn,
            StreamEvent.is_datacenter,
        ).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.platform_username.isnot(None),
        )
    )
    for stream_id, username, user_id, is_proxy, is_vpn, is_dc in result.all():
        key = (username or user_id or "").lower()
        if not key:
            continue
        bucket = by_user[stream_id][key]
        bucket["event_count"] += 1
        if is_proxy:
            bucket["proxy"] += 1
        if is_vpn:
            bucket["vpn"] += 1
        if is_dc:
            bucket["dc"] += 1

    out: Dict[UUID, Dict[str, Dict[str, float]]] = {}
    for sid, users in by_user.items():
        out[sid] = {}
        for uname, raw in users.items():
            n = max(raw["event_count"], 1)
            out[sid][uname] = {
                "event_count": float(raw["event_count"]),
                "proxy_ratio": raw["proxy"] / n,
                "vpn_ratio": raw["vpn"] / n,
                "datacenter_ratio": raw["dc"] / n,
            }
    return out


async def _banned_usernames(db: AsyncSession, stream_ids: List[UUID]) -> set[str]:
    result = await db.execute(
        select(Ban.target_value).where(
            Ban.stream_id.in_(stream_ids),
            Ban.is_active == True,
            Ban.target_type == "user",
        )
    )
    return {row[0].lower() for row in result.all() if row[0]}


async def load_training_rows(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    limit: int = 5000,
    include_inactive: bool = True,
) -> List[ViewerMLRow]:
    stream_ids = await get_tenant_stream_ids(db, tenant_id)
    if not stream_ids:
        return []

    event_stats = await _event_stats_for_streams(db, stream_ids)
    banned = await _banned_usernames(db, stream_ids)

    query = select(ViewerSession).where(ViewerSession.stream_id.in_(stream_ids))
    if not include_inactive:
        query = query.where(ViewerSession.is_active == True)
    query = query.order_by(ViewerSession.updated_at.desc()).limit(limit)

    result = await db.execute(query)
    sessions = list(result.scalars().all())

    rows: List[ViewerMLRow] = []
    for session in sessions:
        uname = (session.platform_username or session.platform_user_id or "").lower()
        stats = event_stats.get(session.stream_id, {}).get(uname, {})
        feats = session_to_features(session, stats)
        force_bot = uname in banned
        label = label_from_session(session, force_bot=force_bot)
        rows.append(
            ViewerMLRow(
                features=feats,
                label=label,
                session_id=str(session.id),
                platform_username=session.platform_username,
            )
        )
    return rows


async def load_session_row(
    db: AsyncSession,
    session: ViewerSession,
) -> ViewerMLRow:
    stats_map = await _event_stats_for_streams(db, [session.stream_id])
    uname = (session.platform_username or session.platform_user_id or "").lower()
    stats = stats_map.get(session.stream_id, {}).get(uname, {})
    return ViewerMLRow(
        features=session_to_features(session, stats),
        label=None,
        session_id=str(session.id),
        platform_username=session.platform_username,
    )
