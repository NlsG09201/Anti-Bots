"""Comprobación de bans activos antes de procesar eventos."""

from typing import Any, Dict, Optional
from uuid import UUID

from app.services.mitigation.service import MitigationService


async def is_event_blocked(
    mitigation: MitigationService,
    stream_id: UUID,
    *,
    platform_user_id: Optional[str] = None,
    platform_username: Optional[str] = None,
    ip_address: Optional[str] = None,
    fingerprint_hash: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if platform_user_id and platform_user_id.isdigit():
        hit = await mitigation.is_banned(stream_id, "user", platform_user_id)
        if hit:
            return hit
    if platform_username:
        hit = await mitigation.is_banned(stream_id, "user_login", platform_username.lower())
        if hit:
            return hit
    if ip_address and ip_address not in ("", "twitch:chat"):
        hit = await mitigation.is_banned(stream_id, "ip", ip_address)
        if hit:
            return hit
    if fingerprint_hash:
        hit = await mitigation.is_banned(stream_id, "fingerprint", fingerprint_hash)
        if hit:
            return hit
    return None
