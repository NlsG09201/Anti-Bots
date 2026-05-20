"""Real-time feature extraction for ML inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StreamFeatureVector:
    """16-dimensional feature vector for sklearn models."""

    joins_per_minute: float = 0.0
    viewer_growth_rate: float = 0.0
    follow_velocity: float = 0.0
    chat_message_rate: float = 0.0
    silent_viewer_ratio: float = 0.0
    proxy_ratio: float = 0.0
    vpn_ratio: float = 0.0
    datacenter_ratio: float = 0.0
    fingerprint_collision_ratio: float = 0.0
    session_duration_avg_sec: float = 0.0
    mouse_entropy: float = 0.5
    connection_sync_score: float = 0.0
    historical_risk_avg: float = 0.0
    cross_stream_activity: float = 0.0
    unique_ip_ratio: float = 1.0
    asn_diversity: float = 1.0

    extra: Dict[str, float] = field(default_factory=dict)

    def as_list(self) -> List[float]:
        return [
            self.joins_per_minute,
            self.viewer_growth_rate,
            self.follow_velocity,
            self.chat_message_rate,
            self.silent_viewer_ratio,
            self.proxy_ratio,
            self.vpn_ratio,
            self.datacenter_ratio,
            self.fingerprint_collision_ratio,
            self.session_duration_avg_sec,
            self.mouse_entropy,
            self.connection_sync_score,
            self.historical_risk_avg,
            self.cross_stream_activity,
            self.unique_ip_ratio,
            self.asn_diversity,
        ]

    def to_dict(self) -> Dict[str, float]:
        base = {
            "joins_per_minute": self.joins_per_minute,
            "viewer_growth_rate": self.viewer_growth_rate,
            "follow_velocity": self.follow_velocity,
            "chat_message_rate": self.chat_message_rate,
            "silent_viewer_ratio": self.silent_viewer_ratio,
            "proxy_ratio": self.proxy_ratio,
            "vpn_ratio": self.vpn_ratio,
            "datacenter_ratio": self.datacenter_ratio,
            "fingerprint_collision_ratio": self.fingerprint_collision_ratio,
            "session_duration_avg_sec": self.session_duration_avg_sec,
            "mouse_entropy": self.mouse_entropy,
            "connection_sync_score": self.connection_sync_score,
            "historical_risk_avg": self.historical_risk_avg,
            "cross_stream_activity": self.cross_stream_activity,
            "unique_ip_ratio": self.unique_ip_ratio,
            "asn_diversity": self.asn_diversity,
        }
        base.update(self.extra)
        return base


class FeatureExtractor:
    """Build feature vectors from ingest events and rolling context."""

    def extract(
        self,
        *,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_intel: Optional[Dict[str, Any]] = None,
        window_stats: Optional[Dict[str, float]] = None,
        fingerprint_risk: float = 0.0,
    ) -> StreamFeatureVector:
        meta = metadata or {}
        win = window_stats or {}
        ip = ip_intel or {}

        joins = float(meta.get("joins_per_minute", win.get("joins_per_minute", 0)))
        if event_type == "viewer_join" and joins < 1:
            joins = 1.0

        viewer_growth = float(
            meta.get("viewer_growth_rate", win.get("viewer_growth_rate", 0))
        )
        follow_vel = float(meta.get("follow_velocity", win.get("follow_velocity", 0)))
        chat_rate = float(meta.get("chat_message_rate", win.get("chat_message_rate", 0)))

        silent = float(meta.get("silent_viewer_ratio", win.get("silent_viewer_ratio", 0)))
        if silent == 0 and joins > 20 and chat_rate < 0.1:
            silent = min(1.0, 1.0 - (chat_rate / max(joins, 1)))

        proxy_r = float(meta.get("proxy_ratio", win.get("proxy_ratio", 0)))
        if ip.get("is_proxy") and proxy_r < 1:
            proxy_r = max(proxy_r, 1.0)

        vpn_r = 1.0 if ip.get("is_vpn") else float(meta.get("vpn_ratio", 0))
        dc_r = 1.0 if ip.get("is_datacenter") else float(meta.get("datacenter_ratio", 0))

        fp_coll = float(
            meta.get(
                "fingerprint_collision_ratio",
                win.get("fingerprint_collision_ratio", 0),
            )
        )
        if fingerprint_risk >= 50:
            fp_coll = max(fp_coll, 0.3)

        session_dur = float(
            meta.get("session_duration_sec", meta.get("session_duration_avg_sec", 0))
        )
        mouse_ent = float(meta.get("mouse_entropy", meta.get("pointer_entropy", 0.5)))
        sync_score = float(
            meta.get("connection_sync_score", meta.get("coordination_score", 0))
        )
        hist_risk = float(meta.get("historical_risk_avg", win.get("historical_risk_avg", 0)))
        cross = float(meta.get("cross_stream_activity", win.get("cross_stream_activity", 0)))
        unique_ip = float(meta.get("unique_ip_ratio", win.get("unique_ip_ratio", 1.0)))
        asn_div = float(meta.get("asn_diversity", win.get("asn_diversity", 1.0)))

        return StreamFeatureVector(
            joins_per_minute=joins,
            viewer_growth_rate=viewer_growth,
            follow_velocity=follow_vel,
            chat_message_rate=chat_rate,
            silent_viewer_ratio=silent,
            proxy_ratio=proxy_r,
            vpn_ratio=vpn_r,
            datacenter_ratio=dc_r,
            fingerprint_collision_ratio=fp_coll,
            session_duration_avg_sec=session_dur,
            mouse_entropy=mouse_ent,
            connection_sync_score=sync_score,
            historical_risk_avg=hist_risk,
            cross_stream_activity=cross,
            unique_ip_ratio=unique_ip,
            asn_diversity=asn_div,
        )
