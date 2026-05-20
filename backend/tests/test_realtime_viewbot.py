"""Tests del motor de detección de viewbots en tiempo real."""

from datetime import datetime, timezone, timedelta

import pytest

from app.services.detection.realtime_viewbot import RealtimeViewbotEngine


def _join_event(offset_sec: int, **extra) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=offset_sec)
    base = {
        "ts": ts.isoformat(),
        "event_type": "viewer_join",
        "ip_address": extra.get("ip_address", "1.2.3.4"),
        "fingerprint_hash": extra.get("fingerprint_hash", "fp_a"),
        "chat_messages": 0,
        "is_proxy": extra.get("is_proxy", False),
        "is_datacenter": extra.get("is_datacenter", False),
    }
    base.update(extra)
    return base


def test_clean_window_low_activity():
    engine = RealtimeViewbotEngine()
    events = [
        _join_event(300, ip_address="1.1.1.1", fingerprint_hash="fp1"),
        _join_event(200, ip_address="2.2.2.2", fingerprint_hash="fp2"),
        _join_event(100, ip_address="3.3.3.3", fingerprint_hash="fp3"),
    ]
    signals = engine._compute_all_signals(events)
    assessment = engine._fuse_assessment(signals, events)
    assert assessment.classification == "clean"
    assert assessment.risk_score < 40


def test_synchronized_joins_classified():
    engine = RealtimeViewbotEngine()
    events = []
    for i in range(12):
        events.append(
            _join_event(
                i * 2,
                ip_address=f"10.0.0.{i % 3}",
                fingerprint_hash="same_fp",
            )
        )
    signals = engine._compute_all_signals(events)
    assert signals.get("synchronized_joins") is True
    assessment = engine._fuse_assessment(signals, events)
    assert assessment.classification in ("likely_viewbot", "coordinated_bot", "suspicious")
    assert assessment.risk_score >= 40


def test_high_velocity_signal():
    engine = RealtimeViewbotEngine()
    events = [_join_event(i) for i in range(30)]
    signals = engine._compute_all_signals(events)
    assert signals.get("join_velocity_per_min", 0) > 12
    assert signals.get("elevated_join_velocity") or signals.get("high_join_velocity")


def test_fingerprint_collision():
    engine = RealtimeViewbotEngine()
    events = [
        _join_event(i, fingerprint_hash="collision_hash")
        for i in range(8)
    ]
    signals = engine._compute_all_signals(events)
    assert signals.get("fingerprint_collision") is True
