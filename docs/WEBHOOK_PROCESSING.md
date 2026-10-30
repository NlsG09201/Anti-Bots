# Webhook processing

## Supported inbound provider events

| Provider | Current inbound events | Acceptance and processing |
| --- | --- | --- |
| Twitch EventSub | `channel.follow`, `channel.subscribe`, `channel.chat.message`, `stream.online`, `stream.offline` | HMAC signature and timestamp checks; message-ID replay protection in Redis; notifications enter the existing Redis Streams pipeline before HTTP 204. Chat moderation rules run after event publication. |
| Kick Events API | Events in `KICK_WEBHOOK_EVENTS` (`chat.message.sent`, follows, subscriptions, gifts, stream status/metadata, bans, rewards) | ULID/header checks, timestamp window, Kick public-key RSA signature verification; accepted payload is committed to `kick_webhook_events` before enqueue/HTTP 204. Worker processing is retried and pending rows are periodically recovered; permanently failed rows require an authorized manual retry. |

Twitch documents at-least-once webhook delivery, message-ID deduplication, and a 10-minute timestamp window. Kick documents an event-message ID as the idempotency key and public-key signature verification. The handlers enforce those controls and use bounded request bodies. Avoid logging raw webhook payloads or credentials.

## Not currently wired to moderation webhooks

There is no YouTube or TikTok moderation webhook receiver in this application. YouTube live chat uses its Live Streaming API (`liveChatMessages`/`streamList`) rather than a webhook route here. TikTok's documented webhook events include authorization removal and video publishing/upload notifications, not live chat moderation events; the existence of TikTok webhooks does not make them an available moderation feed. Do not subscribe to unsupported event types.

## Operational requirements and limits

- Keep Redis available for Twitch idempotency and its event pipeline; in production a missing Redis configuration returns 503 rather than acknowledging notifications without replay protection.
- Keep the Kick worker enabled. Its database inbox protects accepted payloads if queueing or the worker is temporarily unavailable; the recovery job re-enqueues pending rows.
- Kick raw payloads are retained only for the configured short retention window and then purged by the worker. Preserve the database backup/recovery process for inbox durability.
- Event ordering across streams is not guaranteed by the provider integrations; workers prioritize suspicious events but may process independent events concurrently.
- Subscription creation and reconciliation use provider APIs only when credentials and required scopes are configured. Confirm the provider's subscription status in the integration diagnostics after setup.

## Verification

Run `pytest tests/test_twitch_webhook_security.py tests/test_kick_webhook_worker.py tests/test_event_queue.py -q` from `backend/` for signature, replay, retry, and queue behavior checks.
