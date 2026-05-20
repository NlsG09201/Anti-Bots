"""Multi-platform adapters (Twitch, Kick, YouTube)."""

from app.services.platforms.base import PlatformAdapter, ViewerSnapshot
from app.services.platforms.registry import get_platform_adapter

__all__ = [
    "PlatformAdapter",
    "ViewerSnapshot",
    "get_platform_adapter",
]
