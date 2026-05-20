"""Consultas de fingerprints por tenant y canal."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Fingerprint, Stream, StreamEvent, ViewerSession
from app.services.dashboard.metrics import get_tenant_stream_ids


async def list_tenant_fingerprints(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    stream_id: Optional[UUID] = None,
    q: Optional[str] = None,
    min_risk: float = 0.0,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Fingerprints vistos en eventos o sesiones de viewers del tenant.
    Opcionalmente filtra por canal y búsqueda parcial de hash.
    """
    stream_ids = await get_tenant_stream_ids(db, tenant_id)
    if not stream_ids:
        return {"fingerprints": [], "count": 0}

    if stream_id:
        if stream_id not in stream_ids:
            return {"fingerprints": [], "count": 0}
        stream_ids = [stream_id]

    hash_streams: Dict[str, Set[UUID]] = defaultdict(set)
    hash_event_counts: Dict[str, int] = defaultdict(int)

    ev_result = await db.execute(
        select(StreamEvent.fingerprint_hash, StreamEvent.stream_id).where(
            StreamEvent.stream_id.in_(stream_ids),
            StreamEvent.fingerprint_hash.isnot(None),
            StreamEvent.fingerprint_hash != "",
        )
    )
    for fp_hash, sid in ev_result.all():
        hash_streams[fp_hash].add(sid)
        hash_event_counts[fp_hash] += 1

    vs_result = await db.execute(
        select(ViewerSession.fingerprint_hash, ViewerSession.stream_id).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.fingerprint_hash.isnot(None),
            ViewerSession.fingerprint_hash != "",
        )
    )
    for fp_hash, sid in vs_result.all():
        hash_streams[fp_hash].add(sid)

    if not hash_streams:
        return {"fingerprints": [], "count": 0}

    q_norm = (q or "").strip().lower()
    if q_norm:
        hash_streams = {
            h: sids for h, sids in hash_streams.items() if q_norm in h.lower()
        }
    if not hash_streams:
        return {"fingerprints": [], "count": 0}

    all_hashes = list(hash_streams.keys())
    fp_result = await db.execute(
        select(Fingerprint).where(Fingerprint.hash.in_(all_hashes))
    )
    fp_by_hash: Dict[str, Fingerprint] = {
        fp.hash: fp for fp in fp_result.scalars().all()
    }

    all_stream_ids: Set[UUID] = set()
    for sids in hash_streams.values():
        all_stream_ids.update(sids)

    names_result = await db.execute(
        select(Stream.id, Stream.channel_name, Stream.platform).where(
            Stream.id.in_(list(all_stream_ids))
        )
    )
    stream_meta = {
        row[0]: {"channel_name": row[1], "platform": row[2].value if row[2] else "twitch"}
        for row in names_result.all()
    }

    rows: List[Dict[str, Any]] = []
    for fp_hash, sids in hash_streams.items():
        fp = fp_by_hash.get(fp_hash)
        risk = fp.risk_score if fp else 0.0
        if risk < min_risk and not fp:
            risk = 50.0 if hash_event_counts.get(fp_hash, 0) > 0 else 0.0
        if risk < min_risk:
            continue

        channels = []
        for sid in sorted(sids, key=str):
            meta = stream_meta.get(sid, {})
            channels.append(
                {
                    "stream_id": str(sid),
                    "channel_name": meta.get("channel_name", "Unknown"),
                    "platform": meta.get("platform", "twitch"),
                }
            )

        rows.append(
            {
                "hash": fp_hash,
                "risk_score": risk,
                "is_headless": fp.is_headless if fp else False,
                "is_blocked": fp.is_blocked if fp else False,
                "occurrence_count": fp.occurrence_count if fp else hash_event_counts.get(fp_hash, 1),
                "automation_flags": list(fp.automation_flags or []) if fp else [],
                "event_count": hash_event_counts.get(fp_hash, 0),
                "channels": channels,
                "channel_count": len(channels),
            }
        )

    rows.sort(key=lambda r: (-r["risk_score"], -r["event_count"], r["hash"]))
    rows = rows[: max(1, min(limit, 500))]

    return {"fingerprints": rows, "count": len(rows)}
