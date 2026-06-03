"""Kick OAuth integration (PKCE)."""

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
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import encrypt_value
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import get_db
from app.integrations.kick.constants import resolve_kick_redirect_uri
from app.integrations.kick.oauth import KickOAuth, kick_credentials_valid

router = APIRouter(prefix="/integrations/kick", tags=["Kick Integration"])
settings = get_settings()


def _frontend_redirect(path: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.app_frontend_url.rstrip('/')}{path}")


@router.get("/setup")
async def kick_setup(_user: CurrentUser):
    cid = settings.kick_client_id or ""
    return {
        "redirect_uri": resolve_kick_redirect_uri(),
        "client_id_prefix": cid[:12] + "..." if len(cid) > 12 else cid,
        "credentials_ok": kick_credentials_valid(),
        "register_at": "https://kick.com/settings/developer",
        "hint": "Redirect URI debe coincidir exactamente en Kick Developer Console.",
    }


@router.get("/authorize")
async def kick_authorize(
    current_user: CurrentUser,
    upgrade_stream_id: Optional[UUID] = Query(None),
):
    if not kick_credentials_valid():
        raise ValidationError(
            "Kick OAuth no configurado. Define KICK_CLIENT_ID y KICK_CLIENT_SECRET en Render."
        )
    oauth = KickOAuth()
    url, state, verifier = oauth.build_authorize_payload()
    cache = RedisCache(prefix="oauth")
    payload = {
        "user_id": str(current_user.id),
        "tenant_id": str(current_user.tenant_id),
        "provider": "kick",
        "code_verifier": verifier,
    }
    if upgrade_stream_id:
        payload["upgrade_stream_id"] = str(upgrade_stream_id)
    await cache.set(f"kick_state:{state}", payload, ttl=900)
    return {"authorization_url": url}


@router.get("/callback")
async def kick_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        msg = quote((error_description or error)[:200])
        return _frontend_redirect(
            f"/dashboard/settings?kick_error={quote(error)}&kick_msg={msg}"
        )
    if not code or not state:
        return _frontend_redirect("/dashboard/settings?kick_error=missing_params")

    cache = RedisCache(prefix="oauth")
    stored = await cache.get(f"kick_state:{state}")
    if not stored:
        return _frontend_redirect(
            "/dashboard/settings?kick_error=invalid_state"
            "&kick_msg=OAuth+state+invalido+o+expirado.+Intenta+conectar+de+nuevo"
        )
    await cache.delete(f"kick_state:{state}")

    verifier = stored.get("code_verifier")
    if not verifier:
        raise ValidationError("PKCE verifier missing")

    oauth = KickOAuth()
    try:
        token_data = await oauth.exchange_code(code, verifier)
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.text or exc.response.reason_phrase or "oauth_token_error")[:180]
        return _frontend_redirect(
            f"/dashboard/settings?kick_error=token_exchange_failed&kick_msg={quote(detail)}"
        )
    except httpx.HTTPError as exc:
        return _frontend_redirect(
            f"/dashboard/settings?kick_error=token_exchange_failed&kick_msg={quote(str(exc)[:180])}"
        )
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    user = await oauth.fetch_user(access_token)
    slug = (
        user.get("slug")
        or user.get("username")
        or user.get("name")
        or ""
    )
    user_id = str(user.get("id") or user.get("user_id") or slug)
    if not slug:
        profile = await _fetch_kick_profile_public(access_token)
        slug = profile.get("slug") or profile.get("username") or ""
        user_id = str(profile.get("id") or user_id)

    if not slug:
        return _frontend_redirect(
            "/dashboard/settings?kick_error=no_profile"
            "&kick_msg=No+se+pudo+obtener+el+canal+Kick"
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
                Stream.platform == Platform.KICK,
                Stream.external_id == user_id,
            )
        )
        stream = result.scalar_one_or_none()

    owner_id = stored.get("user_id")
    meta = {
        "login": slug.lower(),
        "monitor_mode": False,
        "soc_monitor": True,
        "is_owned": True,
        "auto_mitigate": True,
        "force_monitor": True,
    }
    if refresh_token:
        meta["refresh_token_encrypted"] = encrypt_value(refresh_token)

    if stream:
        stream.channel_name = slug
        stream.external_id = user_id
        stream.oauth_token_encrypted = encrypt_value(access_token)
        existing = dict(stream.settings or {})
        existing.update(meta)
        stream.settings = existing
    else:
        stream = Stream(
            tenant_id=UUID(stored["tenant_id"]),
            owner_id=UUID(owner_id),
            platform=Platform.KICK,
            external_id=user_id,
            channel_name=slug,
            oauth_token_encrypted=encrypt_value(access_token),
            settings=meta,
        )
        db.add(stream)

    await db.commit()
    if upgrade_id:
        return _frontend_redirect(f"/dashboard/viewers?stream={upgrade_id}&kick=connected")
    return _frontend_redirect("/dashboard/settings?kick=connected")


@router.get("/status")
async def kick_status(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.KICK,
        )
    )
    streams = result.scalars().all()
    return {
        "connected": any(s.oauth_token_encrypted for s in streams),
        "configured": kick_credentials_valid(),
        "redirect_uri": resolve_kick_redirect_uri(),
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


async def _fetch_kick_profile_public(access_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://kick.com/api/v2/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return {}
