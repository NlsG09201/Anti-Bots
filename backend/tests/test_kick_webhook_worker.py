from datetime import datetime, timezone
import base64
from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.workers import arq_worker


@pytest.mark.asyncio
async def test_kick_signature_verifies_signed_headers_and_raw_body(monkeypatch):
    from app.api.v1 import webhooks

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    message_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    timestamp = "2026-10-30T12:00:00Z"
    body = b'{"event":"chat.message.sent"}'
    signed_message = f"{message_id}.{timestamp}.".encode() + body
    signature = private_key.sign(signed_message, padding.PKCS1v15(), hashes.SHA256())
    monkeypatch.setattr(webhooks, "_get_kick_public_key", AsyncMock(return_value=public_key))
    monkeypatch.setattr(webhooks, "_kick_public_key_loaded_at", 0.0)

    assert await webhooks._verify_kick_signature(
        message_id, timestamp, base64.b64encode(signature).decode(), body
    )
    assert not await webhooks._verify_kick_signature(
        message_id, timestamp, base64.b64encode(signature).decode(), body + b" "
    )


class _Session:
    def __init__(self, scalar_results):
        self.scalar = AsyncMock(side_effect=scalar_results)
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def add(self, _value):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempts", "expected_status", "expected_attempts"),
    [(3, "pending", 4), (9, "failed", 10)],
)
async def test_kick_processing_failure_counts_one_attempt(
    monkeypatch, attempts, expected_status, expected_attempts
):
    event = SimpleNamespace(
        id=uuid4(),
        stream_id=uuid4(),
        processing_status="pending",
        processing_attempts=attempts,
        raw_payload={"sender": {"user_id": "user-1", "username": "viewer"}, "content": "hello"},
        event_type="chat.message.sent",
        message_id="event-1",
        event_version="1",
        message_timestamp=datetime.now(timezone.utc),
        last_error=None,
    )
    stream = SimpleNamespace(
        id=event.stream_id,
        tenant_id=uuid4(),
        settings={},
        is_live=False,
    )
    sessions = [
        _Session([event, stream]),
        _Session([event]),
    ]
    monkeypatch.setattr(
        "app.infrastructure.database.session.AsyncSessionLocal",
        lambda: sessions.pop(0),
    )
    process = AsyncMock(side_effect=RuntimeError("temporary processor failure"))
    monkeypatch.setattr(
        "app.services.ingest.event_ingest.process_stream_event", process
    )

    with pytest.raises(RuntimeError, match="temporary processor failure"):
        await arq_worker.process_kick_webhook_event_job({}, str(event.id))

    assert event.processing_attempts == expected_attempts
    assert event.processing_status == expected_status
    assert event.last_error == "RuntimeError"
    process.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_kick_delivery_is_not_automatically_reprocessed(monkeypatch):
    event = SimpleNamespace(id=uuid4(), processing_status="failed")
    session = _Session([event])
    monkeypatch.setattr(
        "app.infrastructure.database.session.AsyncSessionLocal",
        lambda: session,
    )

    result = await arq_worker.process_kick_webhook_event_job({}, str(event.id))

    assert result == {"status": "failed"}
    session.scalar.assert_awaited_once()
