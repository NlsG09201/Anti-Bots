"""Métricas de seguridad para el panel SOC (tenant + stream)."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import AlertSeverity, Attack, Stream, StreamEvent
from app.infrastructure.security.metrics_recorder import (
    BLOCK_REASONS,
    get_security_metrics_recorder,
)
from app.services.dashboard.metrics import get_tenant_stream_ids


async def compute_security_dashboard(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    stream_id: Optional[UUID] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    hours = max(1, min(hours, 72))

    if stream_id:
        stream = await db.get(Stream, stream_id)
        if not stream or stream.tenant_id != tenant_id:
            stream_ids: List[UUID] = []
        else:
            stream_ids = [stream_id]
    else:
        stream_ids = await get_tenant_stream_ids(db, tenant_id)

    recorder = get_security_metrics_recorder()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    gateway = await recorder.summary(hours, tenant_id=None)
    gateway_timeline = await recorder.timeline(
        list(BLOCK_REASONS),
        hours,
        tenant_id=None,
    )
    top_gateway_reasons = await recorder.top_block_reasons(hours, tenant_id=None)

    stream_stats = await _stream_event_security_stats(db, stream_ids, since)
    attack_stats = await _attack_security_stats(db, stream_ids, since)
    per_stream = await _per_stream_breakdown(db, stream_ids, since)

    flag_counter: Counter[str] = Counter()
    for ev in stream_stats.get("flag_samples", []):
        for f in ev:
            flag_counter[f] += 1

    timeline_events = await _events_timeline(db, stream_ids, since, hours)

    return {
        "hours": hours,
        "stream_id": str(stream_id) if stream_id else None,
        "summary": {
            "blocks_429": gateway["blocks_429"],
            "blocks_403": gateway["blocks_403"],
            "blocks_widget": gateway["blocks_widget"],
            "blocks_replay": gateway["blocks_replay"],
            "proxy_detections": stream_stats["proxy_events"],
            "vpn_detections": stream_stats["vpn_events"],
            "tor_detections": stream_stats["tor_events"],
            "datacenter_detections": stream_stats["datacenter_events"],
            "high_risk_events": stream_stats["high_risk_events"],
            "automation_signals": stream_stats["automation_events"],
            "security_attacks": attack_stats["security_related"],
            "total_events": stream_stats["total_events"],
        },
        "gateway": {
            "timeline": gateway_timeline,
            "top_reasons": top_gateway_reasons,
            **gateway,
        },
        "timeline": timeline_events,
        "top_flags": [
            {"flag": k, "count": v}
            for k, v in flag_counter.most_common(12)
        ],
        "per_stream": per_stream,
        "recent_signals": stream_stats.get("recent_signals", []),
    }


async def _stream_event_security_stats(
    db: AsyncSession,
    stream_ids: List[UUID],
    since: datetime,
) -> Dict[str, Any]:
    if not stream_ids:
        return {
            "total_events": 0,
            "proxy_events": 0,
            "vpn_events": 0,
            "tor_events": 0,
            "datacenter_events": 0,
            "high_risk_events": 0,
            "automation_events": 0,
            "flag_samples": [],
            "recent_signals": [],
        }

    base = select(StreamEvent).where(
        StreamEvent.stream_id.in_(stream_ids),
        StreamEvent.created_at >= since,
    )

    total = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
        )
    )
    proxy = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
            StreamEvent.is_proxy == True,
        )
    )
    vpn = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
            StreamEvent.is_vpn == True,
        )
    )
    tor = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
            StreamEvent.is_tor == True,
        )
    )
    dc = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
            StreamEvent.is_datacenter == True,
        )
    )
    high_risk = await db.scalar(
        select(func.count(StreamEvent.id)).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
            StreamEvent.risk_score >= 70,
        )
    )

    result = await db.execute(
        base.order_by(StreamEvent.created_at.desc()).limit(200)
    )
    events = result.scalars().all()

    automation_count = 0
    flag_samples: List[List[str]] = []
    recent_signals: List[Dict[str, Any]] = []

    for ev in events:
        meta = ev.event_metadata or {}
        flags = list(meta.get("ip_analysis", {}).get("flags", []))
        auto = meta.get("automation_flags") or []
        if auto:
            automation_count += 1
            flags.extend(auto)
        if flags:
            flag_samples.append(flags)
        if len(recent_signals) < 15 and (ev.risk_score >= 55 or ev.is_proxy or ev.is_vpn):
            recent_signals.append(
                {
                    "stream_id": str(ev.stream_id),
                    "ip_address": ev.ip_address,
                    "risk_score": ev.risk_score,
                    "is_proxy": ev.is_proxy,
                    "is_vpn": ev.is_vpn,
                    "flags": flags[:6],
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                }
            )

    return {
        "total_events": total or 0,
        "proxy_events": proxy or 0,
        "vpn_events": vpn or 0,
        "tor_events": tor or 0,
        "datacenter_events": dc or 0,
        "high_risk_events": high_risk or 0,
        "automation_events": automation_count,
        "flag_samples": flag_samples,
        "recent_signals": recent_signals,
    }


async def _attack_security_stats(
    db: AsyncSession,
    stream_ids: List[UUID],
    since: datetime,
) -> Dict[str, int]:
    if not stream_ids:
        return {"security_related": 0}

    result = await db.execute(
        select(Attack).where(
            Attack.stream_id.in_(stream_ids),
            Attack.created_at >= since,
        )
    )
    security_related = 0
    for atk in result.scalars().all():
        ev = atk.evidence or {}
        if ev.get("proxy_attack") or ev.get("bot_invasion") or atk.severity in (
            AlertSeverity.HIGH,
            AlertSeverity.CRITICAL,
        ):
            security_related += 1

    return {"security_related": security_related}


async def _per_stream_breakdown(
    db: AsyncSession,
    stream_ids: List[UUID],
    since: datetime,
) -> List[Dict[str, Any]]:
    if not stream_ids:
        return []

    breakdown: Dict[UUID, Dict[str, Any]] = defaultdict(
        lambda: {
            "events": 0,
            "proxy": 0,
            "vpn": 0,
            "high_risk": 0,
        }
    )
    result = await db.execute(
        select(StreamEvent).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
        )
    )
    for ev in result.scalars().all():
        b = breakdown[ev.stream_id]
        b["events"] += 1
        if ev.is_proxy:
            b["proxy"] += 1
        if ev.is_vpn:
            b["vpn"] += 1
        if ev.risk_score >= 70:
            b["high_risk"] += 1

    stream_names: Dict[UUID, str] = {}
    sres = await db.execute(select(Stream).where(Stream.id.in_(stream_ids)))
    for s in sres.scalars().all():
        stream_names[s.id] = s.channel_name or str(s.id)[:8]

    out = []
    for sid, stats in breakdown.items():
        out.append(
            {
                "stream_id": str(sid),
                "channel_name": stream_names.get(sid, "—"),
                **stats,
            }
        )
    out.sort(key=lambda x: x["high_risk"], reverse=True)
    return out


async def _events_timeline(
    db: AsyncSession,
    stream_ids: List[UUID],
    since: datetime,
    hours: int,
) -> List[Dict[str, Any]]:
    if not stream_ids:
        return []

    result = await db.execute(
        select(StreamEvent.created_at, StreamEvent.risk_score, StreamEvent.is_proxy).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.created_at >= since,
        )
    )
    buckets: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"events": 0, "high_risk": 0, "proxy": 0}
    )
    for created_at, risk, is_proxy in result.all():
        if not created_at:
            continue
        label = created_at.astimezone(timezone.utc).strftime("%H:00")
        buckets[label]["events"] += 1
        if risk and risk >= 70:
            buckets[label]["high_risk"] += 1
        if is_proxy:
            buckets[label]["proxy"] += 1

    now = datetime.now(timezone.utc)
    points = []
    for i in range(hours):
        dt = now - timedelta(hours=hours - 1 - i)
        label = dt.strftime("%H:00")
        b = buckets.get(label, {"events": 0, "high_risk": 0, "proxy": 0})
        points.append({"time": label, **b})
    return points
