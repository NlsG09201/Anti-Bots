"""In-process registry of per-stream health trackers."""

from __future__ import annotations

from typing import Dict, Optional

from app.services.platform_health.tracker import MonitorHealthTracker

_TRACKERS: Dict[str, MonitorHealthTracker] = {}


def get_or_create_tracker(
    stream_id: str,
    platform: str,
    channel_name: str,
    *,
    slug: str = "",
) -> MonitorHealthTracker:
    sid = str(stream_id)
    existing = _TRACKERS.get(sid)
    if existing:
        return existing
    tracker = MonitorHealthTracker(
        stream_id=sid,
        platform=platform,
        channel_name=channel_name,
        slug=slug,
    )
    _TRACKERS[sid] = tracker
    return tracker


def get_tracker(stream_id: str) -> Optional[MonitorHealthTracker]:
    return _TRACKERS.get(str(stream_id))


def drop_tracker(stream_id: str) -> None:
    _TRACKERS.pop(str(stream_id), None)


def all_trackers() -> Dict[str, MonitorHealthTracker]:
    return dict(_TRACKERS)
