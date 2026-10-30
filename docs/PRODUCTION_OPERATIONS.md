# Production deployment and recovery

## Current deployment shape

The repository has a manual Render deployment workflow for the API and platform worker, plus a VPS Compose deployment script and a Vercel frontend setup. There is no repository-managed staging deployment, automated database backup destination/schedule, or tested production restore in this workspace. Do not treat the sample staging environment file as a deployed staging environment.

## One-time setup

1. Configure GitHub Actions secrets `DEPLOY_RENDER_ENV` (the complete production environment file contents) and `RENDER_API_KEY` (a least-privilege Render API key).
2. In GitHub repository settings, create the `production` environment, restrict deployments to `main`, and require a reviewer. The workflow intentionally deploys only when manually dispatched from `main`; it checks that CI succeeded for the exact commit before touching Render.
3. Confirm the Render services `anti-bots-api` and `anti-bots-platform-monitor` exist and that the health endpoint is reachable. The workflow updates environment variables and requests deploys; it does not create services or change their plans.
4. Keep Vercel configuration in its environment settings. Never commit `.env`, Render import files, API keys, or database URLs.

The `production` approval gate depends on repository environment protection settings. A workflow file alone cannot enforce reviewer approval if the environment is left unprotected.

## Deploy and verify

Merge and wait for the CI workflow to pass on `main`. Review the exact commit, then manually run **Deploy Render env** against `main` and approve the GitHub environment deployment. The script waits for API `/health`; inspect Render logs and worker health/status separately before considering the release complete. Check the frontend and a representative authenticated API flow in the deployed environment.

For VPS deployments, `deploy/vps/vps-deploy.ps1` currently pulls the latest branch and rebuilds in place. It performs a health check but does not perform an automated rollback. Use a reviewed release commit and retain the previous commit identifier before running it.

## Rollback and failed configuration

For Render, use the service's deployment history to redeploy the last known-good deploy, then verify `/health`, worker status, and a basic user flow. If the failure came from configuration, restore the previous values from the operator's protected configuration record before redeploying. Do not paste secrets into tickets or logs. If the previous deployment is incompatible with a database change, stop and follow the migration recovery plan rather than switching application versions blindly.

For VPS, SSH to the host, check `git log -1 --oneline`, and deploy the previously recorded release commit using the normal Compose procedure. This rebuilds the image and is not an atomic rollback; verify health and logs. Do not reset the database as part of an application rollback.

## Database backup and restoration

The backup utility and isolated restore instructions are in [DATABASE_BACKUP_RECOVERY.md](DATABASE_BACKUP_RECOVERY.md). Run backups from a protected runner with PostgreSQL client tools and `DATABASE_URL` injected as a secret. Copy dump and checksum manifest to encrypted, access-controlled storage outside the database host; configure retention and alerting in that storage/scheduler. The repository does not currently configure that scheduler or storage, so backups are not yet automatic.

Restore only to a new empty isolated database/Neon branch, run archive/manifest verification and the documented restore command, then smoke-test the application and compare expected data before cutover. Never use the live database as a restore drill target. Record the drill date, archive, result, and restore duration without recording credentials.

## Recovery objectives and operational monitoring

Current guaranteed RPO and RTO are **undefined**: no scheduled off-host backup and no isolated restore drill have been verified here. Set an initial operational target of RPO ≤24 hours and RTO ≤4 hours only after a daily backup schedule, off-host retention, failure alerts, and a successful restore drill are in place. These are targets, not measured guarantees; provider point-in-time recovery can improve RPO only after its plan and retention are confirmed.

Check `/health`, deployment status, application/worker logs, database connectivity, and queue/event lag during incidents. Prometheus configuration exists, but an alert receiver is not configured in this repository; route critical alerts through the operator's chosen monitoring service. Preserve timestamps, release commit, affected service, and non-sensitive error identifiers for incident review.

## Incident sequence

1. Identify affected service and last deployment/configuration change; use health checks and logs to determine whether API, worker, database, or frontend is failing.
2. Stop further releases. Roll back the application/configuration if compatible with current schema; otherwise keep the release and recover forward with a reviewed fix.
3. If data integrity is in question, isolate writes and restore a verified backup only into a separate database first. Confirm integrity before changing service configuration.
4. Verify health and key flows, notify affected operators/customers through established channels, and record impact, timeline, recovery point, and follow-up actions.
