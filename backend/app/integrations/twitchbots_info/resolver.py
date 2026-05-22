"""Resolve Twitch usernames to numeric IDs for TwitchBots.info API."""

from __future__ import annotations

import re
from typing import Optional

from app.core.logging import get_logger
from app.integrations.twitch.helix import TwitchHelixClient
from app.integrations.twitchbots_info.cache import get_twitchbots_info_cache

logger = get_logger(__name__)

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{2,25}$")


class TwitchIdResolver:
    async def resolve(
        self,
        *,
        username: Optional[str] = None,
        platform_user_id: Optional[str] = None,
    ) -> Optional[str]:
        if platform_user_id and str(platform_user_id).strip().isdigit():
            return str(platform_user_id).strip()
        if not username:
            return None
        uname = username.strip().lstrip("@")
        if not _USERNAME_RE.match(uname):
            return None
        cache = get_twitchbots_info_cache()
        cached = await cache.resolve_username(uname)
        if cached and cached.isdigit():
            return cached
        client = TwitchHelixClient()
        if not client.configured:
            return None
        try:
            user = await client.get_user_by_login(uname)
        except Exception as exc:
            logger.debug("tbi_helix_resolve_failed", username=uname, error=str(exc)[:100])
            return None
        if not user or not user.get("id"):
            return None
        tid = str(user["id"])
        await cache.store_username_id(uname, tid)
        return tid


_resolver: Optional[TwitchIdResolver] = None


def get_twitch_id_resolver() -> TwitchIdResolver:
    global _resolver
    if _resolver is None:
        _resolver = TwitchIdResolver()
    return _resolver
