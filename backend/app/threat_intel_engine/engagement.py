"""Engagement health scoring and streaming intelligence metrics."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from app.threat_intel_engine.schemas import EngagementMetrics


@dataclass
class StreamEngagementState:
    viewers: Set[str] = field(default_factory=set)
    suspected_viewers: Set[str] = field(default_factory=set)
    chatters: Set[str] = field(default_factory=set)
    message_timestamps: list[float] = field(default_factory=list)
    viewer_samples: list[tuple[float, int]] = field(default_factory=list)
    last_viewer_count: int = 0


class EngagementAnalyzer:
    """Rolling per-stream engagement metrics (in-memory + periodic persist)."""

    def __init__(self) -> None:
        self._streams: Dict[str, StreamEngagementState] = {}

    def _state(self, stream_id: str) -> StreamEngagementState:
        if stream_id not in self._streams:
            self._streams[stream_id] = StreamEngagementState()
        return self._streams[stream_id]

    def record_viewer(
        self,
        stream_id: str,
        user_key: str,
        *,
        suspected: bool = False,
        viewer_count: int | None = None,
    ) -> None:
        st = self._state(stream_id)
        st.viewers.add(user_key)
        if suspected:
            st.suspected_viewers.add(user_key)
        if viewer_count is not None:
            now = time.time()
            st.viewer_samples.append((now, viewer_count))
            st.viewer_samples = st.viewer_samples[-120:]
            st.last_viewer_count = viewer_count

    def record_chat(self, stream_id: str, user_key: str) -> None:
        st = self._state(stream_id)
        st.chatters.add(user_key)
        st.message_timestamps.append(time.time())
        st.message_timestamps = st.message_timestamps[-600:]

    def compute(self, stream_id: str) -> EngagementMetrics:
        st = self._state(stream_id)
        now = time.time()
        window = [t for t in st.message_timestamps if now - t <= 60]
        mpm = float(len(window))
        viewers_total = max(st.last_viewer_count, len(st.viewers), 1)
        active = len(st.chatters)
        unique_chat = len(st.chatters)
        suspected = len(st.suspected_viewers)
        real_est = max(0, viewers_total - suspected)
        engagement_pct = min(100.0, (active / viewers_total) * 100.0)
        ratio = active / viewers_total if viewers_total else 0.0

        growth_anomaly = self._growth_anomaly(st)
        synthetic = self._synthetic_score(
            viewers_total, suspected, engagement_pct, mpm, ratio
        )
        health = self._health_score(
            engagement_pct, ratio, mpm, unique_chat, viewers_total, synthetic
        )

        return EngagementMetrics(
            stream_id=stream_id,
            viewers_total=viewers_total,
            viewers_suspected=suspected,
            viewers_real_estimate=real_est,
            engagement_percent=round(engagement_pct, 2),
            active_chatters=active,
            unique_chatters=unique_chat,
            messages_per_minute=round(mpm, 2),
            viewer_to_chat_ratio=round(ratio, 4),
            engagement_health_score=round(health, 2),
            growth_anomaly=growth_anomaly,
            synthetic_engagement_score=round(synthetic, 2),
        )

    def _growth_anomaly(self, st: StreamEngagementState) -> bool:
        if len(st.viewer_samples) < 4:
            return False
        counts = [c for _, c in st.viewer_samples[-8:]]
        if len(counts) < 3:
            return False
        deltas = [counts[i] - counts[i - 1] for i in range(1, len(counts))]
        avg = sum(abs(d) for d in deltas) / len(deltas)
        last = abs(deltas[-1]) if deltas else 0
        return last > max(50, avg * 4)

    def _synthetic_score(
        self,
        viewers: int,
        suspected: int,
        engagement_pct: float,
        mpm: float,
        ratio: float,
    ) -> float:
        score = 0.0
        if viewers > 0:
            score += (suspected / viewers) * 45
        if engagement_pct < 2 and viewers > 100:
            score += 35
        if mpm > 200:
            score += 15
        if ratio < 0.005 and viewers > 50:
            score += 25
        return min(100.0, score)

    def _health_score(
        self,
        engagement_pct: float,
        ratio: float,
        mpm: float,
        unique_chat: int,
        viewers: int,
        synthetic: float,
    ) -> float:
        base = 50.0
        base += min(25, engagement_pct * 0.35)
        base += min(15, ratio * 100)
        base += min(10, unique_chat * 0.5)
        if mpm > 5:
            base += min(10, mpm * 0.05)
        base -= synthetic * 0.5
        if viewers > 500 and engagement_pct < 1:
            base -= 20
        return max(0.0, min(100.0, base))

    def prune(self, stream_id: str) -> None:
        self._streams.pop(stream_id, None)
