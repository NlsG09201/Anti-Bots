"""Cross-platform viewer sync for enterprise multi-platform streams."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Platform, Stream
from app.services.platforms.registry import get_platform_adapter
from app.services.viewers.session import ViewerSessionService


class PlatformSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.viewers = ViewerSessionService(db)

    async def sync_viewers(self, stream: Stream) -> Dict[str, Any]:
        adapter = get_platform_adapter(stream.platform)
        live = await adapter.fetch_live_status(stream)
        stream.is_live = live.is_live
        stream.viewer_count = live.viewer_count
        if stream.platform == Platform.YOUTUBE:
            meta = dict(stream.settings or {})
            if live.external_live_id:
                # YouTube distingue el ID del canal del ID del video en directo.
                meta["live_video_id"] = live.external_live_id
            else:
                meta.pop("live_video_id", None)
            stream.settings = meta

        if live.is_live:
            snapshots = await adapter.fetch_viewers(stream)
            chatters = [
                {
                    "username": snap.platform_username or snap.platform_user_id,
                    "user_id": snap.platform_user_id,
                    "source": snap.metadata.get("source", stream.platform.value),
                }
                for snap in snapshots
                if snap.is_in_chat and (snap.platform_username or snap.platform_user_id)
            ]
        else:
            # Un canal confirmado offline no debe conservar participantes activos.
            chatters = []

        sync_stats = await self.viewers.sync_chat_presence(
            stream.id,
            chatters,
            full_resync=True,
            clear_if_empty=True,
        )
        synced = sync_stats["total_synced"]

        return {
            "platform": stream.platform.value,
            "is_live": live.is_live,
            "viewer_count": live.viewer_count,
            "chatters_synced": synced,
            "source": stream.platform.value,
        }
