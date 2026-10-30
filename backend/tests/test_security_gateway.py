"""Tests de capa de seguridad: IP, headers, replay, rate limit."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from app.infrastructure.security.client_ip import resolve_client_ip
from app.infrastructure.security.headers import validate_request_headers
from app.infrastructure.security.replay import ReplayProtection


def _make_request(
    *,
    path: str = "/api/v1/auth/login",
    headers: dict | None = None,
    client_host: str = "203.0.113.10",
):
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
        "client": (client_host, 0),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_resolve_client_ip_trusts_cf_connecting_ip():
    req = _make_request(
        headers={"CF-Connecting-IP": "198.51.100.5", "X-Forwarded-For": "10.0.0.1"},
    )
    ip, meta = resolve_client_ip(req)
    assert ip == "198.51.100.5"
    assert meta["xff_spoof_risk"] is False


def test_resolve_client_ip_spoof_risk_without_trusted_forward():
    with patch("app.infrastructure.security.client_ip.settings") as mock_settings:
        mock_settings.security_trust_proxy_headers = False
        req = _make_request(
            client_host="203.0.113.10",
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        ip, meta = resolve_client_ip(req)
        assert ip == "203.0.113.10"
        assert meta["xff_spoof_risk"] is True


def test_headers_block_host_injection():
    req = _make_request(headers={"Host": "evil\r\nX-Injected: true", "User-Agent": "Mozilla/5.0"})
    result = validate_request_headers(req)
    assert result.allowed is False
    assert "host_header_anomaly" in result.flags


def test_headers_detect_automation_ua():
    req = _make_request(headers={"User-Agent": "python-requests/2.31"})
    result = validate_request_headers(req)
    assert result.automation_detected is True
    assert "automated_user_agent" in result.flags


@pytest.mark.asyncio
async def test_replay_rejects_duplicate_nonce():
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=False)
    rp = ReplayProtection(cache=cache)
    with pytest.raises(Exception) as exc:
        await rp.validate_request(
            scope="test",
            nonce="abc123",
            timestamp_ms=int(time.time() * 1000),
        )
    assert "Replay" in str(exc.value) or getattr(exc.value, "message", "")


@pytest.mark.asyncio
async def test_replay_accepts_fresh_nonce():
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=True)
    rp = ReplayProtection(cache=cache)
    await rp.validate_request(
        scope="test",
        nonce="fresh-nonce-xyz",
        timestamp_ms=int(time.time() * 1000),
    )
    cache.set_if_absent.assert_awaited_once()


@pytest.mark.asyncio
async def test_widget_hmac_mode_requires_signature_before_nonce_claim(monkeypatch):
    from app.infrastructure.security import replay

    monkeypatch.setattr(replay.settings, "security_widget_hmac_enabled", True)
    monkeypatch.setattr(replay.settings, "security_replay_protection_enabled", False)
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=True)
    protection = ReplayProtection(cache=cache)

    with pytest.raises(Exception, match="Missing X-SS-Signature"):
        await protection.validate_request(
            scope="widget:test",
            nonce="nonce-without-signature",
            timestamp_ms=int(time.time() * 1000),
            secret="test-widget-key",
        )
    cache.set_if_absent.assert_not_awaited()


@pytest.mark.asyncio
async def test_widget_hmac_validates_exact_request_body(monkeypatch):
    import hashlib
    import hmac

    from app.infrastructure.security import replay

    monkeypatch.setattr(replay.settings, "security_widget_hmac_enabled", True)
    timestamp_ms = int(time.time() * 1000)
    nonce = "signed-widget-nonce"
    body = b'{"stream_key":"test-key","event_type":"viewer_pulse"}'
    secret = "test-widget-key"
    signature = hmac.new(
        secret.encode(), f"{timestamp_ms}.{nonce}.".encode() + body, hashlib.sha256
    ).hexdigest()
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=True)

    await ReplayProtection(cache=cache).validate_request(
        scope="widget:test",
        nonce=nonce,
        timestamp_ms=timestamp_ms,
        signature=signature,
        body=body,
        secret=secret,
    )

    cache.set_if_absent.assert_awaited_once()


@pytest.mark.asyncio
async def test_replay_nonce_ttl_covers_full_accepted_timestamp_window(monkeypatch):
    from app.infrastructure.security import replay

    monkeypatch.setattr(replay.settings, "security_replay_protection_enabled", True)
    monkeypatch.setattr(replay.settings, "security_replay_max_skew_seconds", 120)
    monkeypatch.setattr(replay.settings, "security_replay_nonce_ttl_seconds", 30)
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=True)

    await ReplayProtection(cache=cache).validate_request(
        scope="widget:test",
        nonce="future-boundary-nonce",
        timestamp_ms=int(time.time() * 1000),
    )

    assert cache.set_if_absent.await_args.kwargs["ttl"] == 241


@pytest.mark.asyncio
async def test_replay_enabled_rejects_requests_missing_nonce_or_timestamp(monkeypatch):
    from app.infrastructure.security import replay

    monkeypatch.setattr(replay.settings, "security_replay_protection_enabled", True)
    monkeypatch.setattr(replay.settings, "security_replay_strict", False)
    cache = AsyncMock()
    cache.set_if_absent = AsyncMock(return_value=True)

    with pytest.raises(Exception, match="Missing X-SS-Nonce or X-SS-Timestamp"):
        await ReplayProtection(cache=cache).validate_request(
            scope="widget:test",
            nonce=None,
            timestamp_ms=None,
        )
    cache.set_if_absent.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_cache_set_if_absent_is_atomic_for_memory_backend(monkeypatch):
    from app.infrastructure.cache import redis_client

    monkeypatch.setattr(redis_client, "redis_cache_is_configured", lambda: False)
    cache = redis_client.RedisCache(prefix=f"test-{time.time_ns()}")

    assert await cache.set_if_absent("delivery", "processing", ttl=30)
    assert not await cache.set_if_absent("delivery", "processing", ttl=30)
    await cache.set("delivery", "completed", ttl=30)
    assert await cache.get("delivery") == "completed"


def test_security_gateway_blocks_scanner_paths():
    from app.infrastructure.security.gateway import SecurityGatewayMiddleware

    app = FastAPI()

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    app.add_middleware(SecurityGatewayMiddleware)
    client = TestClient(app)
    resp = client.get("/.env")
    assert resp.status_code == 404
