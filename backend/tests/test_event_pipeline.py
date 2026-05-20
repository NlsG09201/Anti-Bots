"""Tests del pipeline de eventos (sin Redis real)."""

from uuid import uuid4

from app.events.schemas import EventCategory, PipelineEvent, resolve_category
from app.events.schemas import EVENT_TYPE_TO_CATEGORY


def test_event_categories_mapping():
    assert EVENT_TYPE_TO_CATEGORY["viewer_join"] == EventCategory.VIEWER
    assert EVENT_TYPE_TO_CATEGORY["follow"] == EventCategory.FOLLOW
    assert EVENT_TYPE_TO_CATEGORY["chat_message"] == EventCategory.MESSAGE
    assert EVENT_TYPE_TO_CATEGORY["widget_connect"] == EventCategory.CONNECTION


def test_resolve_suspicious_by_pre_risk():
    cat = resolve_category("viewer_join", {"pre_risk_score": 85})
    assert cat == EventCategory.SUSPICIOUS


def test_pipeline_event_roundtrip_fields():
    sid, tid = uuid4(), uuid4()
    event = PipelineEvent.from_ingest(
        stream_id=sid,
        tenant_id=tid,
        event_type="chat_message",
        platform_username="tester",
        metadata={"msg": "hello"},
        source="api",
    )
    fields = event.to_stream_fields()
    restored = PipelineEvent.from_stream_fields(fields)
    assert restored.event_type == "chat_message"
    assert restored.category == EventCategory.MESSAGE
    assert restored.platform_username == "tester"
    assert restored.metadata["msg"] == "hello"


def test_normalize_event_type_mapping():
    from app.events.processor import _normalize_event_type

    assert _normalize_event_type("channel.follow") == "follow"
    assert _normalize_event_type("channel.chat.message") == "chat_message"
