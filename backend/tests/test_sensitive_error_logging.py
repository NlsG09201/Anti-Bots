from types import SimpleNamespace

import httpx
import pytest


class CapturingLogger:
    def __init__(self):
        self.calls = []

    def warning(self, event, **fields):
        self.calls.append((event, fields))

    def error(self, event, **fields):
        self.calls.append((event, fields))


class FailingHttpClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        raise httpx.ConnectError(f"connection failed for {url}")


@pytest.mark.asyncio
async def test_alert_webhook_failure_does_not_log_secret_url(monkeypatch):
    from app.services import alert_engine

    secret_url = "https://hooks.example.test/webhook/123/token-secret"
    captured_logger = CapturingLogger()
    monkeypatch.setattr(alert_engine.settings, "alert_webhook_urls", secret_url)
    monkeypatch.setattr(alert_engine, "logger", captured_logger)
    monkeypatch.setattr(httpx, "AsyncClient", FailingHttpClient)

    engine = alert_engine.AlertEngine.__new__(alert_engine.AlertEngine)
    await engine._send_webhook_notifications(SimpleNamespace(to_dict=lambda: {}))

    rendered_logs = repr(captured_logger.calls)
    assert secret_url not in rendered_logs
    assert captured_logger.calls[0][1] == {"error_type": "ConnectError"}


@pytest.mark.asyncio
async def test_discord_webhook_failure_does_not_log_secret_url(monkeypatch):
    from app.integrations.discord import webhook

    secret_url = "https://discord.com/api/webhooks/123/token-secret"
    captured_logger = CapturingLogger()
    monkeypatch.setattr(webhook, "logger", captured_logger)
    monkeypatch.setattr(httpx, "AsyncClient", FailingHttpClient)

    notifier = webhook.DiscordNotifier(webhook_url=secret_url)
    assert await notifier.send_alert("title", "message") is False

    rendered_logs = repr(captured_logger.calls)
    assert secret_url not in rendered_logs
    assert captured_logger.calls[0][1] == {"error_type": "ConnectError"}


@pytest.mark.asyncio
async def test_database_connect_failure_does_not_log_exception_message(monkeypatch):
    from app.infrastructure.database import init_db

    secret = "database-password-that-must-not-be-logged"
    captured_logger = CapturingLogger()
    monkeypatch.setattr(init_db, "logger", captured_logger)

    class FailedTransaction:
        async def __aenter__(self):
            raise RuntimeError(f"connection failed with password={secret}")

        async def __aexit__(self, *args):
            return False

    class FailedEngine:
        def begin(self):
            return FailedTransaction()

    with pytest.raises(RuntimeError):
        await init_db.init_database(FailedEngine(), max_attempts=1)

    rendered_logs = repr(captured_logger.calls)
    assert secret not in rendered_logs
    assert captured_logger.calls[0][1]["error_type"] == "RuntimeError"
