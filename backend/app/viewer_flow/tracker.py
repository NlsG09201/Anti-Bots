"""In-memory per-stream viewer flow state (Render-safe, bounded memory)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from app.viewer_flow.schemas import FlowEventKind, PlatformName, ViewerFlowTimelinePoint


@dataclass
class EntityFlowState:
    username: str
    platform_user_id: Optional[str] = None
    first_seen: float = 0.0
    last_seen: float = 0.0
    message_count: int = 0
    follow_count: int = 0
    gift_count: int = 0
    join_signals: int = 0
    risk_hints: List[str] = field(default_factory=list)

    @property
    def is_silent(self) -> bool:
        age = time.monotonic() - self.first_seen
        return age > 45 and self.message_count == 0 and self.follow_count == 0


@dataclass
class StreamFlowState:
    stream_id: str
    tenant_id: str
    platform: PlatformName
    channel_name: str
    is_live: bool = False
    viewers_current: int = 0
    last_viewer_count: int = 0
    viewer_samples: Deque[Tuple[float, int]] = field(
        default_factory=lambda: deque(maxlen=120)
    )
    message_times: Deque[float] = field(default_factory=lambda: deque(maxlen=800))
    follow_times: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    gift_times: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    timeline: Deque[ViewerFlowTimelinePoint] = field(
        default_factory=lambda: deque(maxlen=80)
    )
    entities: Dict[str, EntityFlowState] = field(default_factory=dict)
    chatter_usernames: Set[str] = field(default_factory=set)
    raid_burst_times: Deque[float] = field(default_factory=lambda: deque(maxlen=20))
    spike_times: Deque[float] = field(default_factory=lambda: deque(maxlen=20))
    viewers_new_total: int = 0
    viewers_lost_total: int = 0

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _push_timeline(
        self,
        kind: FlowEventKind,
        label: str,
        *,
        value: float = 0.0,
        username: Optional[str] = None,
        severity: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.timeline.append(
            ViewerFlowTimelinePoint(
                ts=self._now_iso(),
                kind=kind,
                label=label,
                value=value,
                username=username,
                severity=severity,
                metadata=metadata or {},
            )
        )

    def record_pulse(self, viewer_count: int, is_live: bool) -> None:
        now = time.monotonic()
        prev = self.viewers_current
        self.viewers_current = viewer_count
        self.is_live = is_live
        self.viewer_samples.append((now, viewer_count))
        delta = viewer_count - prev
        if prev > 0 and delta > 0:
            self.viewers_new_total += delta
            if delta >= max(25, int(prev * 0.35)):
                self.spike_times.append(now)
                self._push_timeline(
                    "spike",
                    f"Pico +{delta} viewers",
                    value=float(delta),
                    severity="high",
                    metadata={"from": prev, "to": viewer_count},
                )
                if delta >= max(50, int(prev * 0.5)):
                    self.raid_burst_times.append(now)
                    self._push_timeline(
                        "raid_suspected",
                        f"Posible raid (+{delta})",
                        value=float(delta),
                        severity="critical",
                    )
        elif prev > 0 and delta < 0:
            lost = abs(delta)
            self.viewers_lost_total += lost
            self._push_timeline(
                "viewer_leave",
                f"Salida ~{lost} viewers",
                value=float(lost),
                severity="low",
            )
        self.last_viewer_count = viewer_count
        self._push_timeline(
            "viewer_pulse",
            f"{viewer_count} viewers",
            value=float(viewer_count),
            severity="info",
        )

    def record_entity_event(
        self,
        event_type: str,
        *,
        username: Optional[str],
        platform_user_id: Optional[str] = None,
    ) -> None:
        if not username:
            return
        key = username.lower().strip()
        now = time.monotonic()
        ent = self.entities.get(key)
        if not ent:
            ent = EntityFlowState(
                username=username,
                platform_user_id=platform_user_id,
                first_seen=now,
            )
            self.entities[key] = ent
            self._push_timeline(
                "viewer_join",
                f"@{username} en flujo",
                username=username,
                severity="info",
            )
        ent.last_seen = now
        if platform_user_id:
            ent.platform_user_id = platform_user_id
        et = event_type.lower()
        if et in ("chat_message", "message", "chat", "comment"):
            ent.message_count += 1
            self.message_times.append(now)
            self.chatter_usernames.add(key)
            self._push_timeline("chat", username, username=username, severity="info")
        elif et in ("follow", "subscription"):
            ent.follow_count += 1
            self.follow_times.append(now)
            self._push_timeline("follow", f"follow @{username}", username=username)
        elif et in ("gift",):
            ent.gift_count += 1
            self.gift_times.append(now)
            self._push_timeline("gift", f"gift @{username}", username=username)
        elif et in ("viewer_join", "join"):
            ent.join_signals += 1

    def rates_in_window(self, window_sec: float = 60.0) -> Dict[str, float]:
        now = time.monotonic()
        msgs = sum(1 for t in self.message_times if now - t <= window_sec)
        flws = sum(1 for t in self.follow_times if now - t <= window_sec)
        gifts = sum(1 for t in self.gift_times if now - t <= window_sec)
        samples = [(t, c) for t, c in self.viewer_samples if now - t <= window_sec]
        vpm = 0.0
        if len(samples) >= 2:
            t0, c0 = samples[0]
            t1, c1 = samples[-1]
            dt = t1 - t0
            if dt > 0:
                vpm = abs(c1 - c0) / (dt / 60.0)
        return {
            "messages_per_minute": float(msgs),
            "follows_per_minute": float(flws),
            "gifts_per_minute": float(gifts),
            "viewers_per_minute": vpm,
            "active_chatters": float(len(self.chatter_usernames)),
        }

    def mark_offline(self) -> None:
        self.is_live = False
        self._push_timeline("offline", "Stream offline", severity="medium")


class ViewerFlowTracker:
    MAX_STREAMS = 40

    def __init__(self) -> None:
        self._streams: Dict[str, StreamFlowState] = {}

    def get_or_create(
        self,
        stream_id: str,
        tenant_id: str,
        platform: PlatformName,
        channel_name: str,
    ) -> StreamFlowState:
        sid = str(stream_id)
        if sid not in self._streams:
            if len(self._streams) >= self.MAX_STREAMS:
                oldest = min(
                    self._streams.values(),
                    key=lambda s: s.viewer_samples[-1][0] if s.viewer_samples else 0,
                )
                self._streams.pop(oldest.stream_id, None)
            self._streams[sid] = StreamFlowState(
                stream_id=sid,
                tenant_id=tenant_id,
                platform=platform,
                channel_name=channel_name,
            )
        return self._streams[sid]

    def get(self, stream_id: str) -> Optional[StreamFlowState]:
        return self._streams.get(str(stream_id))

    def remove(self, stream_id: str) -> None:
        self._streams.pop(str(stream_id), None)

    def all_for_tenant(self, tenant_id: str) -> List[StreamFlowState]:
        tid = str(tenant_id)
        return [s for s in self._streams.values() if s.tenant_id == tid]

    def all_states(self) -> List[StreamFlowState]:
        return list(self._streams.values())


_tracker: Optional[ViewerFlowTracker] = None


def get_viewer_flow_tracker() -> ViewerFlowTracker:
    global _tracker
    if _tracker is None:
        _tracker = ViewerFlowTracker()
    return _tracker
