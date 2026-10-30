"""Kick OAuth integration (PKCE)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import encrypt_value
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import AuditLog, KickWebhookEvent, Platform, Stream, UserRole
from app.infrastructure.database.session import get_db
from app.integrations.kick.constants import resolve_kick_redirect_uri
from app.integrations.kick.oauth import KickOAuth, kick_credentials_valid

router = APIRouter(prefix="/integrations/kick", tags=["Kick Integration"])
settings = get_settings()
logger = get_logger(__name__)


def _frontend_redirect(path: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.app_frontend_url.rstrip('/')}{path}")


def _oauth_error_redirect(
    error_code: str,
    message: str,
    *,
    extra: str = "",
) -> RedirectResponse:
    path = (
        f"/dashboard/settings?kick_error={quote(error_code)}"
        f"&kick_msg={quote(message)}"
    )
    if extra:
        path += f"&{extra}"
    return _frontend_redirect(path)


@router.get("/setup")
async def kick_setup(_user: CurrentUser):
    cid = settings.kick_client_id or ""
    return {
        "redirect_uri": resolve_kick_redirect_uri(),
        "webhook_callback_url": settings.kick_webhook_callback_url,
        "client_id_prefix": cid[:12] + "..." if len(cid) > 12 else cid,
        "credentials_ok": kick_credentials_valid(),
        "register_at": "https://kick.com/settings/developer",
        "hint": "Kick OAuth usa PKCE; registra el redirect URI exacto y el Client ID del proyecto.",
    }


@router.get("/authorize")
async def kick_authorize(
    current_user: CurrentUser,
    upgrade_stream_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not kick_credentials_valid():
        raise ValidationError(
            "Kick OAuth no configurado. Define KICK_CLIENT_ID en Render."
        )
    if upgrade_stream_id:
        result = await db.execute(
            select(Stream).where(
                Stream.id == upgrade_stream_id,
                Stream.tenant_id == current_user.tenant_id,
                Stream.platform == Platform.KICK,
            )
        )
        stream = result.scalar_one_or_none()
        if not stream:
            raise NotFoundError("Kick account")
        if stream.owner_id != current_user.id and current_user.role not in (
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
        ):
            raise AuthorizationError("Only the account owner or a tenant administrator can reconnect it")
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
        return _oauth_error_redirect(
            "token_exchange_failed",
            f"Token exchange failed: {detail}",
            extra=f"kick_redirect_uri={quote(resolve_kick_redirect_uri())}",
        )
    except httpx.HTTPError as exc:
        return _oauth_error_redirect(
            "token_exchange_failed",
            f"Token exchange failed: {str(exc)[:180]}",
            extra=f"kick_redirect_uri={quote(resolve_kick_redirect_uri())}",
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
        if stream and str(stream.external_id) != user_id:
            return _frontend_redirect(
                "/dashboard/settings?kick_error=account_mismatch"
                "&kick_msg=La+cuenta+Kick+autorizada+no+coincide+con+el+canal+seleccionado"
            )

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
        # New connections receive AI alerts first. Automatic bans/timeouts stay
        # disabled until the channel owner explicitly enables mitigation.
        "auto_mitigate": False,
        "kick_mitigation_default_reviewed": True,
        "force_monitor": True,
    }
    expires_in = int(token_data.get("expires_in") or 3600)
    from datetime import datetime, timedelta, timezone
    meta["oauth_access_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 60))
    ).isoformat()
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
    try:
        previous_settings = dict(stream.settings or {})
        subscription_result = await oauth.reconcile_event_subscriptions(
            access_token,
            previously_requested=previous_settings.get("kick_webhook_subscriptions", []),
            requested_at=previous_settings.get("kick_webhook_subscriptions_requested_at"),
        )
        meta = dict(stream.settings or {})
        meta["kick_webhook_subscriptions"] = (
            subscription_result.get("subscribed", [])
            + subscription_result.get("created", [])
            + subscription_result.get("assumed", [])
        )
        if subscription_result.get("created"):
            meta["kick_webhook_subscriptions_requested_at"] = datetime.now(timezone.utc).isoformat()
        meta["kick_webhook_subscriptions_verified"] = bool(
            subscription_result.get("verified_by_api")
        )
        meta["kick_chat_webhook_subscribed"] = (
            "chat.message.sent" in meta["kick_webhook_subscriptions"]
        )
        meta["kick_webhook_enabled"] = bool(meta["kick_webhook_subscriptions"])
        meta["kick_webhook_subscription_error"] = (
            ",".join(subscription_result.get("failed", [])) or None
        )
        meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
        meta["kick_webhook_callback_url"] = settings.kick_webhook_callback_url
        stream.settings = meta
        await db.commit()
    except Exception as exc:
        meta = dict(stream.settings or {})
        meta["kick_webhook_subscription_error"] = type(exc).__name__
        meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
        stream.settings = meta
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        # OAuth connection stays valid if the developer app has not enabled
        # its public webhook endpoint yet; expose the reason in Render logs.
        logger.warning(
            "kick_chat_event_subscription_failed",
            broadcaster_id=user_id,
            error_type=type(exc).__name__,
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
        )
    if upgrade_id:
        return _frontend_redirect("/dashboard/channels?kick=connected")
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
    stream_ids = [s.id for s in streams]
    delivery_counts: dict[str, dict[str, int]] = {}
    latest_delivery: dict[str, KickWebhookEvent] = {}
    if stream_ids:
        counts_result = await db.execute(
            select(
                KickWebhookEvent.stream_id,
                KickWebhookEvent.processing_status,
                func.count(KickWebhookEvent.id),
            )
            .where(KickWebhookEvent.stream_id.in_(stream_ids))
            .group_by(KickWebhookEvent.stream_id, KickWebhookEvent.processing_status)
        )
        for stream_id, status, count in counts_result.all():
            delivery_counts.setdefault(str(stream_id), {})[status] = count
        latest_result = await db.execute(
            select(KickWebhookEvent)
            .where(KickWebhookEvent.stream_id.in_(stream_ids))
            .order_by(KickWebhookEvent.received_at.desc())
            .limit(1000)
        )
        for event in latest_result.scalars().all():
            latest_delivery.setdefault(str(event.stream_id), event)
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
                "webhook_subscriptions": (s.settings or {}).get("kick_webhook_subscriptions", []),
                "webhook_subscriptions_verified": (s.settings or {}).get("kick_webhook_subscriptions_verified", False),
                "webhook_last_checked_at": (s.settings or {}).get("kick_webhook_subscriptions_checked_at"),
                "webhook_subscription_error": (s.settings or {}).get("kick_webhook_subscription_error"),
                "webhook_deliveries": {
                    "pending": delivery_counts.get(str(s.id), {}).get("pending", 0),
                    "processing": delivery_counts.get(str(s.id), {}).get("processing", 0),
                    "processed": delivery_counts.get(str(s.id), {}).get("processed", 0),
                    "ignored": delivery_counts.get(str(s.id), {}).get("ignored", 0),
                    "failed": delivery_counts.get(str(s.id), {}).get("failed", 0),
                    "last_event_type": (
                        latest_delivery[str(s.id)].event_type if str(s.id) in latest_delivery else None
                    ),
                    "last_status": (
                        latest_delivery[str(s.id)].processing_status
                        if str(s.id) in latest_delivery
                        else None
                    ),
                    "last_processing_error": (
                        latest_delivery[str(s.id)].last_error
                        if str(s.id) in latest_delivery
                        else None
                    ),
                    "last_received_at": (
                        latest_delivery[str(s.id)].received_at.isoformat()
                        if str(s.id) in latest_delivery
                        and latest_delivery[str(s.id)].received_at
                        else None
                    ),
                },
                "can_disconnect": s.owner_id == current_user.id or current_user.role in (
                    UserRole.ADMIN,
                    UserRole.SUPER_ADMIN,
                ),
            }
            for s in streams
        ],
    }


@router.post("/events/{message_id}/retry")
async def retry_kick_webhook_event(
    message_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KickWebhookEvent, Stream)
        .join(Stream, KickWebhookEvent.stream_id == Stream.id)
        .where(
            KickWebhookEvent.message_id == message_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    pair = result.first()
    if not pair:
        raise NotFoundError("Kick webhook event")
    event, stream = pair
    if stream.owner_id != current_user.id and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise AuthorizationError("Only the account owner or a tenant administrator can retry webhook processing")
    if event.processing_status not in ("failed", "pending"):
        raise ValidationError("Only pending or failed Kick deliveries can be retried")
    event.processing_status = "pending"
    event.processing_attempts = 0
    event.last_error = None
    db.add(
        AuditLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="kick.webhook.event_retried",
            resource_type="kick_webhook_event",
            resource_id=event.message_id,
            details={"stream_id": str(stream.id)},
        )
    )
    await db.commit()
    from app.events.queue import enqueue_kick_webhook_job

    job_id = await enqueue_kick_webhook_job(str(event.id))
    if not job_id:
        return {"status": "pending", "queued": False}
    return {"status": "pending", "queued": True}


@router.post("/subscriptions/reconcile")
async def reconcile_kick_subscriptions(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.KICK,
        )
    )
    streams = result.scalars().all()
    oauth = KickOAuth()
    outcomes = []
    for stream in streams:
        if stream.owner_id != current_user.id and current_user.role not in (
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
        ):
            outcomes.append({"stream_id": str(stream.id), "status": "not_authorized"})
            continue
        if (stream.settings or {}).get("is_owned") and not stream.oauth_token_encrypted:
            outcomes.append({"stream_id": str(stream.id), "status": "not_connected"})
            continue
        try:
            from app.services.platforms.oauth_tokens import get_stream_access_token

            token = await get_stream_access_token(stream)
            app_token = token is None
            token = token or await oauth.get_app_access_token()
            subscriptions = await oauth.reconcile_event_subscriptions(
                token,
                str(stream.external_id) if app_token else None,
                previously_requested=(stream.settings or {}).get("kick_webhook_subscriptions", []),
                requested_at=(stream.settings or {}).get("kick_webhook_subscriptions_requested_at"),
            )
            meta = dict(stream.settings or {})
            meta["kick_webhook_subscriptions"] = (
                subscriptions.get("subscribed", []) + subscriptions.get("created", [])
                + subscriptions.get("assumed", [])
            )
            if subscriptions.get("created"):
                meta["kick_webhook_subscriptions_requested_at"] = datetime.now(timezone.utc).isoformat()
            meta["kick_webhook_subscriptions_verified"] = bool(
                subscriptions.get("verified_by_api")
            )
            meta["kick_webhook_subscription_error"] = (
                ",".join(subscriptions.get("failed", [])) or None
            )
            meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
            meta["kick_chat_webhook_subscribed"] = (
                "chat.message.sent" in meta["kick_webhook_subscriptions"]
            )
            meta["kick_webhook_enabled"] = bool(meta["kick_webhook_subscriptions"])
            meta["kick_webhook_callback_url"] = settings.kick_webhook_callback_url
            stream.settings = meta
            outcomes.append(
                {
                    "stream_id": str(stream.id),
                    "status": "partial" if subscriptions.get("failed") else "reconciled",
                    "created": subscriptions.get("created", []),
                    "failed": subscriptions.get("failed", []),
                    "verified_by_api": subscriptions.get("verified_by_api", False),
                }
            )
        except Exception as exc:
            meta = dict(stream.settings or {})
            meta["kick_webhook_subscription_error"] = type(exc).__name__
            meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
            stream.settings = meta
            outcomes.append({"stream_id": str(stream.id), "status": "failed"})
            logger.warning(
                "kick_subscription_manual_reconcile_failed",
                stream_id=str(stream.id),
                error_type=type(exc).__name__,
            )
    db.add(
        AuditLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="kick.webhook.subscriptions_reconciled",
            resource_type="kick_webhook_subscription",
            details={"stream_count": len(streams)},
        )
    )
    await db.commit()
    return {"callback_url": settings.kick_webhook_callback_url, "streams": outcomes}


@router.delete("/disconnect/{stream_id}")
async def disconnect_kick_account(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.KICK,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise NotFoundError("Kick account")
    if stream.owner_id != current_user.id and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise AuthorizationError("Only the account owner or a tenant administrator can disconnect it")

    from app.services.platforms.oauth_revocation import disconnect_stream_account

    possible_shared_streams = await db.scalars(
        select(Stream)
        .where(
            Stream.platform == Platform.KICK,
            Stream.external_id == stream.external_id,
            Stream.id != stream.id,
        )
    )
    shared_stream = next(
        (
            other
            for other in possible_shared_streams.all()
            if not (
                (other.settings or {}).get("is_owned")
                and not other.oauth_token_encrypted
            )
            and bool(
                (other.settings or {}).get(
                    "kick_webhook_enabled",
                    (other.settings or {}).get("kick_chat_webhook_subscribed", False),
                )
            )
        ),
        None,
    )
    response = await disconnect_stream_account(
        stream,
        unsubscribe_kick_webhooks=shared_stream is None,
    )
    response["shared_broadcaster_subscription_kept"] = shared_stream is not None
    await db.execute(
        delete(KickWebhookEvent).where(KickWebhookEvent.stream_id == stream.id)
    )
    await db.commit()
    return response


async def _fetch_kick_profile_public(access_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.kick.com/public/v1/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if response.status_code == 200:
                return response.json()
    except httpx.HTTPError:
        pass
    return {}
