from fastapi import APIRouter, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.twitch.eventsub import TwitchEventSubClient
from app.infrastructure.database.session import get_db
from fastapi import Depends

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


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
        from app.workers.tasks import process_stream_event
        process_stream_event.delay(
            stream_id=event.get("broadcaster_id", ""),
            event_data={
                "event_type": event["type"],
                "platform_user_id": event.get("user_id"),
                "platform_username": event.get("username"),
                "timestamp": event.get("timestamp"),
                "metadata": event.get("event", {}),
            },
        )

    return Response(status_code=204)
