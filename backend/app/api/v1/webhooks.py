from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import EventIngest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.bus import get_event_bus, ingest_event
from app.events.schemas import PipelineEvent
from app.integrations.twitch.eventsub import TwitchEventSubClient
from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import get_db

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

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
