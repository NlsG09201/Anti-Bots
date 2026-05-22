"""In-memory rolling event rates per stream (chat, follows)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple


@dataclass
class StreamRates:
    messages: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    follows: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    chatters: set[str] = field(default_factory=set)
    live_started_at: float | None = None
    peak_viewers: int = 0


class LiveIntelTracker:
    def __init__(self) -> None:
        self._streams: Dict[str, StreamRates] = {}

    def _rates(self, stream_id: str) -> StreamRates:
        if stream_id not in self._streams:
            self._streams[stream_id] = StreamRates()
        return self._streams[stream_id]

    def record_event(
        self,
        stream_id: str,
        event_type: str,
        *,
        username: str | None = None,
    ) -> None:
        now = time.time()
        st = self._rates(stream_id)
        et = (event_type or "").lower()
        if et in ("chat_message", "message", "chat"):
            st.messages.append(now)
            if username:
                st.chatters.add(username.lower())
        elif et in ("follow", "subscription"):
            st.follows.append(now)

    def mark_live(self, stream_id: str, *, viewers: int = 0) -> None:
        st = self._rates(stream_id)
        if st.live_started_at is None:
            st.live_started_at = time.time()
        st.peak_viewers = max(st.peak_viewers, viewers)

    def mark_offline(self, stream_id: str) -> None:
        self._streams.pop(stream_id, None)

    def compute_rates(self, stream_id: str, window_sec: float = 60.0) -> Dict[str, float | int]:
        st = self._rates(stream_id)
        now = time.time()
        msgs = [t for t in st.messages if now - t <= window_sec]
        flws = [t for t in st.follows if now - t <= window_sec]
        duration = 0
        if st.live_started_at:
            duration = int(now - st.live_started_at)
        return {
            "messages_per_minute": float(len(msgs)),
            "follows_per_minute": float(len(flws)),
            "active_chatters": len(st.chatters),
            "duration_seconds": duration,
            "peak_viewers": st.peak_viewers,
        }


_tracker: LiveIntelTracker | None = None


def get_live_intel_tracker() -> LiveIntelTracker:
    global _tracker
    if _tracker is None:
        _tracker = LiveIntelTracker()
    return _tracker
