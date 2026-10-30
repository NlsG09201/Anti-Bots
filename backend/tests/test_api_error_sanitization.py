from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.oauth_errors import oauth_exchange_public_message


def test_oauth_status_error_message_does_not_expose_provider_response_or_url():
    secret = "oauth-client-secret-value"
    request = httpx.Request(
        "POST",
        f"https://provider.example/token?access_token={secret}",
    )
    response = httpx.Response(
        401,
        request=request,
        text=f'{{"error_description":"invalid secret {secret}"}}',
    )
    error = httpx.HTTPStatusError("provider response", request=request, response=response)

    message = oauth_exchange_public_message("Twitch", error)

    assert "Twitch" in message
    assert "401" in message
    assert secret not in message
    assert "invalid secret" not in message


def test_oauth_transport_error_message_does_not_expose_request_url():
    secret = "oauth-client-secret-value"
    request = httpx.Request("POST", f"https://provider.example/token?code={secret}")
    error = httpx.ConnectError(f"failed to reach {request.url}", request=request)

    message = oauth_exchange_public_message("Kick", error)

    assert "Kick" in message
    assert "token" not in message
    assert secret not in message


@pytest.mark.asyncio
async def test_powerbi_sync_returns_generic_error_without_provider_details(monkeypatch):
    from app.api.v1 import powerbi_analytics

    secret = "powerbi-client-secret-value"

    class FailingWarehouse:
        def __init__(self, *_args, **_kwargs):
            self.snapshot_at = None

        async def build_export_bundle(self):
            raise RuntimeError(f"provider failure: {secret}")

    monkeypatch.setattr(powerbi_analytics, "AnalyticsWarehouseService", FailingWarehouse)

    with pytest.raises(HTTPException) as error:
        await powerbi_analytics.analytics_powerbi_sync(
            SimpleNamespace(tenant_id=uuid4()),
            db=object(),
            hours=24,
        )

    assert error.value.status_code == 503
    assert secret not in repr(error.value.detail)
    assert error.value.detail["error"] == "sync_failed"
