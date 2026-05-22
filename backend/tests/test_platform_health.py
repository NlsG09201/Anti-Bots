"""Tests for platform monitor health engine."""

import pytest

from app.services.platform_health.circuit_breaker import get_circuit_breaker
from app.services.platform_health.tracker import MonitorHealthTracker


def test_circuit_breaker_opens_after_failures():
    cb = get_circuit_breaker("test_platform")
    cb.failures = 0
    cb.state = "closed"
    for _ in range(5):
        cb.record_failure()
    assert cb.state == "open"
    assert not cb.allow_request()


def test_tracker_ai_flags_stale_poll():
    t = MonitorHealthTracker("s1", "kick", "channel", slug="ch")
    import time

    t._is_live = True
    t._last_poll_at = time.monotonic() - 120
    score, flags = t.compute_ai_flags()
    assert score >= 35
    assert "stale_poll" in flags


def test_tracker_snapshot_fields():
    t = MonitorHealthTracker("s2", "youtube", "MyChannel")
    t.record_poll(viewer_count=100, is_live=True, latency_ms=42.0)
    t.record_event("chat_message")
    snap = t.to_snapshot(status="healthy")
    assert snap.viewer_count == 100
    assert snap.platform == "youtube"
    assert snap.poll_latency_ms == 42.0
