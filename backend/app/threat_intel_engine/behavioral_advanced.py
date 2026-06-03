"""Advanced Behavioral Analysis — Real-time pattern detection."""

from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json
import statistics

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis

logger = get_logger(__name__)
settings = get_settings()

# Window sizes for analysis
WINDOW_SIZE_SECONDS = {
    "immediate": 10,      # Real-time patterns
    "short": 60,          # 1 minute
    "medium": 300,        # 5 minutes
    "long": 900,          # 15 minutes
    "extended": 3600,     # 1 hour
}

MIN_VIEWERS_FOR_ANALYSIS = 10


class BehavioralAnalyzer:
    """Detect behavioral anomalies in real-time streaming data."""

    def __init__(self):
        self._cache = get_redis()
        self._viewer_windows: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: {w: deque(maxlen=300) for w in WINDOW_SIZE_SECONDS}
        )
        self._viewer_ips: Dict[str, Set[str]] = defaultdict(set)
        self._viewer_fingerprints: Dict[str, Set[str]] = defaultdict(set)
        self._entry_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._platform_user_ids: Dict[str, Set[str]] = defaultdict(set)

    async def record_viewer_join(
        self,
        stream_id: str,
        viewer_count: int,
        ip_address: Optional[str] = None,
        fingerprint: Optional[str] = None,
        platform_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record viewer join and analyze patterns."""
        current_time = int(__import__("time").time())

        # Record in time windows
        self._entry_times[stream_id].append(current_time)

        # Track IP/fingerprint/user uniqueness
        if ip_address:
            self._viewer_ips[stream_id].add(ip_address)
        if fingerprint:
            self._viewer_fingerprints[stream_id].add(fingerprint)
        if platform_user_id:
            self._platform_user_ids[stream_id].add(platform_user_id)

        # Analyze patterns
        patterns = await self._detect_patterns(stream_id, viewer_count)

        return patterns

    async def record_viewer_leave(self, stream_id: str) -> None:
        """Record viewer leave (for future exit analysis)."""
        pass

    async def _detect_patterns(
        self,
        stream_id: str,
        current_viewer_count: int,
    ) -> Dict[str, Any]:
        """Detect multiple behavioral patterns."""
        patterns = {
            "synchronized_entries": await self._detect_synchronized_entries(stream_id),
            "impossible_growth": await self._detect_impossible_growth(stream_id, current_viewer_count),
            "mass_entry": await self._detect_mass_entry(stream_id),
            "silent_viewers": await self._detect_silent_viewers(stream_id),
            "unique_entropy": await self._calculate_unique_entropy(stream_id),
            "entry_rate_anomaly": await self._detect_entry_rate_anomaly(stream_id),
        }

        return patterns

    async def _detect_synchronized_entries(self, stream_id: str) -> Dict[str, Any]:
        """
        Detect synchronized viewer entries.
        Multiple viewers joining within same second = suspicious.
        """
        entries = list(self._entry_times.get(stream_id, []))
        if len(entries) < 5:
            return {"detected": False, "confidence": 0}

        # Get last 10 entries
        recent_entries = entries[-10:]
        now = int(__import__("time").time())
        last_30s = [e for e in recent_entries if now - e <= 30]

        if len(last_30s) < 3:
            return {"detected": False, "confidence": 0}

        # Check if multiple entries in same second
        per_second = defaultdict(int)
        for entry_time in last_30s:
            per_second[entry_time] += 1

        max_same_second = max(per_second.values()) if per_second else 0
        
        # Check time gaps
        if len(last_30s) > 1:
            gaps = [last_30s[i + 1] - last_30s[i] for i in range(len(last_30s) - 1)]
            avg_gap = statistics.mean(gaps) if gaps else 1
            gap_variance = statistics.variance(gaps) if len(gaps) > 1 else 0

            # Synchronized = low variance (entries at similar intervals)
            synchronization_score = min(1.0, gap_variance / 10.0) if gap_variance > 0 else 1.0
        else:
            synchronization_score = 0.5

        confidence = min(1.0, (max_same_second / 3.0) * synchronization_score)

        return {
            "detected": confidence > 0.5,
            "confidence": confidence,
            "synchronized_per_second": max_same_second,
            "interval_variance": gap_variance if 'gap_variance' in locals() else 0,
        }

    async def _detect_impossible_growth(
        self,
        stream_id: str,
        current_count: int,
    ) -> Dict[str, Any]:
        """
        Detect impossible/unrealistic viewer growth.
        Viewers per second growing faster than physically possible.
        """
        entries = list(self._entry_times.get(stream_id, []))
        if len(entries) < 20:
            return {"detected": False, "confidence": 0}

        now = int(__import__("time").time())

        # Analyze growth rates in different windows
        growth_rates = []
        for window in [30, 60, 120]:  # 30s, 1m, 2m windows
            window_entries = [e for e in entries if now - e <= window]
            if len(window_entries) > 0:
                rate = len(window_entries) / window
                growth_rates.append(rate)

        if not growth_rates:
            return {"detected": False, "confidence": 0}

        avg_growth_rate = statistics.mean(growth_rates)
        max_growth_rate = max(growth_rates)

        # Impossible if growth > 50 viewers/second
        # Suspicious if > 20 viewers/second
        suspicious_threshold = 20
        impossible_threshold = 50

        if max_growth_rate > impossible_threshold:
            confidence = 1.0
        elif max_growth_rate > suspicious_threshold:
            confidence = min(1.0, (max_growth_rate - suspicious_threshold) / (impossible_threshold - suspicious_threshold))
        else:
            confidence = 0.0

        return {
            "detected": confidence > 0.3,
            "confidence": confidence,
            "growth_rate_per_second": avg_growth_rate,
            "peak_growth_rate": max_growth_rate,
        }

    async def _detect_mass_entry(self, stream_id: str) -> Dict[str, Any]:
        """
        Detect mass viewer entries.
        Large spike in viewers joining simultaneously.
        """
        entries = list(self._entry_times.get(stream_id, []))
        if len(entries) < 10:
            return {"detected": False, "confidence": 0}

        now = int(__import__("time").time())

        # Count entries in last 5 seconds
        recent_5s = [e for e in entries if now - e <= 5]
        # Count entries in 5 seconds before
        previous_5s = [e for e in entries if 10 > (now - e) > 5]

        if len(previous_5s) == 0:
            return {"detected": False, "confidence": 0}

        entry_ratio = len(recent_5s) / max(len(previous_5s), 1)

        # Spike detected if 3x or more increase
        if entry_ratio >= 3:
            confidence = min(1.0, (entry_ratio - 2) / 3)
        else:
            confidence = 0.0

        return {
            "detected": confidence > 0.4,
            "confidence": confidence,
            "recent_entries_5s": len(recent_5s),
            "previous_entries_5s": len(previous_5s),
            "spike_ratio": entry_ratio,
        }

    async def _detect_silent_viewers(self, stream_id: str) -> Dict[str, Any]:
        """
        Detect viewers that never interact (no chat, no gifts, etc).
        Bots typically don't interact.
        """
        total_ips = len(self._viewer_ips.get(stream_id, set()))
        total_fingerprints = len(self._viewer_fingerprints.get(stream_id, set()))

        # Check for viewers without platform IDs (highly suspicious)
        # These are viewers tracked only by IP/fingerprint
        unidentified_viewers = max(total_ips, total_fingerprints)

        # High ratio of unidentified viewers suggests bot activity
        if unidentified_viewers > 20:
            confidence = min(1.0, (unidentified_viewers - 20) / 100.0)
        else:
            confidence = 0.0

        return {
            "detected": confidence > 0.3,
            "confidence": confidence,
            "unidentified_viewers": unidentified_viewers,
        }

    async def _calculate_unique_entropy(self, stream_id: str) -> Dict[str, Any]:
        """
        Calculate entropy of unique viewers.
        Low entropy = same viewers repeatedly (coordinated activity).
        """
        all_ids = list(self._platform_user_ids.get(stream_id, set()))
        if len(all_ids) < 5:
            return {"entropy": 0, "uniqueness": 0, "repetition_detected": False}

        # Calculate proportion of unique IDs
        entries = len(list(self._entry_times.get(stream_id, [])))
        uniqueness = len(all_ids) / max(entries, 1) if entries > 0 else 0

        # Low uniqueness = high repetition = suspicious
        if uniqueness < 0.3:
            confidence = 1.0 - uniqueness
        else:
            confidence = 0.0

        return {
            "entropy": uniqueness,
            "uniqueness": uniqueness,
            "repetition_detected": confidence > 0.5,
            "unique_users": len(all_ids),
            "total_entries": entries,
        }

    async def _detect_entry_rate_anomaly(self, stream_id: str) -> Dict[str, Any]:
        """
        Detect abnormal entry rates over time.
        """
        entries = list(self._entry_times.get(stream_id, []))
        if len(entries) < 20:
            return {"detected": False, "confidence": 0}

        now = int(__import__("time").time())

        # Calculate rate for different windows
        rates = {}
        for window in [60, 300, 900]:  # 1m, 5m, 15m
            window_entries = [e for e in entries if now - e <= window]
            rate = len(window_entries) / (window / 60.0) if window > 0 else 0
            rates[f"rate_{window}s"] = rate

        # Detect if rates are inconsistent
        rate_values = list(rates.values())
        if len(rate_values) > 1:
            variance = statistics.variance(rate_values)
            mean_rate = statistics.mean(rate_values)

            # High variance = inconsistent = suspicious
            if mean_rate > 0:
                cv = variance / (mean_rate ** 2)  # Coefficient of variation
                confidence = min(1.0, cv / 2.0)
            else:
                confidence = 0.0
        else:
            confidence = 0.0

        return {
            "detected": confidence > 0.4,
            "confidence": confidence,
            "rates": rates,
        }

    async def get_behavioral_risk_score(self, stream_id: str) -> float:
        """
        Calculate overall behavioral risk score.
        Combines all pattern detections.
        """
        current_viewers = len(self._viewer_ips.get(stream_id, set()))
        if current_viewers < MIN_VIEWERS_FOR_ANALYSIS:
            return 0.0

        patterns = await self._detect_patterns(stream_id, current_viewers)

        # Weight each pattern
        weights = {
            "synchronized_entries": 0.25,
            "impossible_growth": 0.25,
            "mass_entry": 0.2,
            "silent_viewers": 0.15,
            "unique_entropy": 0.1,
            "entry_rate_anomaly": 0.05,
        }

        risk_score = 0.0
        for pattern_name, weight in weights.items():
            pattern_data = patterns.get(pattern_name, {})
            confidence = pattern_data.get("confidence", 0)
            risk_score += confidence * weight

        return min(1.0, risk_score)

    async def clear_stream_data(self, stream_id: str) -> None:
        """Clear accumulated data for a stream."""
        self._viewer_windows.pop(stream_id, None)
        self._viewer_ips.pop(stream_id, None)
        self._viewer_fingerprints.pop(stream_id, None)
        self._entry_times.pop(stream_id, None)
        self._platform_user_ids.pop(stream_id, None)
