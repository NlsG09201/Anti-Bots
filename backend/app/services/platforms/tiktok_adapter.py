"""TikTok Live platform adapter."""

from __future__ import annotations

from typing import List

from app.integrations.tiktok.webcast import UNAVAILABLE_REASON
from app.infrastructure.database.models import Platform, Stream
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot


class TikTokPlatformAdapter(PlatformAdapter):
    platform = Platform.TIKTOK

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        raise RuntimeError(UNAVAILABLE_REASON)

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        return []
