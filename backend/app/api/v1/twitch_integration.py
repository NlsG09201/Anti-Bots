import secrets
from typing import List, Optional
from urllib.parse import quote
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
from app.integrations.twitch.constants import PRODUCTION_CALLBACK_URL
from app.integrations.twitch.oauth import (
    TwitchOAuth,
    resolve_twitch_redirect_uri,
    twitch_credentials_valid,
)
from app.integrations.twitch.eventsub import TwitchEventSubClient

router = APIRouter(prefix="/integrations/twitch", tags=["Twitch Integration"])
settings = get_settings()

EVENT_TYPES = [
    "channel.follow",
    "stream.online",
    "stream.offline",
    "channel.chat.message",
]


@router.get("/setup")
async def twitch_setup(current_user: CurrentUser):
    """Diagnóstico: qué URI usa el servidor y si las credenciales son válidas."""
    cid = settings.twitch_client_id or ""
    return {
        "redirect_uri": resolve_twitch_redirect_uri(),
        "client_id_prefix": cid[:12] + "..." if len(cid) > 12 else cid,
        "credentials_ok": twitch_credentials_valid(),
        "client_id_equals_secret": bool(
            cid and cid == (settings.twitch_client_secret or "").strip()
        ),
        "register_at": "https://dev.twitch.tv/console/apps",
        "hint": (
            "En Twitch → OAuth Redirect URLs debe existir exactamente redirect_uri. "
            "Client ID y Client Secret deben ser distintos (app real en dev.twitch.tv)."
        ),
    }


async def _start_oauth(state_payload: dict) -> str:
    state = secrets.token_urlsafe(32)
    cache = RedisCache(prefix="oauth")
    await cache.set(f"state:{state}", state_payload, ttl=900)
    oauth = TwitchOAuth()
    return oauth.get_authorization_url(state)


@router.get("/authorize")
async def twitch_authorize(
    current_user: CurrentUser,
    upgrade_stream_id: Optional[UUID] = Query(None),
):
    if not settings.twitch_client_id:
        raise ValidationError("Twitch integration is not configured")
    if not twitch_credentials_valid():
        raise ValidationError(
            "Credenciales Twitch inválidas en el servidor: Client ID y Client Secret "
            "no pueden ser iguales. Crea una app en https://dev.twitch.tv/console/apps "
            "y actualiza TWITCH_CLIENT_ID y TWITCH_CLIENT_SECRET en Render."
        )

    payload = {
        "user_id": str(current_user.id),
        "tenant_id": str(current_user.tenant_id),
    }
    if upgrade_stream_id:
        payload["upgrade_stream_id"] = str(upgrade_stream_id)
    url = await _start_oauth(payload)
    return {"authorization_url": url}


@router.get("/invite/{invite_token}/start")
async def start_invite_oauth(invite_token: str):
    """Inicio OAuth publico (sin login SOC) usando token de invitacion."""
    if not twitch_credentials_valid():
        raise ValidationError("Twitch no configurado en el servidor")

    cache = RedisCache(prefix="oauth")
    stored = await cache.get(f"invite:{invite_token}")
    if not stored:
        raise ValidationError("Invitacion invalida o expirada")

    url = await _start_oauth({
        "tenant_id": stored["tenant_id"],
        "upgrade_stream_id": stored["stream_id"],
        "invite": invite_token,
        "public_invite": True,
    })
    return RedirectResponse(url)


def _frontend_redirect(path: str) -> RedirectResponse:
    base = settings.app_frontend_url.rstrip("/")
    return RedirectResponse(f"{base}{path}")


@router.get("/callback")
async def twitch_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        msg = quote((error_description or error)[:200])
        return _frontend_redirect(f"/dashboard/settings?twitch_error={quote(error)}&twitch_msg={msg}")

    if not code or not state:
        return _frontend_redirect("/dashboard/settings?twitch_error=missing_params")

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
        if stream and stream.external_id != broadcaster_id:
            expected = (stream.settings or {}).get("login", stream.channel_name)
            return _frontend_redirect(
                f"/dashboard/channels?twitch_error=wrong_account"
                f"&twitch_msg={quote(f'Debes conectar la cuenta @{expected}')}"
            )

    if not stream:
        result = await db.execute(
            select(Stream).where(
                Stream.tenant_id == UUID(stored["tenant_id"]),
                Stream.platform == Platform.TWITCH,
                Stream.external_id == broadcaster_id,
            )
        )
        stream = result.scalar_one_or_none()

    owner_id = stored.get("user_id")
    if not owner_id and stream:
        owner_id = str(stream.owner_id)

    if stream:
        stream.channel_name = user_info.get("display_name", login)
        stream.oauth_token_encrypted = encrypt_value(access_token)
        meta = stream.settings or {}
        meta["refresh_token_encrypted"] = encrypt_value(refresh_token) if refresh_token else None
        meta["monitor_mode"] = False
        meta["is_owned"] = True
        meta["auto_mitigate"] = True
        stream.settings = meta
    else:
        if not owner_id:
            return _frontend_redirect("/dashboard/channels?twitch_error=missing_owner")
        stream = Stream(
            tenant_id=UUID(stored["tenant_id"]),
            owner_id=UUID(owner_id),
            platform=Platform.TWITCH,
            external_id=broadcaster_id,
            channel_name=user_info.get("display_name", login),
            oauth_token_encrypted=encrypt_value(access_token),
            settings={
                "refresh_token_encrypted": encrypt_value(refresh_token) if refresh_token else None,
                "login": login,
                "monitor_mode": False,
                "is_owned": True,
                "auto_mitigate": True,
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

    if stored.get("invite") or stored.get("upgrade_stream_id"):
        await cache.delete(f"invite:{stored['invite']}") if stored.get("invite") else None
        return _frontend_redirect("/dashboard/channels?twitch=connected")
    return _frontend_redirect("/dashboard/settings?twitch=connected")


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
        "configured": twitch_credentials_valid(),
        "redirect_uri": resolve_twitch_redirect_uri(),
        "credentials_ok": twitch_credentials_valid(),
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
