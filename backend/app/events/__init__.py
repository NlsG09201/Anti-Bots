"""Pipeline de eventos en tiempo real (Redis Streams + colas + WebSockets)."""

from app.events.bus import EventBus, get_event_bus
from app.events.schemas import EventCategory, PipelineEvent

__all__ = ["EventBus", "EventCategory", "PipelineEvent", "get_event_bus"]
