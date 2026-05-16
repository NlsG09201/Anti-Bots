import secrets
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import encrypt_value
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import get_db
from app.integrations.twitch.oauth import TwitchOAuth
from app.integrations.twitch.eventsub import TwitchEventSubClient

router = APIRouter(prefix="/integrations/twitch", tags=["Twitch Integration"])
settings = get_settings()

EVENT_TYPES = [
    "channel.follow",
    "stream.online",
    "stream.offline",
    "channel.chat.message",
]


@router.get("/authorize")
async def twitch_authorize(current_user: CurrentUser):
    if not settings.twitch_client_id:
        raise ValidationError("Twitch integration is not configured")

    state = secrets.token_urlsafe(32)
    cache = RedisCache(prefix="oauth")
    await cache.set(f"state:{state}", {"user_id": str(current_user.id), "tenant_id": str(current_user.tenant_id)}, ttl=600)

    oauth = TwitchOAuth()
    url = oauth.get_authorization_url(state)
    return {"authorization_url": url}


@router.get("/callback")
async def twitch_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    cache = RedisCache(prefix="oauth")
    stored = await cache.get(f"state:{state}")
    if not stored:
        raise ValidationError("Invalid or expired OAuth state")

    await cache.delete(f"state:{state}")

    oauth = TwitchOAuth()
    token_data = await oauth.exchange_code(code)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    user_info = await _get_twitch_user(access_token)
    if not user_info:
        raise ValidationError("Could not fetch Twitch user profile")

    broadcaster_id = user_info["id"]
    login = user_info["login"]

    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == UUID(stored["tenant_id"]),
            Stream.platform == Platform.TWITCH,
            Stream.external_id == broadcaster_id,
        )
    )
    stream = result.scalar_one_or_none()

    if stream:
        stream.channel_name = user_info.get("display_name", login)
        stream.oauth_token_encrypted = encrypt_value(access_token)
        meta = stream.settings or {}
        meta["refresh_token_encrypted"] = encrypt_value(refresh_token) if refresh_token else None
        stream.settings = meta
    else:
        stream = Stream(
            tenant_id=UUID(stored["tenant_id"]),
            owner_id=UUID(stored["user_id"]),
            platform=Platform.TWITCH,
            external_id=broadcaster_id,
            channel_name=user_info.get("display_name", login),
            oauth_token_encrypted=encrypt_value(access_token),
            settings={
                "refresh_token_encrypted": encrypt_value(refresh_token) if refresh_token else None,
                "login": login,
            },
        )
        db.add(stream)

    await db.flush()

    if settings.twitch_eventsub_callback_url and settings.twitch_webhook_secret:
        eventsub = TwitchEventSubClient(access_token)
        for event_type in EVENT_TYPES:
            try:
                await eventsub.create_subscription(event_type, broadcaster_id)
            except Exception:
                pass

    frontend = settings.app_frontend_url.rstrip("/")
    return RedirectResponse(f"{frontend}/dashboard/settings?twitch=connected")


@router.get("/status")
async def twitch_status(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.TWITCH,
        )
    )
    streams = result.scalars().all()
    return {
        "connected": len(streams) > 0,
        "configured": bool(settings.twitch_client_id),
        "channels": [
            {
                "id": str(s.id),
                "channel_name": s.channel_name,
                "external_id": s.external_id,
                "is_live": s.is_live,
            }
            for s in streams
        ],
    }


@router.post("/subscribe/{stream_id}")
async def subscribe_events(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import decrypt_value

    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.TWITCH,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream or not stream.oauth_token_encrypted:
        raise NotFoundError("Stream")

    access_token = decrypt_value(stream.oauth_token_encrypted)
    eventsub = TwitchEventSubClient(access_token)
    subs = []
    for event_type in EVENT_TYPES:
        try:
            sub = await eventsub.create_subscription(event_type, stream.external_id)
            subs.append({"type": event_type, "status": "ok", "id": sub.get("data", [{}])[0].get("id")})
        except Exception as e:
            subs.append({"type": event_type, "status": "error", "message": str(e)})

    return {"subscriptions": subs}


async def _get_twitch_user(access_token: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.twitch.tv/helix/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": settings.twitch_client_id,
                },
            )
            if response.status_code != 200:
                return None
            users = response.json().get("data", [])
            return users[0] if users else None
    except Exception:
        return None
