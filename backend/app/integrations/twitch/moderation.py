from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
MAX_TIMEOUT_SECONDS = 14 * 24 * 60 * 60


async def ban_user_on_twitch(
    broadcaster_id: str,
    access_token: str,
    user_id: str,
    reason: str = "StreamShield: actividad sospechosa",
    duration_seconds: Optional[int] = None,
    moderator_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Timeout o ban via Helix moderation (requiere permisos mod en el canal)."""
    body: Dict[str, Any] = {
        "data": {
            "user_id": user_id,
            "reason": reason[:500],
        }
    }
    if duration_seconds is not None:
        if not 1 <= duration_seconds <= MAX_TIMEOUT_SECONDS:
            return {
                "ok": False,
                "status": 422,
                "detail": "La duración del timeout debe estar entre 1 segundo y 14 días.",
            }
        body["data"]["duration"] = duration_seconds

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.twitch.tv/helix/moderation/bans",
                params={
                    "broadcaster_id": broadcaster_id,
                    # This OAuth integration authorizes the broadcaster account.
                    "moderator_id": moderator_id or broadcaster_id,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": settings.twitch_client_id,
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        logger.warning("twitch_ban_request_failed", error=str(exc)[:200])
        return {"ok": False, "status": 502, "detail": str(exc)[:240]}

    if response.status_code not in (200, 201):
        logger.warning(
            "twitch_ban_failed",
            status=response.status_code,
            body=response.text[:300],
        )
        return {"ok": False, "status": response.status_code, "detail": response.text}
    return {"ok": True, "data": response.json()}


async def delete_chat_message_on_twitch(
    broadcaster_id: str,
    moderator_id: str,
    access_token: str,
    message_id: str,
) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                "https://api.twitch.tv/helix/moderation/chat",
                params={
                    "broadcaster_id": broadcaster_id,
                    "moderator_id": moderator_id,
                    "message_id": message_id,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": settings.twitch_client_id,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("twitch_chat_delete_request_failed", error=str(exc)[:160])
        return {"ok": False, "status": 502, "detail": str(exc)[:200]}
    if response.status_code != 204:
        logger.warning("twitch_chat_delete_failed", status=response.status_code)
        return {"ok": False, "status": response.status_code, "detail": response.text[:200]}
    return {"ok": True, "status": 204}


async def add_channel_moderator_on_twitch(
    broadcaster_id: str,
    moderator_user_id: str,
    access_token: str,
) -> Dict[str, Any]:
    """Idempotently add a user as moderator using the broadcaster's OAuth token."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": settings.twitch_client_id,
    }
    params = {"broadcaster_id": broadcaster_id, "user_id": moderator_user_id}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            current = await client.get(
                "https://api.twitch.tv/helix/moderation/moderators",
                headers=headers,
                params=params,
            )
            if current.status_code != 200:
                return {"ok": False, "status": current.status_code, "detail": current.text[:300]}
            if any(
                str(item.get("user_id")) == moderator_user_id
                for item in current.json().get("data", [])
            ):
                return {"ok": True, "status": 200, "already_moderator": True}

            response = await client.post(
                "https://api.twitch.tv/helix/moderation/moderators",
                headers=headers,
                params=params,
            )
    except httpx.HTTPError as exc:
        logger.warning("twitch_add_moderator_request_failed", error=str(exc)[:180])
        return {"ok": False, "status": 502, "detail": str(exc)[:220]}
    if response.status_code != 204:
        logger.warning(
            "twitch_add_moderator_failed",
            status=response.status_code,
            body=response.text[:260],
        )
        return {"ok": False, "status": response.status_code, "detail": response.text[:300]}
    return {"ok": True, "status": 204, "already_moderator": False}


async def remove_channel_moderator_on_twitch(
    broadcaster_id: str,
    moderator_user_id: str,
    access_token: str,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": settings.twitch_client_id,
    }
    params = {"broadcaster_id": broadcaster_id, "user_id": moderator_user_id}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            current = await client.get(
                "https://api.twitch.tv/helix/moderation/moderators",
                headers=headers,
                params=params,
            )
            if current.status_code != 200:
                return {"ok": False, "status": current.status_code, "detail": current.text[:300]}
            if not any(
                str(item.get("user_id")) == moderator_user_id
                for item in current.json().get("data", [])
            ):
                return {"ok": True, "status": 200, "already_removed": True}
            response = await client.delete(
                "https://api.twitch.tv/helix/moderation/moderators",
                headers=headers,
                params=params,
            )
    except httpx.HTTPError as exc:
        logger.warning("twitch_remove_moderator_request_failed", error=str(exc)[:180])
        return {"ok": False, "status": 502, "detail": str(exc)[:220]}
    if response.status_code != 204:
        logger.warning(
            "twitch_remove_moderator_failed",
            status=response.status_code,
            body=response.text[:260],
        )
        return {"ok": False, "status": response.status_code, "detail": response.text[:300]}
    return {"ok": True, "status": 204, "already_removed": False}
