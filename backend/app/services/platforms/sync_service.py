"""Cross-platform viewer sync for enterprise multi-platform streams."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import Stream
from app.services.platforms.registry import get_platform_adapter
from app.services.viewers.session import ViewerSessionService

logger = get_logger(__name__)


class PlatformSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.viewers = ViewerSessionService(db)

    async def sync_viewers(self, stream: Stream) -> Dict[str, Any]:
        adapter = get_platform_adapter(stream.platform)
        live = await adapter.fetch_live_status(stream)
        snapshots = await adapter.fetch_viewers(stream)

        synced = 0
        for snap in snapshots:
            username = snap.platform_username or snap.platform_user_id
            if snap.is_in_chat and username:
                await self.viewers.upsert_chat_viewer(
                    stream.id,
                    username,
                    platform_user_id=snap.platform_user_id,
                    source=snap.metadata.get("source", stream.platform.value),
                )
            else:
                await self.viewers.upsert_from_event(
                    stream.id,
                    platform_username=snap.platform_username,
                    platform_user_id=snap.platform_user_id,
                    ip_address=None,
                    fingerprint_hash=None,
                    risk_score=0.0,
                    event_type="platform_sync",
                )
            synced += 1

        return {
            "platform": stream.platform.value,
            "is_live": live.is_live,
            "viewer_count": live.viewer_count,
            "chatters_synced": synced,
            "source": stream.platform.value,
        }
