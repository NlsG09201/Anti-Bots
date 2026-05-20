"""Abstract platform adapter for live streaming anti-bot."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.infrastructure.database.models import Platform, Stream


@dataclass
class ViewerSnapshot:
    platform_user_id: str
    platform_username: Optional[str]
    is_in_chat: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveStatus:
    is_live: bool
    viewer_count: int = 0
    title: Optional[str] = None
    external_live_id: Optional[str] = None


class PlatformAdapter(ABC):
    platform: Platform

    @abstractmethod
    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        ...

    @abstractmethod
    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        ...

    async def supports_oauth(self) -> bool:
        return False
