"""Per-stream health metrics for Kick / YouTube / TikTok monitors."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Deque, List, Optional, Tuple

from app.services.platform_health.schemas import StreamMonitorHealth


class MonitorHealthTracker:
    CHAT_EVENTS = frozenset(
        {
            "chat_message",
            "message",
            "comment",
            "gift",
            "follow",
            "share",
            "viewer_join",
            "like",
        }
    )

    def __init__(
        self,
        stream_id: str,
        platform: str,
        channel_name: str,
        *,
        slug: str = "",
    ) -> None:
        self.stream_id = stream_id
        self.platform = platform.lower()
        self.channel_name = channel_name
        self.slug = slug
        self._started_at = time.monotonic()
        self._last_poll_at: Optional[float] = None
        self._last_event_at: Optional[float] = None
        self._last_chat_at: Optional[float] = None
        self._viewer_count = 0
        self._is_live = False
        self._poll_latency_ms: Optional[float] = None
        self._socket_connected = False
        self._socket_transport = ""
        self._reconnect_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None
        self._events_total = 0
        self._chat_events_1h = 0
        self._chat_timestamps: Deque[float] = deque(maxlen=500)
        self._viewer_samples: Deque[Tuple[float, int]] = deque(maxlen=12)
        self._frozen_polls = 0
        self._last_viewer_for_freeze: Optional[int] = None

    def record_poll(
        self,
        *,
        viewer_count: int,
        is_live: bool,
        latency_ms: Optional[float] = None,
    ) -> None:
        now = time.monotonic()
        self._last_poll_at = now
        self._viewer_count = viewer_count
        self._is_live = is_live
        if latency_ms is not None:
            self._poll_latency_ms = latency_ms
        self._viewer_samples.append((now, viewer_count))
        if (
            is_live
            and self._last_viewer_for_freeze is not None
            and viewer_count == self._last_viewer_for_freeze
        ):
            self._frozen_polls += 1
        else:
            self._frozen_polls = 0
        self._last_viewer_for_freeze = viewer_count

    def record_event(self, event_type: str) -> None:
        now = time.monotonic()
        self._last_event_at = now
        self._events_total += 1
        et = (event_type or "").lower()
        if et in self.CHAT_EVENTS or "chat" in et or "message" in et:
            self._last_chat_at = now
            self._chat_timestamps.append(now)
            self._chat_events_1h += 1

    def record_socket(self, connected: bool, transport: str = "") -> None:
        self._socket_connected = connected
        if transport:
            self._socket_transport = transport

    def record_reconnect(self) -> None:
        self._reconnect_count += 1

    def record_error(self, message: str) -> None:
        self._error_count += 1
        self._last_error = (message or "")[:300]

    def _messages_per_min(self) -> float:
        cutoff = time.monotonic() - 60.0
        while self._chat_timestamps and self._chat_timestamps[0] < cutoff:
            self._chat_timestamps.popleft()
        return float(len(self._chat_timestamps))

    def _viewers_per_min(self) -> float:
        if len(self._viewer_samples) < 2:
            return 0.0
        oldest_t, oldest_v = self._viewer_samples[0]
        newest_t, newest_v = self._viewer_samples[-1]
        dt = newest_t - oldest_t
        if dt <= 0:
            return 0.0
        return abs(newest_v - oldest_v) / (dt / 60.0)

    def _iso(self, mono: Optional[float]) -> Optional[str]:
        if mono is None:
            return None
        return datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - (time.monotonic() - mono),
            tz=timezone.utc,
        ).isoformat()

    def compute_ai_flags(self) -> Tuple[float, List[str]]:
        flags: List[str] = []
        score = 0.0
        now = time.monotonic()
        if self._is_live and self._last_poll_at and now - self._last_poll_at > 90:
            flags.append("stale_poll")
            score += 35.0
        if (
            self._is_live
            and self._socket_transport
            and not self._socket_connected
        ):
            flags.append("socket_down")
            score += 40.0
        if self._frozen_polls >= 4 and self._is_live:
            flags.append("frozen_viewers")
            score += 25.0
        if self._reconnect_count >= 8:
            flags.append("excessive_reconnects")
            score += 20.0
        if self._error_count >= 5:
            flags.append("high_errors")
            score += 15.0
        if (
            self._is_live
            and self._last_chat_at
            and now - self._last_chat_at > 180
            and self._socket_transport in ("pusher", "webcast")
        ):
            flags.append("stale_chat")
            score += 20.0
        return min(100.0, score), flags

    def to_snapshot(self, *, status: str = "unknown") -> StreamMonitorHealth:
        ai_score, ai_flags = self.compute_ai_flags()
        return StreamMonitorHealth(
            stream_id=self.stream_id,
            platform=self.platform,  # type: ignore[arg-type]
            channel_name=self.channel_name,
            slug=self.slug,
            status=status,  # type: ignore[arg-type]
            is_live=self._is_live,
            viewer_count=self._viewer_count,
            messages_per_min=round(self._messages_per_min(), 2),
            viewers_per_min=round(self._viewers_per_min(), 2),
            events_total=self._events_total,
            chat_events_1h=self._chat_events_1h,
            last_poll_at=self._iso(self._last_poll_at),
            last_event_at=self._iso(self._last_event_at),
            last_chat_at=self._iso(self._last_chat_at),
            poll_latency_ms=self._poll_latency_ms,
            socket_connected=self._socket_connected,
            socket_transport=self._socket_transport,
            reconnect_count=self._reconnect_count,
            error_count=self._error_count,
            last_error=self._last_error,
            frozen_viewer_polls=self._frozen_polls,
            ai_anomaly_score=ai_score,
            ai_flags=ai_flags,
            uptime_seconds=round(time.monotonic() - self._started_at, 1),
        )
