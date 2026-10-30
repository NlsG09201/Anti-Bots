"""Security checks for Twitch EventSub webhook verification."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from unittest.mock import patch

import pytest
from httpx import AsyncClient


def _headers(timestamp: str, *, signature: str = "sha256=test") -> dict[str, str]:
    return {
        "Twitch-Eventsub-Message-Id": "eventsub-message-1",
        "Twitch-Eventsub-Message-Timestamp": timestamp,
        "Twitch-Eventsub-Message-Signature": signature,
        "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
    }


@pytest.mark.asyncio
async def test_twitch_callback_challenge_requires_valid_signature(client: AsyncClient):
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = b'{"challenge":"challenge-value"}'

    with patch(
        "app.api.v1.webhooks.TwitchEventSubClient.verify_signature",
        return_value=False,
    ) as verify:
        rejected = await client.post(
            "/api/v1/webhooks/twitch",
            content=payload,
            headers=_headers(timestamp),
        )

    assert rejected.status_code == 403
    verify.assert_called_once()

    with patch(
        "app.api.v1.webhooks.TwitchEventSubClient.verify_signature",
        return_value=True,
    ):
        accepted = await client.post(
            "/api/v1/webhooks/twitch",
            content=payload,
            headers=_headers(timestamp),
        )

    assert accepted.status_code == 200
    assert accepted.json() == {"challenge": "challenge-value"}


@pytest.mark.asyncio
async def test_twitch_webhook_rejects_stale_signed_message(client: AsyncClient):
    timestamp = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()

    with patch(
        "app.api.v1.webhooks.TwitchEventSubClient.verify_signature",
        return_value=True,
    ) as verify:
        response = await client.post(
            "/api/v1/webhooks/twitch",
            content=b'{"challenge":"challenge-value"}',
            headers=_headers(timestamp),
        )

    assert response.status_code == 403
    verify.assert_not_called()


def test_twitch_signature_verification_fails_without_a_secret():
    from app.integrations.twitch.eventsub import TwitchEventSubClient

    with patch("app.integrations.twitch.eventsub.settings.twitch_webhook_secret", ""):
        assert not TwitchEventSubClient.verify_signature("id", "timestamp", b"body", "sha256=anything")


def test_twitch_signature_verification_uses_message_id_timestamp_and_raw_body():
    from app.integrations.twitch.eventsub import TwitchEventSubClient

    message_id = "message-id"
    timestamp = "2026-10-29T12:00:00Z"
    body = b'{"event":"payload"}'
    secret = "a-random-test-secret"
    digest = hmac.new(
        secret.encode(), message_id.encode() + timestamp.encode() + body, hashlib.sha256
    ).hexdigest()

    with patch("app.integrations.twitch.eventsub.settings.twitch_webhook_secret", secret):
        assert TwitchEventSubClient.verify_signature(
            message_id, timestamp, body, f"sha256={digest}"
        )
        assert not TwitchEventSubClient.verify_signature(
            message_id, timestamp, body + b"x", f"sha256={digest}"
        )
