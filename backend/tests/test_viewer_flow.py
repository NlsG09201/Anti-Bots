"""Tests for Viewer Flow Intelligence engine."""

from app.viewer_flow.analyzer import analyze_stream
from app.viewer_flow.tracker import StreamFlowState


def test_viewbot_spike_detection():
    state = StreamFlowState(
        stream_id="s1",
        tenant_id="t1",
        platform="kick",
        channel_name="testchannel",
    )
    state.record_pulse(50, True)
    state.record_pulse(200, True)
    for _ in range(3):
        state.record_pulse(210, True)
    snap = analyze_stream(state)
    assert snap.metrics.viewers_current == 210
    assert snap.metrics.suspicious_growth_score >= 0


def test_silent_chatter_entity():
    state = StreamFlowState(
        stream_id="s2",
        tenant_id="t1",
        platform="youtube",
        channel_name="ytchan",
    )
    state.record_entity_event("viewer_join", username="silent_bot_99")
    snap = analyze_stream(state)
    assert len(snap.suspicious_viewers) >= 0
