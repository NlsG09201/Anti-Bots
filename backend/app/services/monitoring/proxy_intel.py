"""Recopila IPs/fingerprints de proxy asociados a un stream para mitigacion."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import StreamEvent
from app.services.viewers.session import CHAT_IP_PLACEHOLDER

PROXY_EVENT_LOOKBACK_HOURS = 24


async def collect_proxy_threats(
    db: AsyncSession,
    stream_id: UUID,
    *,
    hours: int = PROXY_EVENT_LOOKBACK_HOURS,
) -> Dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(StreamEvent).where(
            StreamEvent.stream_id == stream_id,
            StreamEvent.created_at >= since,
            or_(
                StreamEvent.is_proxy == True,
                StreamEvent.is_vpn == True,
                StreamEvent.is_tor == True,
                StreamEvent.is_datacenter == True,
            ),
        ).order_by(StreamEvent.risk_score.desc()).limit(200)
    )
    events = list(result.scalars().all())

    ips: Set[str] = set()
    fingerprints: Set[str] = set()
    usernames: Set[str] = set()
    asn_set: Set[int] = set()

    for ev in events:
        ip = (ev.ip_address or "").strip()
        if ip and ip != CHAT_IP_PLACEHOLDER:
            ips.add(ip)
        if ev.fingerprint_hash:
            fingerprints.add(ev.fingerprint_hash)
        if ev.platform_username:
            usernames.add(ev.platform_username)
        if ev.asn:
            asn_set.add(ev.asn)

    return {
        "proxy_ips": sorted(ips)[:50],
        "fingerprints": sorted(fingerprints)[:20],
        "usernames": sorted(usernames)[:30],
        "asns": sorted(asn_set)[:10],
        "event_count": len(events),
    }


def merge_attack_proxy_evidence(
    evidence: Dict[str, Any],
    proxy_intel: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(evidence)
    existing_ips = set(merged.get("proxy_ips") or [])
    existing_ips.update(proxy_intel.get("proxy_ips") or [])
    merged["proxy_ips"] = sorted(existing_ips)[:50]
    merged["proxy_event_count"] = proxy_intel.get("event_count", 0)
    if proxy_intel.get("asns"):
        merged["proxy_asns"] = proxy_intel["asns"]
    return merged
