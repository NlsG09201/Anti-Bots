"""Engagement health scoring and streaming intelligence metrics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Set

from app.threat_intel_engine.schemas import EngagementMetrics

MEASUREMENT_WINDOW_SECONDS = 60
MIN_VIEWER_SAMPLE = 20
LOW_COVERAGE_THRESHOLD_PERCENT = 25.0
LOW_ENGAGEMENT_THRESHOLD_PERCENT = 2.0
STALE_SAMPLE_GRACE_SECONDS = 60
STALE_SAMPLE_MAX_AGE_SECONDS = 300


@dataclass
class StreamEngagementState:
    viewer_last_seen: Dict[str, float] = field(default_factory=dict)
    suspected_viewers: Set[str] = field(default_factory=set)
    chatter_last_seen: Dict[str, float] = field(default_factory=dict)
    message_timestamps: list[float] = field(default_factory=list)
    viewer_samples: list[tuple[float, int]] = field(default_factory=list)
    last_viewer_count: int | None = None


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
        st.viewer_last_seen[user_key] = time.time()
        if suspected:
            st.suspected_viewers.add(user_key)
        if viewer_count is not None:
            now = time.time()
            st.viewer_samples.append((now, viewer_count))
            st.viewer_samples = st.viewer_samples[-120:]
            st.last_viewer_count = max(0, viewer_count)

    def record_chat(self, stream_id: str, user_key: str) -> None:
        st = self._state(stream_id)
        now = time.time()
        st.chatter_last_seen[user_key] = now
        st.message_timestamps.append(now)
        st.message_timestamps = st.message_timestamps[-600:]

    def compute(self, stream_id: str) -> EngagementMetrics:
        st = self._state(stream_id)
        now = time.time()
        window_seconds = MEASUREMENT_WINDOW_SECONDS
        window = [
            timestamp
            for timestamp in st.message_timestamps
            if now - timestamp <= window_seconds
        ]
        mpm = float(len(window))
        recent_viewers = {
            user_key
            for user_key, seen_at in st.viewer_last_seen.items()
            if now - seen_at <= window_seconds
        }
        identified_viewers = len(recent_viewers)
        viewers_total = max(st.last_viewer_count or 0, identified_viewers)
        active = sum(
            seen_at >= now - window_seconds
            for seen_at in st.chatter_last_seen.values()
        )
        unique_chat = len(st.chatter_last_seen)
        suspected = len(st.suspected_viewers.intersection(recent_viewers))
        real_est = max(0, viewers_total - suspected)
        engagement_pct = min(100.0, (active / max(viewers_total, 1)) * 100.0)
        ratio = active / max(viewers_total, 1)
        if st.last_viewer_count is not None:
            viewer_count_source = "platform"
        elif identified_viewers:
            viewer_count_source = "event_sample"
        else:
            viewer_count_source = "unavailable"
        data_coverage = (
            min(100.0, identified_viewers / st.last_viewer_count * 100.0)
            if st.last_viewer_count and st.last_viewer_count > 0
            else 0.0
        )
        sample_factor = min(identified_viewers / MIN_VIEWER_SAMPLE, 1.0)
        coverage_factor = (
            data_coverage / 100.0 if viewer_count_source == "platform" else 0.5
        )
        sample_timestamps = list(st.viewer_last_seen.values())
        if st.viewer_samples:
            sample_timestamps.append(st.viewer_samples[-1][0])
        last_sample_at = max(sample_timestamps, default=None)
        freshness_factor = (
            max(
                0.0,
                min(
                    1.0,
                    1.0
                    - max(
                        0.0,
                        now - last_sample_at - STALE_SAMPLE_GRACE_SECONDS,
                    )
                    / (STALE_SAMPLE_MAX_AGE_SECONDS - STALE_SAMPLE_GRACE_SECONDS),
                ),
            )
            if last_sample_at is not None
            else 0.0
        )
        data_quality = sample_factor * coverage_factor * freshness_factor * 100.0

        growth_anomaly = self._growth_anomaly(st)
        synthetic = self._synthetic_score(
            viewers_total, suspected, engagement_pct, mpm, ratio
        )
        health = self._health_score(
            engagement_pct, ratio, mpm, unique_chat, viewers_total, synthetic
        )
        signals = self._build_signals(
            identified_viewers=identified_viewers,
            data_coverage=data_coverage,
            viewer_count_source=viewer_count_source,
            engagement_percent=engagement_pct,
            viewers_total=viewers_total,
            growth_anomaly=growth_anomaly,
            synthetic_score=synthetic,
            data_quality_score=data_quality,
        )

        return EngagementMetrics(
            stream_id=stream_id,
            viewers_total=viewers_total,
            identified_viewers=identified_viewers,
            viewer_count_source=viewer_count_source,
            viewers_suspected=suspected,
            viewers_real_estimate=real_est,
            engagement_percent=round(engagement_pct, 2),
            active_chatters=active,
            unique_chatters=unique_chat,
            messages_per_minute=round(mpm, 2),
            viewer_to_chat_ratio=round(ratio, 4),
            measurement_window_seconds=window_seconds,
            data_coverage_percent=round(data_coverage, 2),
            data_quality_score=round(data_quality, 2),
            signals=signals,
            engagement_health_score=round(health, 2),
            growth_anomaly=growth_anomaly,
            synthetic_engagement_score=round(synthetic, 2),
        )

    @staticmethod
    def _build_signals(
        *,
        identified_viewers: int,
        data_coverage: float,
        viewer_count_source: str,
        engagement_percent: float,
        viewers_total: int,
        growth_anomaly: bool,
        synthetic_score: float,
        data_quality_score: float,
    ) -> list[str]:
        signals = [
            "Las señales son estimaciones basadas en eventos observados; no prueban viewbotting."
        ]
        if identified_viewers < MIN_VIEWER_SAMPLE:
            signals.append(
                f"Muestra pequeña: menos de {MIN_VIEWER_SAMPLE} viewers identificados."
            )
        if viewer_count_source != "platform":
            signals.append("No hay conteo de viewers de la plataforma; cobertura no calculable.")
        elif data_coverage < LOW_COVERAGE_THRESHOLD_PERCENT and viewers_total > 0:
            signals.append("Cobertura parcial: se identificó menos del 25 % del conteo reportado.")
        if (
            viewers_total > 100
            and engagement_percent < LOW_ENGAGEMENT_THRESHOLD_PERCENT
        ):
            signals.append(
                "Participación de chat baja para el volumen actual; depende del tipo de audiencia."
            )
        if growth_anomaly:
            signals.append("Cambio inusual de viewers entre muestras recientes.")
        if data_quality_score < 25.0:
            signals.append(
                "Calidad de datos baja por tamaño, cobertura o antigüedad de la muestra."
            )
        if synthetic_score > 60:
            signals.append(
                "Señal de engagement sintético elevada; requiere revisión con otras evidencias."
            )
        return signals

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
