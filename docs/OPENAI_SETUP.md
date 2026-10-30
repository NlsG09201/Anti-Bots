# OpenAI integration

The backend uses the official asynchronous OpenAI Python SDK and Responses API.
OpenAI is contextual analysis alongside local rules and trained detectors; its
output is validated and never directly executes moderation actions.

## Configure

Set these values in the backend environment (`backend/.env` locally, or Render
service environment variables in production):

```dotenv
OPENAI_API_KEY=your-project-api-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODERATION_MODEL=omni-moderation-latest
AI_ENABLED=true
OPENAI_CHAT_ANALYSIS_ENABLED=true
OPENAI_TIMEOUT_SECONDS=12
OPENAI_MAX_RETRIES=2
OPENAI_MAX_OUTPUT_TOKENS=350
OPENAI_RATE_LIMIT_PER_MINUTE=60
OPENAI_ANALYSIS_CACHE_SECONDS=900
OPENAI_INPUT_COST_PER_MILLION=0
OPENAI_OUTPUT_COST_PER_MILLION=0
```

Never put the key in a frontend variable or commit it. `render.yaml` declares
secret fields for both `anti-bots-api` and `anti-bots-platform-monitor`; add the
same API key to both Render services and deploy them. Change model identifiers
through service environment variables. Set both token price variables from
your current OpenAI billing rates to enable cost estimates; otherwise the UI
shows token usage and marks cost estimates as unconfigured.

## Processing behavior

- Routine chat messages stay in the existing local detection pipeline. Local
  URL, promotion, abuse-language, and repetition signals select candidates for
  OpenAI analysis. The tenant rate limiter reserves two requests (moderation
  and contextual analysis), and repeated candidate text is cached per tenant,
  channel, and signal set.
- Selected text is sent to the OpenAI Moderation endpoint, then the Responses
  API returns a strict JSON Schema analysis. The prompt treats chat text as
  untrusted data and supplies no tools. The response is Pydantic-validated.
- Existing statistical/behavioral risk remains the primary input. OpenAI can
  add a bounded corroboration and an assisted-review alert. The model cannot
  call moderation endpoints or cause automatic bans/timeouts. Existing local
  rules and explicit channel configuration remain responsible for actions.
- `AIUsageRecord` stores tenant, channel, operation, model, token counts,
  status, cache hits, and optional estimated cost. `GET /api/v1/ai/usage` scopes
  totals to the authenticated tenant. The SOC assistant can load recent
  incidents/activity for a selected tenant-owned channel; it receives a
  minimized context without raw chat bodies, user identifiers, OAuth tokens,
  or IP addresses.
- Kick webhook processing already runs in the Arq worker. Other platform
  messages enter through their existing event-processing paths. Provider
  failures fall back to local analysis; the SDK applies bounded retries and a
  request timeout.

## Verify

Use `GET /api/v1/ai/usage` to check whether OpenAI is configured and to view
token/cost estimates. An administrator can call
`POST /api/v1/ai/openai/validate` to verify access to the configured model.
OpenAI structured results use the [official Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
and [Moderation API](https://developers.openai.com/api/docs/guides/moderation).
