from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, Header, Request, Response
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import time
import httpx
from sqlalchemy.exc import IntegrityError

from app.api.v1.schemas import EventIngest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.bus import get_event_bus, ingest_event
from app.events.schemas import PipelineEvent
from app.integrations.twitch.eventsub import TwitchEventSubClient
from app.infrastructure.database.models import KickWebhookEvent, Platform, Stream
from app.infrastructure.database.session import get_db
from app.integrations.kick.oauth import KICK_WEBHOOK_EVENTS

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
_kick_public_key = None
_kick_public_key_loaded_at = 0.0
KICK_EVENT_TYPES = frozenset(KICK_WEBHOOK_EVENTS)
_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_KICK_FUTURE_TOLERANCE_SECONDS = 300
_KICK_MAX_DELIVERY_AGE_SECONDS = 86_400
_KICK_MAX_BODY_BYTES = 1_048_576

EVENTSUB_TO_INGEST = {
    "channel.follow": "follow",
    "channel.chat.message": "chat_message",
    "stream.online": "viewer_join",
    "stream.offline": "viewer_leave",
    "channel.subscribe": "follow",
}


@router.post("/twitch")
async def twitch_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    twitch_eventsub_message_id: str = Header(None, alias="Twitch-Eventsub-Message-Id"),
    twitch_eventsub_message_timestamp: str = Header(None, alias="Twitch-Eventsub-Message-Timestamp"),
    twitch_eventsub_message_signature: str = Header(None, alias="Twitch-Eventsub-Message-Signature"),
    twitch_eventsub_message_type: str = Header(None, alias="Twitch-Eventsub-Message-Type"),
):
    body = await request.body()

    if twitch_eventsub_message_type == "webhook_callback_verification":
        data = await request.json()
        return {"challenge": data.get("challenge")}

    if not TwitchEventSubClient.verify_signature(
        twitch_eventsub_message_id or "",
        twitch_eventsub_message_timestamp or "",
        body,
        twitch_eventsub_message_signature or "",
    ):
        return Response(status_code=403)

    if twitch_eventsub_message_type == "notification":
        payload = await request.json()
        event = TwitchEventSubClient.parse_event(
            {
                "twitch-eventsub-subscription-type": request.headers.get(
                    "Twitch-Eventsub-Subscription-Type", ""
                ),
                "twitch-eventsub-message-timestamp": twitch_eventsub_message_timestamp or "",
            },
            payload,
        )
        logger.info("twitch_event_received", event_type=event["type"])

        broadcaster_id = event.get("broadcaster_id") or ""
        if not broadcaster_id:
            return Response(status_code=204)

        result = await db.execute(
            select(Stream).where(
                Stream.external_id == str(broadcaster_id),
                Stream.platform == Platform.TWITCH,
            )
        )
        candidate_streams = result.scalars().all()
        subscription_user_id = str(event.get("chat_user_id") or "")
        stream = next(
            (
                item for item in candidate_streams
                if subscription_user_id
                and str((item.settings or {}).get("twitch_bot_user_id") or "") == subscription_user_id
            ),
            None,
        )
        if not stream:
            stream = next(
                (
                    item for item in candidate_streams
                    if not (item.settings or {}).get("twitch_bot_access_token_encrypted")
                ),
                candidate_streams[0] if candidate_streams else None,
            )
        if not stream:
            logger.warning("twitch_webhook_stream_not_found", broadcaster_id=broadcaster_id)
            return Response(status_code=204)

        ingest_type = EVENTSUB_TO_INGEST.get(event["type"], event["type"])
        event_ingest = EventIngest(
            event_type=ingest_type,
            platform_user_id=event.get("user_id"),
            platform_username=event.get("username"),
            metadata={
                "timestamp": event.get("timestamp"),
                "eventsub_type": event["type"],
                **(event.get("event") or {}),
            },
        )

        if settings.event_pipeline_enabled:
            bus = get_event_bus()
            pipeline_event = PipelineEvent.from_ingest(
                stream_id=stream.id,
                tenant_id=stream.tenant_id,
                event_type=ingest_type,
                platform_user_id=event_ingest.platform_user_id,
                platform_username=event_ingest.platform_username,
                metadata=event_ingest.metadata,
                source="twitch_eventsub",
            )
            await bus.publish(pipeline_event)
        else:
            await ingest_event(
                db,
                stream,
                stream.tenant_id,
                event_ingest,
                source="twitch_eventsub",
            )
            await db.commit()

        if event["type"] == "channel.chat.message":
            try:
                from app.services.twitch_chat_moderation import process_twitch_chat_message

                await process_twitch_chat_message(db, stream, event.get("event") or {})
            except Exception as exc:
                logger.exception(
                    "twitch_chat_moderation_processing_failed",
                    stream_id=str(stream.id),
                    error_type=type(exc).__name__,
                )

    return Response(status_code=204)


async def _get_kick_public_key(*, force_refresh: bool = False):
    global _kick_public_key, _kick_public_key_loaded_at
    if (
        not force_refresh
        and _kick_public_key is not None
        and time.monotonic() - _kick_public_key_loaded_at < 900
    ):
        return _kick_public_key
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://api.kick.com/public/v1/public-key")
        response.raise_for_status()
        try:
            key_response = response.json()
        except ValueError:
            key_response = {}
        public_key_text = (
            (key_response.get("data") or {}).get("public_key")
            if isinstance(key_response, dict)
            else None
        )
        public_key_text = public_key_text or response.text.strip()
        if not public_key_text:
            raise ValueError("Kick no devolvió su clave pública")
        _kick_public_key = serialization.load_pem_public_key(public_key_text.encode())
        if not isinstance(_kick_public_key, rsa.RSAPublicKey):
            raise ValueError("El tipo de clave pública de Kick no es compatible")
        _kick_public_key_loaded_at = time.monotonic()
    return _kick_public_key


async def _verify_kick_signature(event_id: str, timestamp: str, signature: str, body: bytes) -> bool:
    signed_message = f"{event_id}.{timestamp}.".encode() + body
    decoded = base64.b64decode(signature, validate=True)
    for refresh in (False, True):
        key = await _get_kick_public_key(force_refresh=refresh)
        try:
            key.verify(decoded, signed_message, padding.PKCS1v15(), hashes.SHA256())
            return True
        except InvalidSignature:
            if refresh:
                return False
            if time.monotonic() - _kick_public_key_loaded_at < 30:
                return False
    return False


async def _read_limited_body(request: Request, max_bytes: int) -> bytes | None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            return None
    return bytes(body)


@router.post("/kick")
async def kick_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    event_id: str = Header("", alias="Kick-Event-Message-Id"),
    timestamp: str = Header("", alias="Kick-Event-Message-Timestamp"),
    signature: str = Header("", alias="Kick-Event-Signature"),
    event_type: str = Header("", alias="Kick-Event-Type"),
    event_version: str = Header("", alias="Kick-Event-Version"),
    subscription_id: str = Header("", alias="Kick-Event-Subscription-Id"),
):
    body = await _read_limited_body(request, _KICK_MAX_BODY_BYTES)
    if body is None:
        return Response(status_code=413)
    if (
        not _ULID_PATTERN.fullmatch(event_id)
        or not timestamp
        or not signature
        or not event_type
        or not event_version
        or (subscription_id and not _ULID_PATTERN.fullmatch(subscription_id))
    ):
        return Response(status_code=400)
    try:
        sent_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if sent_at.tzinfo is None:
            return Response(status_code=400)
        age = (datetime.now(timezone.utc) - sent_at.astimezone(timezone.utc)).total_seconds()
        if age < -_KICK_FUTURE_TOLERANCE_SECONDS or age > _KICK_MAX_DELIVERY_AGE_SECONDS:
            logger.warning("kick_webhook_rejected", reason="timestamp_outside_tolerance", event_id=event_id)
            return Response(status_code=403)
        if not await _verify_kick_signature(event_id, timestamp, signature, body):
            logger.warning("kick_webhook_rejected", reason="invalid_signature", event_id=event_id)
            return Response(status_code=403)
    except (InvalidSignature, ValueError, TypeError):
        return Response(status_code=403)
    except Exception as exc:
        logger.error("kick_webhook_key_unavailable", error_type=type(exc).__name__)
        return Response(status_code=503)

    if event_type not in KICK_EVENT_TYPES or event_version != "1":
        logger.warning(
            "kick_webhook_unsupported_event",
            event_id=event_id,
            event_type=event_type,
            event_version=event_version,
        )
        # Acknowledge signed, future event types to avoid a retry loop that can
        # cause Kick to disable delivery for currently supported subscriptions.
        return Response(status_code=204)

    try:
        import json

        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return Response(status_code=400)
        if not isinstance(payload, dict):
            return Response(status_code=400)
        broadcaster = payload.get("broadcaster") or {}
        broadcaster_id = str(broadcaster.get("user_id") or "")
        if not broadcaster_id.isdigit():
            return Response(status_code=400)
        result = await db.execute(
            select(Stream).where(
                Stream.platform == Platform.KICK,
                Stream.external_id == broadcaster_id,
            )
        )
        streams = list(result.scalars().all())
        pending_events = []
        if not streams:
            db.add(
                KickWebhookEvent(
                    message_id=event_id,
                    subscription_id=subscription_id or None,
                    stream_id=None,
                    broadcaster_user_id=broadcaster_id,
                    event_type=event_type,
                    event_version=event_version,
                    message_timestamp=sent_at.astimezone(timezone.utc),
                    raw_payload=payload,
                    processing_status="ignored",
                )
            )
        else:
            for stream in streams:
                existing = await db.scalar(
                    select(KickWebhookEvent).where(
                        KickWebhookEvent.message_id == event_id,
                        KickWebhookEvent.stream_id == stream.id,
                    )
                )
                if existing:
                    if existing.processing_status == "pending":
                        pending_events.append(existing)
                    continue
                stream_settings = dict(stream.settings or {})
                webhook_enabled = bool(
                    stream_settings.get(
                        "kick_webhook_enabled",
                        stream_settings.get("kick_chat_webhook_subscribed", False),
                    )
                )
                stored = KickWebhookEvent(
                    message_id=event_id,
                    subscription_id=subscription_id or None,
                    stream_id=stream.id,
                    broadcaster_user_id=broadcaster_id,
                    event_type=event_type,
                    event_version=event_version,
                    message_timestamp=sent_at.astimezone(timezone.utc),
                    raw_payload=payload,
                    processing_status="pending" if webhook_enabled else "ignored",
                )
                db.add(stored)
                if webhook_enabled:
                    pending_events.append(stored)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing_rows = await db.scalars(
                select(KickWebhookEvent).where(KickWebhookEvent.message_id == event_id)
            )
            pending_events = [
                row for row in existing_rows.all()
                if row.processing_status == "pending"
            ]
            if not pending_events:
                return Response(status_code=204)
        if not pending_events:
            logger.info("kick_webhook_untracked_broadcaster", event_id=event_id, event_type=event_type)
            return Response(status_code=204)

        from app.events.queue import enqueue_kick_webhook_job

        for stored in pending_events:
            job_id = await enqueue_kick_webhook_job(str(stored.id))
            if not job_id:
                logger.error(
                    "kick_webhook_enqueue_failed",
                    event_id=event_id,
                    event_type=event_type,
                    stream_id=str(stored.stream_id),
                )
                return Response(status_code=503)
        logger.info(
            "kick_webhook_accepted",
            event_id=event_id,
            event_type=event_type,
            stream_count=len(pending_events),
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("kick_webhook_persist_failed", event_id=event_id, error_type=type(exc).__name__)
        return Response(status_code=503)

    return Response(status_code=204)
