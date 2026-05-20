"""
Fuentes de entrenamiento J48:
- registered_bots: Twitch Insights + bans + fingerprints + sesiones marcadas
- channel_flow: agregación de stream_events + viewer_sessions del tenant
- mixed: combina ambas (por defecto)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.twitch.chat_filters import TWITCH_CHAT_BOTS
from app.integrations.twitchinsights.bot_database import (
    TwitchInsightsBotRecord,
    get_twitch_insights_db,
)
from app.infrastructure.database.models import Ban, Fingerprint, StreamEvent, ViewerSession
from app.ml.weka_j48.dataset import _banned_usernames, _event_stats_for_streams
from app.ml.weka_j48.features import (
    ViewerMLRow,
    aggregate_flow_to_features,
    insights_record_to_features,
    label_from_session,
    session_to_features,
)
from app.services.dashboard.metrics import get_tenant_stream_ids
from app.services.detection.viewer_bot_screening import ViewerBotScreeningService

TrainingSource = Literal["registered_bots", "channel_flow", "mixed"]


def _row_key(row: ViewerMLRow) -> str:
    uname = (row.platform_username or "").lower()
    return row.session_id or f"flow:{uname}"


def _dedupe_rows(rows: List[ViewerMLRow]) -> List[ViewerMLRow]:
    """Conserva la fila con etiqueta más fuerte por clave (sesión o usuario)."""
    by_key: Dict[str, ViewerMLRow] = {}
    for row in rows:
        key = _row_key(row)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = row
            continue
        if row.label == "yes" or (prev.label != "yes" and row.label == "no"):
            by_key[key] = row
    return list(by_key.values())


async def _load_tenant_sessions(
    db: AsyncSession,
    stream_ids: List[UUID],
    *,
    limit: int,
    include_inactive: bool = True,
) -> List[ViewerSession]:
    if not stream_ids:
        return []
    query = select(ViewerSession).where(ViewerSession.stream_id.in_(stream_ids))
    if not include_inactive:
        query = query.where(ViewerSession.is_active == True)
    query = query.order_by(ViewerSession.updated_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def _blocked_fingerprint_hashes(db: AsyncSession) -> Set[str]:
    result = await db.execute(
        select(Fingerprint.hash).where(
            (Fingerprint.is_blocked == True) | (Fingerprint.risk_score >= 75)
        )
    )
    return {row[0] for row in result.all() if row[0]}


async def _tenant_event_usernames(
    db: AsyncSession,
    stream_ids: List[UUID],
    *,
    limit: int = 50000,
) -> Dict[str, Dict[str, Any]]:
    """username_lower -> perfil agregado del flujo de eventos en canales del tenant."""
    if not stream_ids:
        return {}

    profiles: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "event_count": 0,
            "proxy": 0,
            "vpn": 0,
            "dc": 0,
            "risk_sum": 0.0,
            "streams": set(),
            "has_fingerprint": False,
        }
    )

    result = await db.execute(
        select(
            StreamEvent.platform_username,
            StreamEvent.platform_user_id,
            StreamEvent.stream_id,
            StreamEvent.is_proxy,
            StreamEvent.is_vpn,
            StreamEvent.is_datacenter,
            StreamEvent.risk_score,
            StreamEvent.fingerprint_hash,
        )
        .where(StreamEvent.stream_id.in_(stream_ids))
        .limit(limit)
    )
    for username, user_id, stream_id, is_proxy, is_vpn, is_dc, risk, fp in result.all():
        key = (username or user_id or "").lower()
        if not key:
            continue
        p = profiles[key]
        p["event_count"] += 1
        p["username"] = username or user_id
        p["streams"].add(str(stream_id))
        if is_proxy:
            p["proxy"] += 1
        if is_vpn:
            p["vpn"] += 1
        if is_dc:
            p["dc"] += 1
        p["risk_sum"] += float(risk or 0)
        if fp:
            p["has_fingerprint"] = True

    out: Dict[str, Dict[str, Any]] = {}
    for key, raw in profiles.items():
        n = max(raw["event_count"], 1)
        out[key] = {
            "username": raw.get("username") or key,
            "event_count": float(raw["event_count"]),
            "proxy_ratio": raw["proxy"] / n,
            "vpn_ratio": raw["vpn"] / n,
            "datacenter_ratio": raw["dc"] / n,
            "avg_risk": raw["risk_sum"] / n,
            "stream_count": len(raw["streams"]),
            "has_fingerprint": raw["has_fingerprint"],
        }
    return out


def _stats_from_profile(profile: Dict[str, Any]) -> Dict[str, float]:
    return {
        "event_count": profile.get("event_count", 0),
        "proxy_ratio": profile.get("proxy_ratio", 0),
        "vpn_ratio": profile.get("vpn_ratio", 0),
        "datacenter_ratio": profile.get("datacenter_ratio", 0),
    }


def _label_from_flow(
    session: Optional[ViewerSession],
    *,
    banned: Set[str],
    insights: Optional[TwitchInsightsBotRecord],
    blocked_fps: Set[str],
    screening_verdict: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    uname = ""
    if session:
        uname = (session.platform_username or session.platform_user_id or "").lower()
    elif screening_verdict:
        return "yes" if screening_verdict.get("is_malicious") else "no"

    if uname in TWITCH_CHAT_BOTS:
        return "no"
    if uname in banned:
        return "yes"
    if insights:
        return "yes"
    if session and session.fingerprint_hash and session.fingerprint_hash in blocked_fps:
        return "yes"

    if screening_verdict:
        if screening_verdict.get("is_malicious"):
            return "yes"
        src = screening_verdict.get("source", "")
        if src in ("local_db", "heuristic") and not screening_verdict.get("needs_ai"):
            return "no"

    if session:
        metrics = session.behavior_metrics or {}
        ai_v = metrics.get("ai_verdict") if isinstance(metrics, dict) else None
        if isinstance(ai_v, dict):
            if ai_v.get("is_malicious"):
                return "yes"
            if ai_v.get("source") == "twitch_insights":
                return "yes"
        return label_from_session(session)

    return None


async def load_from_channel_flow(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    limit: int = 5000,
) -> Tuple[List[ViewerMLRow], Dict[str, Any]]:
    """Etiquetas y features desde el flujo real en canales del tenant."""
    stream_ids = await get_tenant_stream_ids(db, tenant_id)
    if not stream_ids:
        return [], {"source": "channel_flow", "streams": 0}

    event_stats = await _event_stats_for_streams(db, stream_ids)
    flow_profiles = await _tenant_event_usernames(db, stream_ids)
    banned = await _banned_usernames(db, stream_ids)
    blocked_fps = await _blocked_fingerprint_hashes(db)
    sessions = await _load_tenant_sessions(db, stream_ids, limit=limit)

    insights_db = get_twitch_insights_db()
    await insights_db.ensure_loaded()
    screener = ViewerBotScreeningService()

    rows: List[ViewerMLRow] = []
    seen_users: Set[str] = set()

    for session in sessions:
        uname = (session.platform_username or session.platform_user_id or "").lower()
        if not uname:
            continue
        seen_users.add(uname)
        stats = event_stats.get(session.stream_id, {}).get(uname, {})
        profile = flow_profiles.get(uname, {})
        if not stats and profile:
            stats = _stats_from_profile(profile)

        verdict = screener._local_verdict(
            session.platform_username or uname,
            insights_db.lookup(uname),
        )
        label = _label_from_flow(
            session,
            banned=banned,
            insights=insights_db.lookup(uname),
            blocked_fps=blocked_fps,
            screening_verdict=verdict,
        )
        if label is None:
            continue

        rows.append(
            ViewerMLRow(
                features=session_to_features(session, stats),
                label=label,
                session_id=str(session.id),
                platform_username=session.platform_username,
            )
        )

    for uname, profile in flow_profiles.items():
        if uname in seen_users or len(rows) >= limit:
            break
        insights_rec = insights_db.lookup(uname)
        verdict = screener._local_verdict(profile.get("username", uname), insights_rec)
        label = _label_from_flow(
            None,
            banned=banned,
            insights=insights_rec,
            blocked_fps=blocked_fps,
            screening_verdict=verdict,
        )
        if label is None:
            continue
        rows.append(
            ViewerMLRow(
                features=aggregate_flow_to_features(
                    chat_messages=0,
                    watch_duration_seconds=int(profile.get("stream_count", 1)) * 120,
                    risk_score=float(profile.get("avg_risk", 50)),
                    has_fingerprint=bool(profile.get("has_fingerprint")),
                    event_stats=_stats_from_profile(profile),
                    username=profile.get("username", uname),
                ),
                label=label,
                session_id=None,
                platform_username=profile.get("username", uname),
            )
        )

    yes = sum(1 for r in rows if r.label == "yes")
    no = sum(1 for r in rows if r.label == "no")
    return rows[:limit], {
        "source": "channel_flow",
        "sessions": len(sessions),
        "flow_users": len(flow_profiles),
        "rows": len(rows),
        "bots": yes,
        "humans": no,
    }


async def load_from_registered_bots(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    limit: int = 8000,
    include_twitch_insights: bool = True,
) -> Tuple[List[ViewerMLRow], Dict[str, Any]]:
    """
    Entrena con bases registradas:
    - Twitch Insights (viewbots conocidos)
    - Bans activos del tenant
    - Fingerprints bloqueados / alto riesgo
    - Patrones locales (malicious_db, pattern_db)
  cruzados con sesiones/eventos del tenant cuando existen.
    """
    stream_ids = await get_tenant_stream_ids(db, tenant_id)
    banned = await _banned_usernames(db, stream_ids) if stream_ids else set()
    blocked_fps = await _blocked_fingerprint_hashes(db)
    event_stats = await _event_stats_for_streams(db, stream_ids) if stream_ids else {}
    flow_profiles = await _tenant_event_usernames(db, stream_ids) if stream_ids else {}
    sessions = await _load_tenant_sessions(db, stream_ids, limit=limit) if stream_ids else []

    session_by_user: Dict[str, ViewerSession] = {}
    for s in sessions:
        key = (s.platform_username or s.platform_user_id or "").lower()
        if key and key not in session_by_user:
            session_by_user[key] = s

    insights_db = get_twitch_insights_db()
    ti_loaded = False
    ti_size = 0
    if include_twitch_insights:
        ti_loaded = await insights_db.ensure_loaded()
        ti_size = insights_db.size

    screener = ViewerBotScreeningService()
    rows: List[ViewerMLRow] = []
    ti_matched = 0
    ban_matched = 0
    fp_matched = 0
    pattern_matched = 0

    def _append_row(
        features: List[float],
        label: str,
        *,
        session: Optional[ViewerSession],
        username: str,
    ) -> None:
        rows.append(
            ViewerMLRow(
                features=features,
                label=label,
                session_id=str(session.id) if session else None,
                platform_username=username,
            )
        )

    tenant_usernames = set(session_by_user.keys()) | set(flow_profiles.keys())

    for uname in tenant_usernames:
        if len(rows) >= limit:
            break
        session = session_by_user.get(uname)
        profile = flow_profiles.get(uname, {})
        insights_rec = insights_db.lookup(uname) if include_twitch_insights else None
        display_name = (
            (session.platform_username if session else None)
            or profile.get("username")
            or uname
        )
        verdict = screener._local_verdict(display_name, insights_rec)

        if uname in TWITCH_CHAT_BOTS:
            if session:
                stats = event_stats.get(session.stream_id, {}).get(uname, {})
                _append_row(session_to_features(session, stats), "no", session=session, username=display_name)
            continue

        label: Optional[str] = None
        if uname in banned:
            label = "yes"
            ban_matched += 1
        elif insights_rec:
            label = "yes"
            ti_matched += 1
        elif session and session.fingerprint_hash in blocked_fps:
            label = "yes"
            fp_matched += 1
        elif verdict.get("is_malicious") and verdict.get("source") in (
            "malicious_db",
            "pattern_db",
            "twitch_insights",
        ):
            label = "yes"
            if verdict.get("source") == "pattern_db":
                pattern_matched += 1
        elif session and session.is_suspected_bot:
            label = "yes"
        elif session and (session.risk_score or 0) < 30 and (session.chat_messages or 0) > 0:
            if not insights_rec and not verdict.get("is_malicious"):
                label = "no"

        if label is None:
            continue

        if session:
            stats = event_stats.get(session.stream_id, {}).get(uname, {})
            feats = session_to_features(session, stats)
        elif profile:
            feats = aggregate_flow_to_features(
                chat_messages=0,
                watch_duration_seconds=300,
                risk_score=float(profile.get("avg_risk", 70 if label == "yes" else 20)),
                has_fingerprint=bool(profile.get("has_fingerprint")),
                event_stats=_stats_from_profile(profile),
                username=display_name,
            )
        elif insights_rec:
            feats = insights_record_to_features(insights_rec)
        else:
            feats = aggregate_flow_to_features(
                risk_score=90.0 if label == "yes" else 15.0,
                username=display_name,
            )

        _append_row(feats, label, session=session, username=display_name)

    if include_twitch_insights and ti_loaded:
        extra_cap = min(2000, limit - len(rows))
        added_ti = 0
        for rec in insights_db.iter_records(limit=extra_cap * 3):
            if added_ti >= extra_cap or len(rows) >= limit:
                break
            key = rec.username.lower()
            if key in tenant_usernames or key in TWITCH_CHAT_BOTS:
                continue
            rows.append(
                ViewerMLRow(
                    features=insights_record_to_features(rec),
                    label="yes",
                    session_id=None,
                    platform_username=rec.username,
                )
            )
            added_ti += 1
        ti_matched += added_ti

    yes = sum(1 for r in rows if r.label == "yes")
    no = sum(1 for r in rows if r.label == "no")
    return _dedupe_rows(rows)[:limit], {
        "source": "registered_bots",
        "twitch_insights_loaded": ti_loaded,
        "twitch_insights_db_size": ti_size,
        "twitch_insights_matched": ti_matched,
        "bans_matched": ban_matched,
        "fingerprints_matched": fp_matched,
        "patterns_matched": pattern_matched,
        "tenant_users": len(tenant_usernames),
        "rows": len(rows),
        "bots": yes,
        "humans": no,
    }


async def build_training_dataset(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    source: TrainingSource = "mixed",
    limit: int = 5000,
    include_twitch_insights: bool = True,
) -> Tuple[List[ViewerMLRow], Dict[str, Any]]:
    if source == "channel_flow":
        rows, stats = await load_from_channel_flow(db, tenant_id, limit=limit)
        return _dedupe_rows(rows), stats

    if source == "registered_bots":
        rows, stats = await load_from_registered_bots(
            db,
            tenant_id,
            limit=limit,
            include_twitch_insights=include_twitch_insights,
        )
        return rows, stats

    reg_rows, reg_stats = await load_from_registered_bots(
        db,
        tenant_id,
        limit=limit,
        include_twitch_insights=include_twitch_insights,
    )
    flow_rows, flow_stats = await load_from_channel_flow(db, tenant_id, limit=limit)
    merged = _dedupe_rows(reg_rows + flow_rows)[:limit]
    yes = sum(1 for r in merged if r.label == "yes")
    no = sum(1 for r in merged if r.label == "no")
    return merged, {
        "source": "mixed",
        "registered": reg_stats,
        "channel_flow": flow_stats,
        "rows": len(merged),
        "bots": yes,
        "humans": no,
    }


async def preview_dataset(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    source: TrainingSource = "mixed",
    include_twitch_insights: bool = True,
) -> Dict[str, Any]:
    """Vista previa sin entrenar — cuántas muestras habría por fuente."""
    from app.core.config import get_settings

    _, stats = await build_training_dataset(
        db,
        tenant_id,
        source=source,
        limit=10000,
        include_twitch_insights=include_twitch_insights,
    )
    settings = get_settings()
    return {
        **stats,
        "min_required": settings.weka_j48_min_training_samples,
        "ready": stats.get("rows", 0) >= settings.weka_j48_min_training_samples
        and stats.get("bots", 0) >= 2
        and stats.get("humans", 0) >= 2,
    }
