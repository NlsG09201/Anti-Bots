"""Security checks for Twitch EventSub webhook verification."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_twitch_webhook_suppresses_completed_duplicate(client: AsyncClient):
    timestamp = datetime.now(timezone.utc).isoformat()
    headers = _headers(timestamp)
    headers["Twitch-Eventsub-Message-Type"] = "notification"
    headers["Twitch-Eventsub-Subscription-Type"] = "channel.follow"
    claim = AsyncMock(side_effect=[True, False])

    with (
        patch(
            "app.api.v1.webhooks.TwitchEventSubClient.verify_signature",
            return_value=True,
        ),
        patch("app.api.v1.webhooks.RedisCache.set_if_absent", new=claim),
        patch(
            "app.api.v1.webhooks.RedisCache.get",
            new_callable=AsyncMock,
            return_value="completed",
        ),
        patch("app.api.v1.webhooks.RedisCache.set", new_callable=AsyncMock),
        patch(
            "app.api.v1.webhooks._process_twitch_notification",
            new_callable=AsyncMock,
        ) as process,
    ):
        first = await client.post("/api/v1/webhooks/twitch", content=b"{}", headers=headers)
        duplicate = await client.post("/api/v1/webhooks/twitch", content=b"{}", headers=headers)

    assert first.status_code == 204
    assert duplicate.status_code == 204
    process.assert_awaited_once()
    assert claim.await_args_list[0].kwargs["ttl"] >= 600 + 30


@pytest.mark.asyncio
async def test_twitch_webhook_releases_failed_claim_for_retry(client: AsyncClient):
    timestamp = datetime.now(timezone.utc).isoformat()
    headers = _headers(timestamp)
    headers["Twitch-Eventsub-Message-Type"] = "notification"
    headers["Twitch-Eventsub-Subscription-Type"] = "channel.follow"

    with (
        patch(
            "app.api.v1.webhooks.TwitchEventSubClient.verify_signature",
            return_value=True,
        ),
        patch(
            "app.api.v1.webhooks.RedisCache.set_if_absent",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.api.v1.webhooks.RedisCache.delete", new_callable=AsyncMock) as delete,
        patch("app.api.v1.webhooks.RedisCache.set", new_callable=AsyncMock),
        patch(
            "app.api.v1.webhooks._process_twitch_notification",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("queue unavailable"), None],
        ) as process,
    ):
        failed = await client.post("/api/v1/webhooks/twitch", content=b"{}", headers=headers)
        retried = await client.post("/api/v1/webhooks/twitch", content=b"{}", headers=headers)

    assert failed.status_code == 503
    assert retried.status_code == 204
    delete.assert_awaited_once()
    assert process.await_count == 2


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
