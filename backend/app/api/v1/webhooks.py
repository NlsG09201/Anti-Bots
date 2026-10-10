from fastapi import APIRouter, Depends, Header, Request, Response
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import time
import httpx

from app.api.v1.schemas import EventIngest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.bus import get_event_bus, ingest_event
from app.events.schemas import PipelineEvent
from app.integrations.twitch.eventsub import TwitchEventSubClient
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import get_db

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
_kick_public_key = None
_kick_public_key_loaded_at = 0.0
_kick_memory_event_ids: dict[str, float] = {}

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
            select(Stream).where(Stream.external_id == str(broadcaster_id))
        )
        stream = result.scalar_one_or_none()
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

    return Response(status_code=204)


async def _get_kick_public_key():
    global _kick_public_key, _kick_public_key_loaded_at
    if _kick_public_key is not None and time.monotonic() - _kick_public_key_loaded_at < 3600:
        return _kick_public_key
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://api.kick.com/public/v1/public-key")
        response.raise_for_status()
        public_key_text = response.json().get("data", {}).get("public_key")
        if not public_key_text:
            raise ValueError("Kick no devolvió su clave pública")
        _kick_public_key = serialization.load_pem_public_key(public_key_text.encode())
        if not isinstance(_kick_public_key, rsa.RSAPublicKey):
            raise ValueError("El tipo de clave pública de Kick no es compatible")
        _kick_public_key_loaded_at = time.monotonic()
    return _kick_public_key


@router.post("/kick")
async def kick_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    event_id: str = Header("", alias="Kick-Event-Message-Id"),
    timestamp: str = Header("", alias="Kick-Event-Message-Timestamp"),
    signature: str = Header("", alias="Kick-Event-Signature"),
    event_type: str = Header("", alias="Kick-Event-Type"),
):
    body = await request.body()
    if not event_id or not timestamp or not signature:
        return Response(status_code=400)
    try:
        key = await _get_kick_public_key()
        key.verify(
            base64.b64decode(signature, validate=True),
            f"{event_id}.{timestamp}.".encode() + body,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError):
        return Response(status_code=403)
    except Exception as exc:
        logger.error("kick_webhook_key_unavailable", error=str(exc)[:160])
        return Response(status_code=503)

    if event_type != "chat.message.sent":
        return Response(status_code=204)

    try:
        payload = await request.json()
        broadcaster = payload.get("broadcaster") or {}
        sender = payload.get("sender") or {}
        broadcaster_id = str(broadcaster.get("user_id") or "")
        sender_id = str(sender.get("user_id") or "")
        username = sender.get("username")
        if not broadcaster_id or not (sender_id or username):
            return Response(status_code=204)
        result = await db.execute(
            select(Stream).where(
                Stream.platform == Platform.KICK,
                Stream.external_id == broadcaster_id,
            )
        )
        stream = result.scalar_one_or_none()
        if not stream:
            return Response(status_code=204)

        # Kick retries webhook delivery. Reserve the event ID before ingest and
        # release it if persistence fails so a retry can safely process it.
        from app.infrastructure.cache.redis_client import optional_get_redis

        redis = await optional_get_redis()
        cache_key = f"kick-webhook-event:{event_id}"
        if redis:
            reserved = await redis.set(cache_key, "processing", ex=86400, nx=True)
            if not reserved:
                return Response(status_code=204)
        else:
            now = time.monotonic()
            expired = [key for key, expires in _kick_memory_event_ids.items() if expires <= now]
            for key in expired:
                _kick_memory_event_ids.pop(key, None)
            if event_id in _kick_memory_event_ids:
                return Response(status_code=204)
            _kick_memory_event_ids[event_id] = now + 86400

        from app.api.v1.schemas import EventIngest

        message = payload.get("content") or (payload.get("message") or {}).get("content")
        await ingest_event(
            db,
            stream,
            stream.tenant_id,
            EventIngest(
                event_type="chat_message",
                platform_user_id=sender_id or None,
                platform_username=username,
                metadata={
                    "content": message,
                    "kick_event_id": event_id,
                    "kick_event_type": event_type,
                    "timestamp": timestamp,
                },
            ),
            source="platform_kick",
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if "redis" in locals() and redis:
            await redis.delete(cache_key)
        else:
            _kick_memory_event_ids.pop(event_id, None)
        logger.exception("kick_webhook_ingest_failed", event_id=event_id, error_type=type(exc).__name__)
        return Response(status_code=503)

    return Response(status_code=204)
