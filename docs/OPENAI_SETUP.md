# OpenAI configuration

The backend already calls OpenAI from the threat insight service, bot screening,
and the SOC assistant. OpenAI is optional: when no API key is configured or a
request fails, threat insights and the assistant fall back to local behavior.
OpenAI calls are server-side; the key is never sent to the browser.

## Local setup

Set these variables in the backend process environment or `backend/.env`:

```dotenv
OPENAI_API_KEY=your-project-api-key
OPENAI_MODEL=gpt-4o-mini
AI_ENABLED=true
```

Keep the API key out of source control and frontend environment variables.

## Render setup

`render.yaml` declares `OPENAI_API_KEY` as a secret for both `anti-bots-api`
and `anti-bots-platform-monitor`, and sets `OPENAI_MODEL=gpt-4o-mini` plus
`AI_ENABLED=true`. Add the API key in Render's Environment settings for both
services, then deploy/restart each service. The API service uses it for request
and threat-insight flows; the worker needs it for asynchronous event analysis.
Startup logs report only whether OpenAI is configured, never the key.

## What uses OpenAI

- Threat insights use the model for evidence summaries when AI is enabled and
  an insight is generated. Local heuristics remain the fallback.
- Bot screening can request model analysis when its local checks determine it
  needs additional analysis.
- The SOC assistant uses the model for analyst responses and falls back to
  local guidance if the API is unavailable.
- The AI Intelligence event orchestrator and its trained models remain local.
  Configuring the API key does not send every raw chat message to OpenAI and
  does not grant the model authority to ban or timeout anyone.

Chat Completions responses requesting structured JSON use OpenAI's JSON mode;
the application still parses and validates the returned data. See the
[official OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
for stronger schema-constrained output options.
