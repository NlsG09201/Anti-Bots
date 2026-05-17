from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Alert,
    Attack,
    Ban,
    IPReputation,
    MitigationAction,
    Stream,
    StreamEvent,
    ViewerSession,
)


def _hour_label(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%H:00")


async def get_tenant_stream_ids(db: AsyncSession, tenant_id: UUID) -> List[UUID]:
    result = await db.execute(select(Stream.id).where(Stream.tenant_id == tenant_id))
    return [row[0] for row in result.all()]


async def compute_dashboard_stats(
    db: AsyncSession,
    tenant_id: UUID,
    stream_ids: Optional[List[UUID]] = None,
) -> Dict[str, Any]:
    if stream_ids is None:
        stream_ids = await get_tenant_stream_ids(db, tenant_id)

    if not stream_ids:
        return {
            "active_attacks": 0,
            "total_alerts": 0,
            "blocked_ips": 0,
            "suspected_bots": 0,
            "live_viewers": 0,
            "risk_score_avg": 0.0,
            "attacks_last_24h": 0,
            "mitigations_applied": 0,
        }

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    active_attacks = await db.scalar(
        select(func.count(Attack.id)).where(
            Attack.stream_id.in_(stream_ids),
            Attack.status == "active",
        )
    )
    attacks_24h = await db.scalar(
        select(func.count(Attack.id)).where(
            Attack.stream_id.in_(stream_ids),
            Attack.created_at >= since_24h,
        )
    )
    mitigations = await db.scalar(
        select(func.count(Attack.id)).where(
            Attack.stream_id.in_(stream_ids),
            Attack.mitigation_action != MitigationAction.NONE,
        )
    )
    alerts = await db.scalar(
        select(func.count(Alert.id)).where(
            Alert.tenant_id == tenant_id,
            Alert.status == "open",
        )
    )
    blocked = await db.scalar(
        select(func.count(IPReputation.id)).where(IPReputation.is_blocked == True)
    )
    bots = await db.scalar(
        select(func.count(ViewerSession.id)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_suspected_bot == True,
            ViewerSession.is_active == True,
        )
    )
    viewers = await db.scalar(
        select(func.count(ViewerSession.id)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_active == True,
        )
    )
    avg_risk = await db.scalar(
        select(func.avg(ViewerSession.risk_score)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_active == True,
        )
    )

    return {
        "active_attacks": active_attacks or 0,
        "total_alerts": alerts or 0,
        "blocked_ips": blocked or 0,
        "suspected_bots": bots or 0,
        "live_viewers": viewers or 0,
        "risk_score_avg": float(avg_risk or 0),
        "attacks_last_24h": attacks_24h or 0,
        "mitigations_applied": mitigations or 0,
    }


async def compute_dashboard_charts(
    db: AsyncSession,
    stream_ids: List[UUID],
    hours: int = 24,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    timeline_buckets: Dict[str, Dict[str, int]] = {}
    for i in range(hours):
        bucket_time = (now - timedelta(hours=hours - 1 - i)).replace(minute=0, second=0, microsecond=0)
        timeline_buckets[_hour_label(bucket_time)] = {"attacks": 0, "mitigated": 0}

    heatmap_buckets: Dict[int, List[float]] = defaultdict(list)

    if stream_ids:
        attack_rows = await db.execute(
            select(Attack.created_at, Attack.status, Attack.mitigation_action).where(
                Attack.stream_id.in_(stream_ids),
                Attack.created_at >= since,
            )
        )
        for created_at, status, mitigation_action in attack_rows.all():
            label = _hour_label(created_at)
            if label not in timeline_buckets:
                timeline_buckets[label] = {"attacks": 0, "mitigated": 0}
            timeline_buckets[label]["attacks"] += 1
            if status == "mitigated" or mitigation_action != MitigationAction.NONE:
                timeline_buckets[label]["mitigated"] += 1

        event_rows = await db.execute(
            select(StreamEvent.created_at, StreamEvent.risk_score).where(
                StreamEvent.stream_id.in_(stream_ids),
                StreamEvent.created_at >= since,
            )
        )
        for created_at, risk_score in event_rows.all():
            heatmap_buckets[created_at.astimezone(timezone.utc).hour].append(risk_score)

    timeline = [
        {"time": label, "attacks": vals["attacks"], "mitigated": vals["mitigated"]}
        for label, vals in timeline_buckets.items()
    ]

    heatmap = []
    for hour in range(24):
        scores = heatmap_buckets.get(hour, [])
        risk = int(sum(scores) / len(scores)) if scores else 0
        heatmap.append({"hour": f"{hour:02d}h", "risk": min(risk, 100), "events": len(scores)})

    return {"timeline": timeline, "heatmap": heatmap, "updated_at": now.isoformat()}
