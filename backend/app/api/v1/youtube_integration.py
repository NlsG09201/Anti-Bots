"""YouTube Live OAuth integration."""

from __future__ import annotations

import secrets
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.security import encrypt_value
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import get_db
from app.integrations.youtube.constants import resolve_youtube_redirect_uri
from app.integrations.youtube.oauth import YouTubeOAuth, youtube_credentials_valid

router = APIRouter(prefix="/integrations/youtube", tags=["YouTube Integration"])
settings = get_settings()


def _frontend_redirect(path: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.app_frontend_url.rstrip('/')}{path}")


def _oauth_error_redirect(error_code: str, message: str, *, extra: str = "") -> RedirectResponse:
    path = (
        f"/dashboard/settings?youtube_error={quote(error_code)}"
        f"&youtube_msg={quote(message)}"
    )
    if extra:
        path += f"&{extra}"
    return _frontend_redirect(path)


@router.get("/setup")
async def youtube_setup(_user: CurrentUser):
    cid = settings.youtube_client_id or ""
    return {
        "redirect_uri": resolve_youtube_redirect_uri(),
        "client_id_prefix": cid[:20] + "..." if len(cid) > 20 else cid,
        "credentials_ok": youtube_credentials_valid(),
        "register_at": "https://console.cloud.google.com/apis/credentials",
        "hint": "Activa YouTube Data API v3 y añade la redirect URI exacta.",
    }


@router.get("/authorize")
async def youtube_authorize(
    current_user: CurrentUser,
    upgrade_stream_id: Optional[UUID] = Query(None),
):
    if not youtube_credentials_valid():
        raise ValidationError(
            "YouTube OAuth no configurado. Define YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET."
        )
    state = secrets.token_urlsafe(32)
    cache = RedisCache(prefix="oauth")
    payload = {
        "user_id": str(current_user.id),
        "tenant_id": str(current_user.tenant_id),
        "provider": "youtube",
    }
    if upgrade_stream_id:
        payload["upgrade_stream_id"] = str(upgrade_stream_id)
    await cache.set(f"youtube_state:{state}", payload, ttl=900)
    oauth = YouTubeOAuth()
    return {"authorization_url": oauth.get_authorization_url(state)}


@router.get("/callback")
async def youtube_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        return _frontend_redirect(
            f"/dashboard/settings?youtube_error={quote(error)}"
        )
    if not code or not state:
        return _frontend_redirect("/dashboard/settings?youtube_error=missing_params")

    cache = RedisCache(prefix="oauth")
    stored = await cache.get(f"youtube_state:{state}")
    if not stored:
        return _frontend_redirect(
            "/dashboard/settings?youtube_error=invalid_state"
            "&youtube_msg=OAuth+state+invalido+o+expirado.+Intenta+conectar+de+nuevo"
        )
    await cache.delete(f"youtube_state:{state}")

    oauth = YouTubeOAuth()
    try:
        token_data = await oauth.exchange_code(code)
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.text or exc.response.reason_phrase or "oauth_token_error")[:180]
        return _oauth_error_redirect(
            "token_exchange_failed",
            f"Token exchange failed: {detail}",
            extra=f"youtube_redirect_uri={quote(resolve_youtube_redirect_uri())}",
        )
    except httpx.HTTPError as exc:
        return _oauth_error_redirect(
            "token_exchange_failed",
            f"Token exchange failed: {str(exc)[:180]}",
            extra=f"youtube_redirect_uri={quote(resolve_youtube_redirect_uri())}",
        )
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    channel = await _fetch_youtube_channel(access_token)
    channel_id = channel.get("id", "")
    title = channel.get("snippet", {}).get("title", channel_id)
    if not channel_id:
        return _frontend_redirect(
            "/dashboard/settings?youtube_error=no_channel"
            "&youtube_msg=Sin+canal+de+YouTube+en+esta+cuenta"
        )

    upgrade_id = stored.get("upgrade_stream_id")
    stream = None
    if upgrade_id:
        result = await db.execute(
            select(Stream).where(
                Stream.id == UUID(upgrade_id),
                Stream.tenant_id == UUID(stored["tenant_id"]),
            )
        )
        stream = result.scalar_one_or_none()

    if not stream:
        result = await db.execute(
            select(Stream).where(
                Stream.tenant_id == UUID(stored["tenant_id"]),
                Stream.platform == Platform.YOUTUBE,
                Stream.external_id == channel_id,
            )
        )
        stream = result.scalar_one_or_none()

    meta = {
        "login": title,
        "monitor_mode": False,
        "soc_monitor": True,
        "is_owned": True,
        "auto_mitigate": True,
        "force_monitor": True,
    }
    if refresh_token:
        meta["refresh_token_encrypted"] = encrypt_value(refresh_token)

    if stream:
        stream.channel_name = title
        stream.external_id = channel_id
        stream.oauth_token_encrypted = encrypt_value(access_token)
        existing = dict(stream.settings or {})
        existing.update(meta)
        stream.settings = existing
    else:
        stream = Stream(
            tenant_id=UUID(stored["tenant_id"]),
            owner_id=UUID(stored["user_id"]),
            platform=Platform.YOUTUBE,
            external_id=channel_id,
            channel_name=title,
            oauth_token_encrypted=encrypt_value(access_token),
            settings=meta,
        )
        db.add(stream)

    await db.commit()
    if upgrade_id:
        return _frontend_redirect(f"/dashboard/viewers?stream={upgrade_id}&youtube=connected")
    return _frontend_redirect("/dashboard/settings?youtube=connected")


@router.get("/status")
async def youtube_status(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.YOUTUBE,
        )
    )
    streams = result.scalars().all()
    return {
        "connected": any(s.oauth_token_encrypted for s in streams),
        "configured": youtube_credentials_valid(),
        "redirect_uri": resolve_youtube_redirect_uri(),
        "api_key_set": bool(settings.youtube_api_key),
        "channels": [
            {
                "id": str(s.id),
                "channel_name": s.channel_name,
                "external_id": s.external_id,
                "is_live": s.is_live,
                "has_oauth": bool(s.oauth_token_encrypted),
            }
            for s in streams
        ],
    }


async def _fetch_youtube_channel(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"part": "snippet", "mine": "true"},
        )
        if response.status_code != 200:
            return {}
        items = response.json().get("items", [])
        return items[0] if items else {}
