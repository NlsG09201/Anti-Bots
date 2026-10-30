# Platform integration audit

## Scope and findings

Reviewed the provider adapters, live monitors, health probes, webhook ingestion,
OAuth callbacks, and viewer synchronization paths for Kick and TikTok.

- Kick live status uses the documented Kick Public API and OAuth. Chat messages
  are received through Kick's signed Events API webhook.
- The previous Kick chat roster sync called website API endpoints and fetched
  chat history that is not part of the documented Public API. Those calls have
  been removed. Kick Events API messages identify chat participants who speak;
  they do not provide a complete list of viewers or silent chat participants.
- The previous TikTok live status and chat implementation used an undocumented
  web endpoint, page parsing, and a third-party Webcast client. Those calls and
  its monitor have been removed. No official TikTok developer API capability
  for public live status or live chat was found in the reviewed docs. The app
  now reports that the integration is unavailable instead of reporting a false
  offline result.
- Twitch and YouTube integrations were not changed in this audit.

## Operational requirements

Kick OAuth credentials and required scopes must be configured in the provider
developer console. The public webhook URL must be enabled for the Kick app, and
the backend must be reachable at the configured callback. Reconnect existing
channels if they lack an access token or the required event subscription.

TikTok LIVE monitoring remains disabled until TikTok approves and documents
an API that grants the app the required live status and chat capabilities.
Do not add private endpoints, page scraping, session cookies, or unofficial
Webcast clients as a fallback.

## Related delivery checks

The BI warehouse SQL was executed against an isolated PostgreSQL instance with
empty operational tables. This confirmed schema and procedure execution, but
does not validate production records or Power BI rendering. The Render 401
authentication issue still requires the sanitized `authentication_rejected`
log event and failing route to identify the production cause. No cloud resource
or Power BI report was deployed from this workspace.

## References

- [Kick Events API introduction](https://github.com/KickEngineering/KickDevDocs/blob/main/events/introduction.md)
- [Kick livestream API documentation](https://github.com/KickEngineering/KickDevDocs/blob/main/apis/livestreams.md)
- [TikTok developer guidelines](https://developers.tiktok.com/docs/en/our-guidelines-developer-guidelines)
- [TikTok API v2 overview](https://developers.tiktok.com/docs/en/tiktok-api-v2-introduction)
