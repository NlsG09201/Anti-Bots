"""Construcción de objetivos para mitigación (IPs, user_id Twitch, fingerprints)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Attack, StreamEvent, ViewerSession
from app.services.monitoring.proxy_intel import collect_proxy_threats
from app.services.viewers.session import CHAT_IP_PLACEHOLDER, is_chat_presence_session


def dedupe_targets(targets: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, str]] = []
    for t in targets:
        typ = t.get("type", "")
        val = (t.get("value") or "").strip()
        if not val:
            continue
        key = (typ, val.lower() if typ != "user" else val)
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": typ, "value": val})
    return out


def session_to_user_target(session: ViewerSession) -> Optional[Dict[str, str]]:
    """Prefiere user_id numérico de Twitch para bans en plataforma."""
    uid = (session.platform_user_id or "").strip()
    if uid.isdigit():
        return {"type": "user", "value": uid}
    login = (session.platform_username or "").strip()
    if login:
        return {"type": "user_login", "value": login}
    return None


async def build_targets_from_suspected_sessions(
    db: AsyncSession,
    stream_id: UUID,
    *,
    limit: int = 50,
    min_risk: float = 55.0,
) -> List[Dict[str, str]]:
    result = await db.execute(
        select(ViewerSession).where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.is_active == True,
            ViewerSession.is_suspected_bot == True,
        ).limit(limit)
    )
    targets: List[Dict[str, str]] = []
    for session in result.scalars().all():
        if not is_chat_presence_session(session) and session.risk_score < min_risk:
            continue
        ut = session_to_user_target(session)
        if ut:
            targets.append(ut)
        if session.ip_address and session.ip_address != CHAT_IP_PLACEHOLDER:
            targets.append({"type": "ip", "value": session.ip_address})
        if session.fingerprint_hash:
            targets.append({"type": "fingerprint", "value": session.fingerprint_hash})
    return dedupe_targets(targets)


async def build_mitigation_targets_from_attack(
    db: AsyncSession,
    attack: Attack,
    *,
    include_suspected_sessions: bool = True,
    max_targets: int = 80,
) -> List[Dict[str, str]]:
    evidence = attack.evidence or {}
    targets: List[Dict[str, str]] = []

    for ip in attack.source_ips or []:
        if ip and str(ip).strip() and str(ip) != CHAT_IP_PLACEHOLDER:
            targets.append({"type": "ip", "value": str(ip).strip()})

    for ip in evidence.get("proxy_ips") or []:
        if ip:
            targets.append({"type": "ip", "value": str(ip).strip()})

    for fp in attack.fingerprints or []:
        if fp:
            targets.append({"type": "fingerprint", "value": str(fp).strip()})
    for fp in evidence.get("fingerprints") or []:
        if fp:
            targets.append({"type": "fingerprint", "value": str(fp).strip()})

    for entry in evidence.get("suspected_sessions") or []:
        if isinstance(entry, dict):
            uid = str(entry.get("user_id") or "").strip()
            login = str(entry.get("username") or "").strip()
            if uid.isdigit():
                targets.append({"type": "user", "value": uid})
            elif login:
                targets.append({"type": "user_login", "value": login})
            ip = entry.get("ip")
            if ip and ip != CHAT_IP_PLACEHOLDER:
                targets.append({"type": "ip", "value": str(ip)})

    for name in evidence.get("suspected_usernames") or []:
        if name:
            targets.append({"type": "user_login", "value": str(name).strip()})

    proxy_intel = await collect_proxy_threats(db, attack.stream_id)
    for ip in proxy_intel.get("proxy_ips", []):
        targets.append({"type": "ip", "value": ip})
    for fp in proxy_intel.get("fingerprints", []):
        targets.append({"type": "fingerprint", "value": fp})
    for asn in proxy_intel.get("asns", []):
        targets.append({"type": "asn", "value": str(asn)})

    if include_suspected_sessions:
        targets.extend(
            await build_targets_from_suspected_sessions(db, attack.stream_id, limit=40)
        )

    return dedupe_targets(targets)[:max_targets]


async def build_targets_from_recent_events(
    db: AsyncSession,
    stream_id: UUID,
    *,
    limit: int = 80,
    min_risk: float = 45.0,
) -> List[Dict[str, str]]:
    """Fallback: IPs/usuarios de eventos recientes del canal."""
    result = await db.execute(
        select(StreamEvent)
        .where(
            StreamEvent.stream_id == stream_id,
            StreamEvent.risk_score >= min_risk,
        )
        .order_by(StreamEvent.created_at.desc())
        .limit(limit)
    )
    targets: List[Dict[str, str]] = []
    for ev in result.scalars().all():
        if ev.ip_address and ev.ip_address != CHAT_IP_PLACEHOLDER:
            if ev.is_proxy or ev.is_vpn or ev.is_datacenter or ev.risk_score >= 60:
                targets.append({"type": "ip", "value": ev.ip_address.strip()})
        if ev.fingerprint_hash:
            targets.append({"type": "fingerprint", "value": ev.fingerprint_hash.strip()})
        uid = (ev.platform_user_id or "").strip()
        login = (ev.platform_username or "").strip()
        if uid.isdigit():
            targets.append({"type": "user", "value": uid})
        elif login:
            targets.append({"type": "user_login", "value": login})
    return dedupe_targets(targets)


async def suspected_sessions_snapshot(
    db: AsyncSession,
    stream_id: UUID,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    result = await db.execute(
        select(ViewerSession).where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.is_active == True,
            ViewerSession.is_suspected_bot == True,
        ).order_by(ViewerSession.risk_score.desc())
        .limit(limit)
    )
    rows: List[Dict[str, Any]] = []
    for s in result.scalars().all():
        verdict = (s.behavior_metrics or {}).get("ai_verdict") or {}
        rows.append({
            "username": s.platform_username,
            "user_id": s.platform_user_id,
            "risk_score": s.risk_score,
            "source": verdict.get("source"),
            "ip": s.ip_address if s.ip_address != CHAT_IP_PLACEHOLDER else None,
        })
    return rows
