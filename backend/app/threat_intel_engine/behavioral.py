"""Real-time behavioral anomaly scoring for streaming events."""

from __future__ import annotations

import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler


WINDOW_SECONDS = 300
MAX_EVENTS_PER_STREAM = 750


@dataclass
class BehavioralEvent:
    timestamp: float
    entity_key: str
    event_type: str
    features: List[float]
    ip_hash: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    asn: Optional[int] = None
    silent: bool = False


@dataclass
class BehavioralAssessment:
    anomaly_score: float = 0.0
    dbscan_noise_score: float = 0.0
    lof_score: float = 0.0
    sync_score: float = 0.0
    follow_coordination_score: float = 0.0
    synthetic_audience_score: float = 0.0
    bot_probability: float = 0.0
    raid_probability: float = 0.0
    trust_score: float = 100.0
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_score": round(self.anomaly_score, 4),
            "dbscan_noise_score": round(self.dbscan_noise_score, 4),
            "lof_score": round(self.lof_score, 4),
            "sync_score": round(self.sync_score, 4),
            "follow_coordination_score": round(self.follow_coordination_score, 4),
            "synthetic_audience_score": round(self.synthetic_audience_score, 4),
            "bot_probability": round(self.bot_probability, 4),
            "raid_probability": round(self.raid_probability, 4),
            "trust_score": round(self.trust_score, 2),
            "flags": self.flags,
        }


class BehavioralAnomalyEngine:
    """Runs bounded unsupervised scoring over recent stream activity."""

    def __init__(self) -> None:
        self._events: Dict[str, Deque[BehavioralEvent]] = defaultdict(
            lambda: deque(maxlen=MAX_EVENTS_PER_STREAM)
        )

    def record_event(
        self,
        stream_id: str,
        entity_key: str,
        event_type: str,
        metadata: Dict[str, Any],
        *,
        network_reputation: Optional[Dict[str, Any]] = None,
    ) -> BehavioralAssessment:
        now = time.time()
        network = network_reputation or {}
        event = BehavioralEvent(
            timestamp=now,
            entity_key=entity_key,
            event_type=(event_type or "").lower(),
            features=self._features(metadata, network),
            ip_hash=metadata.get("ip_hash"),
            fingerprint_hash=metadata.get("fingerprint_hash")
            or metadata.get("fingerprint"),
            asn=((network.get("asn") or {}).get("number") if isinstance(network.get("asn"), dict) else None),
            silent=bool(metadata.get("silent_viewer"))
            or (event_type == "viewer_join" and float(metadata.get("chat_message_rate", 0) or 0) == 0),
        )

        bucket = self._events[stream_id]
        bucket.append(event)
        self._prune(bucket, now)
        return self.assess(stream_id, entity_key)

    def assess(self, stream_id: str, entity_key: Optional[str] = None) -> BehavioralAssessment:
        events = list(self._events.get(stream_id, ()))
        if not events:
            return BehavioralAssessment()

        focus = [e for e in events if entity_key is None or e.entity_key == entity_key]
        if not focus:
            focus = events[-1:]

        matrix = np.array([e.features for e in events], dtype=float)
        iso_score = self._isolation_score(matrix, focus, events)
        lof_score = self._lof_score(matrix, focus, events)
        dbscan_noise = self._dbscan_noise_score(matrix, focus, events)
        sync = self._sync_score(events)
        follow_coord = self._follow_coordination(events)
        synthetic = self._synthetic_audience(events)

        bot_p = min(
            1.0,
            iso_score * 0.28
            + lof_score * 0.2
            + dbscan_noise * 0.16
            + sync * 0.18
            + synthetic * 0.18,
        )
        raid_p = min(1.0, sync * 0.35 + follow_coord * 0.35 + self._burst_score(events) * 0.3)
        trust = max(0.0, 100.0 - bot_p * 55 - raid_p * 25 - synthetic * 20)

        flags: List[str] = []
        if iso_score >= 0.65:
            flags.append("isolation_forest_anomaly")
        if lof_score >= 0.65:
            flags.append("lof_outlier")
        if dbscan_noise >= 0.6:
            flags.append("dbscan_noise_cluster")
        if sync >= 0.55:
            flags.append("synchronized_viewers")
        if follow_coord >= 0.55:
            flags.append("coordinated_follows")
        if synthetic >= 0.55:
            flags.append("synthetic_audience")

        return BehavioralAssessment(
            anomaly_score=iso_score,
            dbscan_noise_score=dbscan_noise,
            lof_score=lof_score,
            sync_score=sync,
            follow_coordination_score=follow_coord,
            synthetic_audience_score=synthetic,
            bot_probability=bot_p,
            raid_probability=raid_p,
            trust_score=trust,
            flags=flags,
        )

    def _features(self, metadata: Dict[str, Any], network: Dict[str, Any]) -> List[float]:
        return [
            float(metadata.get("joins_per_minute", 0) or 0),
            float(metadata.get("viewer_growth_rate", 0) or 0),
            float(metadata.get("follow_velocity", 0) or 0),
            float(metadata.get("chat_message_rate", 0) or 0),
            float(metadata.get("silent_viewer_ratio", 0) or 0),
            float(metadata.get("connection_sync_score", metadata.get("coordination_score", 0)) or 0),
            float(metadata.get("fingerprint_collision_ratio", 0) or 0),
            float(network.get("risk_score", metadata.get("risk_score", 0)) or 0) / 100.0,
            1.0 if network.get("is_vpn") else 0.0,
            1.0 if network.get("is_proxy") else 0.0,
            1.0 if network.get("is_datacenter") else 0.0,
            1.0 if network.get("is_tor") else 0.0,
        ]

    def _isolation_score(
        self, matrix: np.ndarray, focus: List[BehavioralEvent], events: List[BehavioralEvent]
    ) -> float:
        if len(events) < 12:
            return self._heuristic_anomaly(focus[-1].features)
        X = StandardScaler().fit_transform(matrix)
        model = IsolationForest(n_estimators=80, contamination="auto", random_state=42)
        model.fit(X)
        raw = -model.decision_function(X)
        return self._focused_scaled(raw, focus, events)

    def _lof_score(
        self, matrix: np.ndarray, focus: List[BehavioralEvent], events: List[BehavioralEvent]
    ) -> float:
        if len(events) < 10:
            return 0.0
        neighbors = max(5, min(20, len(events) - 1))
        X = StandardScaler().fit_transform(matrix)
        model = LocalOutlierFactor(n_neighbors=neighbors, contamination="auto")
        model.fit_predict(X)
        raw = -model.negative_outlier_factor_
        return self._focused_scaled(raw, focus, events)

    def _dbscan_noise_score(
        self, matrix: np.ndarray, focus: List[BehavioralEvent], events: List[BehavioralEvent]
    ) -> float:
        if len(events) < 8:
            return 0.0
        X = StandardScaler().fit_transform(matrix)
        labels = DBSCAN(eps=1.15, min_samples=4).fit_predict(X)
        focus_ids = {id(e) for e in focus}
        focus_labels = [labels[i] for i, e in enumerate(events) if id(e) in focus_ids]
        if not focus_labels:
            return 0.0
        return sum(1 for label in focus_labels if label == -1) / len(focus_labels)

    def _focused_scaled(
        self, raw: Iterable[float], focus: List[BehavioralEvent], events: List[BehavioralEvent]
    ) -> float:
        values = list(float(v) for v in raw)
        if not values:
            return 0.0
        lo, hi = min(values), max(values)
        if hi <= lo:
            return 0.0
        focus_ids = {id(e) for e in focus}
        selected = [
            (values[i] - lo) / (hi - lo)
            for i, event in enumerate(events)
            if id(event) in focus_ids
        ]
        return max(selected) if selected else 0.0

    def _heuristic_anomaly(self, features: List[float]) -> float:
        joins, growth, follow, chat, silent, sync, fp, risk, vpn, proxy, dc, tor = features
        score = 0.0
        score += min(0.3, joins / 600)
        score += min(0.18, growth * 0.18)
        score += min(0.15, follow / 120)
        score += min(0.12, max(0, silent - 0.55) * 0.3)
        score += min(0.15, sync * 0.15)
        score += min(0.1, fp * 0.1)
        score += min(0.2, risk * 0.2)
        score += 0.04 * (vpn + proxy + dc + tor)
        if chat > 250:
            score += 0.08
        return min(1.0, score)

    def _sync_score(self, events: List[BehavioralEvent]) -> float:
        joins = [e for e in events if e.event_type in {"viewer_join", "join", "viewer", "presence"}]
        if len(joins) < 5:
            return 0.0
        buckets = Counter(int(e.timestamp // 5) for e in joins)
        densest = max(buckets.values(), default=0)
        fp_collisions = self._collision_ratio(e.fingerprint_hash for e in joins)
        ip_collisions = self._collision_ratio(e.ip_hash for e in joins)
        return min(1.0, densest / max(len(joins), 1) * 0.65 + max(fp_collisions, ip_collisions) * 0.35)

    def _follow_coordination(self, events: List[BehavioralEvent]) -> float:
        follows = [e for e in events if e.event_type in {"follow", "subscription", "gift"}]
        if len(follows) < 4:
            return 0.0
        buckets = Counter(int(e.timestamp // 10) for e in follows)
        return min(1.0, max(buckets.values(), default=0) / max(len(follows), 1))

    def _synthetic_audience(self, events: List[BehavioralEvent]) -> float:
        viewers = [e for e in events if e.event_type in {"viewer_join", "join", "viewer", "presence"}]
        if len(viewers) < 8:
            return 0.0
        silent_ratio = sum(1 for e in viewers if e.silent) / len(viewers)
        network_ratio = sum(1 for e in viewers if max(e.features[8:12]) > 0) / len(viewers)
        fp_collisions = self._collision_ratio(e.fingerprint_hash for e in viewers)
        return min(1.0, silent_ratio * 0.45 + network_ratio * 0.35 + fp_collisions * 0.2)

    def _burst_score(self, events: List[BehavioralEvent]) -> float:
        if len(events) < 6:
            return 0.0
        buckets = Counter(int(e.timestamp // 10) for e in events)
        return min(1.0, max(buckets.values(), default=0) / max(len(events), 1))

    def _collision_ratio(self, values: Iterable[Optional[str]]) -> float:
        filtered = [v for v in values if v]
        if len(filtered) < 3:
            return 0.0
        counts = Counter(filtered)
        repeated = sum(c for c in counts.values() if c > 1)
        return repeated / len(filtered)

    def _prune(self, bucket: Deque[BehavioralEvent], now: float) -> None:
        while bucket and now - bucket[0].timestamp > WINDOW_SECONDS:
            bucket.popleft()
