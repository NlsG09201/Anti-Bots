# Security policy

## Reporting a vulnerability

Report suspected vulnerabilities through GitHub's private vulnerability reporting for this repository (Security → Advisories → Report a vulnerability). Do not publish exploit details, customer data, tokens, or live credentials in an issue or pull request. If private reporting is unavailable, contact a repository maintainer privately and include the affected component, impact, reproduction steps, and any relevant logs with secrets removed.

The maintained security baseline is the current `main` branch. Do not test attacks against production accounts or platform integrations without explicit authorization.

## Incident response

1. Triage the report and preserve relevant, access-controlled application and provider audit logs.
2. Contain the exposure: disable affected credentials or integration paths and restrict access where needed.
3. Revoke and rotate exposed credentials with their issuer. Revoke refresh sessions and provider OAuth grants when affected; deleting a secret from Git history alone does not invalidate it.
4. Patch and test the affected code or configuration, then deploy through staging before production when feasible.
5. Notify affected customers and providers when their data, credentials, or integrations may have been impacted; record the scope and remediation.

Application logs should use structured event names and safe metadata (for example, failure reason and error type). Never log passwords, access/refresh tokens, authorization headers, API keys, webhook signatures, or raw authentication payloads. Login lockout identifiers are HMAC-fingerprinted before they are stored or logged.
