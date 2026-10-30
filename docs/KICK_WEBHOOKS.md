# Kick Events API integration

## Supported event types

The integration subscribes to version 1 of all ten event types currently
documented by Kick:

- `chat.message.sent`
- `channel.followed`
- `channel.subscription.new`
- `channel.subscription.renewal`
- `channel.subscription.gifts`
- `livestream.status.updated`
- `livestream.metadata.updated`
- `moderation.banned`
- `channel.reward.redemption.updated`
- `kicks.gifted`

The public endpoint is `POST /api/v1/webhooks/kick`. Configure the Kick
Developer app's webhook callback to the HTTPS URL shown by the authenticated
Kick setup/status API. The endpoint verifies the raw request body before it
parses or stores the event.

## Kick app setup

1. Configure `KICK_CLIENT_ID`, `KICK_CLIENT_SECRET`, and the exact OAuth
   redirect URI in the deployment secrets and Kick Developer settings.
2. Enable webhooks in the Kick Developer app and set its callback to
   `https://<backend-host>/api/v1/webhooks/kick`.
3. Reconnect channels authorized before `events:subscribe` was requested so
   the user access token receives the current scope set.
4. Ensure the deployment has native `REDIS_URL` and the platform monitor worker
   is running. Upstash REST alone cannot run the Arq queue.
5. Use `POST /api/v1/integrations/kick/subscriptions/reconcile` to reconcile a
   tenant's channels manually. `GET /api/v1/integrations/kick/status` reports
   provider-list verification, last check, delivery counts, and the last
   processing failure.

The API lists existing subscriptions before creating missing entries. Kick's
GET listing can temporarily omit a recently created subscription, so a
successful create is treated as locally expected for six hours before the
reconciler tries to create it again. Status distinguishes this from a provider
listing that confirms the event.

## Verification and processing

The receiver validates the ULID message ID, RFC 3339 timestamp, event type,
version, and Base64 signature. It fetches the official public key dynamically,
caches it for 15 minutes, and refreshes it immediately after a signature failure
to handle key rotation. It uses RSA PKCS#1 v1.5 with SHA-256 over
`message_id.timestamp.raw_body`. Timestamps up to five minutes in the future
and deliveries up to 24 hours old are accepted; the persistent message ID
unique constraint prevents replay and duplicate processing.

Verified deliveries are stored in `kick_webhook_events`, then enqueued for the
existing Arq worker. Processing passes normalized events through Anti-Bots'
existing AI, threat-intelligence, correlation, alert, and mitigation pipeline.
Only chat messages enter chat-presence tracking. Other Kick events are recorded
without inventing viewer activity. Webhook processing and manual retries write
tenant-scoped audit records. Worker retries are bounded; a recovery task
re-enqueues pending deliveries, and failed records can be retried by the stream
owner or tenant administrator at
`POST /api/v1/integrations/kick/events/{message_id}/retry`.

Raw provider payloads are purged after 24 hours. Long-lived event metadata
retains derived security results but removes raw chat content and embedded user
objects. Automatic moderation defaults to off for Kick; detections create
alerts, and existing authorized workflows govern any moderation action.

## Delivery failure monitoring

The worker checks subscriptions every 30 minutes and attempts to restore ones
missing from Kick's subscription list. The webhook endpoint returns `503` when
the public key service, database, or queue is unavailable, allowing Kick to
retry. Valid duplicate deliveries return `204`. If a delivery repeatedly fails,
the status API shows pending or failed counts and the last processing error.
Kick documents that it can automatically unsubscribe an event after more than
one day of continual webhook processing failures; check the status API and run
manual subscription reconciliation after fixing the cause.

## Verification boundary

Unit coverage checks the supported event catalog and state boundaries. A real
Kick webhook delivery, app approval, scope grant, public callback reachability,
provider subscription listing, and production retry behavior require the
deployed Kick app and cannot be proven from this local workspace.

## Official references

- [Kick event payloads and event names](https://github.com/KickEngineering/KickDevDocs/blob/main/events/event-types.md)
- [Kick webhook signature verification and unsubscribe behavior](https://github.com/KickEngineering/KickDevDocs/blob/main/events/webhook-security.md)
- [Kick event subscription API](https://github.com/KickEngineering/KickDevDocs/blob/main/events/subscribe-to-events.md)
- [Kick developer terms and chat retention requirements](https://dev.kick.com/terms-of-service)
