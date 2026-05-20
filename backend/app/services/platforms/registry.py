"""Platform adapter registry."""

from __future__ import annotations

from typing import Dict, Type

from app.infrastructure.database.models import Platform
from app.services.platforms.base import PlatformAdapter
from app.services.platforms.kick_adapter import KickPlatformAdapter
from app.services.platforms.twitch_adapter import TwitchPlatformAdapter
from app.services.platforms.youtube_adapter import YouTubePlatformAdapter

_ADAPTERS: Dict[Platform, Type[PlatformAdapter]] = {
    Platform.TWITCH: TwitchPlatformAdapter,
    Platform.KICK: KickPlatformAdapter,
    Platform.YOUTUBE: YouTubePlatformAdapter,
}


def get_platform_adapter(platform: Platform) -> PlatformAdapter:
    cls = _ADAPTERS.get(platform, TwitchPlatformAdapter)
    return cls()
