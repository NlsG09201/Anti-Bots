from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def ban_user_on_twitch(
    broadcaster_id: str,
    access_token: str,
    user_id: str,
    reason: str = "StreamShield: actividad sospechosa",
    duration_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Timeout o ban via Helix moderation (requiere permisos mod en el canal)."""
    body: Dict[str, Any] = {
        "data": {
            "user_id": user_id,
            "reason": reason[:500],
        }
    }
    if duration_seconds and duration_seconds > 0:
        body["data"]["duration"] = duration_seconds

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.twitch.tv/helix/moderation/bans",
            params={
                "broadcaster_id": broadcaster_id,
                "moderator_id": broadcaster_id,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.twitch_client_id,
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code not in (200, 201):
            logger.warning(
                "twitch_ban_failed",
                status=response.status_code,
                body=response.text[:300],
            )
            return {"ok": False, "status": response.status_code, "detail": response.text}
        return {"ok": True, "data": response.json()}
