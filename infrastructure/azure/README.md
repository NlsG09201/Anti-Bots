# StreamShield Azure infrastructure (Bicep)

This template describes the Azure infrastructure boundary for the Python API and
worker. It contains Azure Container Apps, an Azure Database for PostgreSQL
Flexible Server/database, Azure Managed Redis, and Log Analytics for Container
Apps logs. The Vercel frontend remains outside this deployment. The existing
BigQuery analytics flow and Power BI PBIP are not migrated by this template.

## Local review status — 2026-11-24

This is an artifact review only. Azure CLI and Bicep CLI are unavailable in the
review environment; subscription, authentication, quotas, resource state, image
registry, and cloud connectivity are **unverified**. No Azure/Fabric calls,
resource changes, image pushes, data transfers, or deployment were made.
Provisioning remains disabled and no deployment command is authorized by this
review.

The local API and worker image entry points are:

| Workload | Dockerfile | Container port/command |
|---|---|---|
| API | `backend/Dockerfile.aca` | HTTP port 8000; direct Uvicorn entry point |
| Platform worker | `backend/Dockerfile.worker` | `python scripts/platform_monitor_worker.py`; no ingress |

Build contexts must be `backend/` so that the Dockerfiles can copy
`requirements.txt`, application modules, scripts, and model data. The existing
`backend/.dockerignore` excludes local environment files, databases, virtual
environments, and test/build caches while retaining application data. The ACA
API Dockerfile intentionally avoids the Render-specific
`render_check_env.py`; application production checks still run during FastAPI
startup. These files have not been built or pushed in this review.

## Provisioning is disabled

The template is intentionally **not deployed**. No Azure resource group,
subscription, region, registry, SKU selection, or workload sizing has been
confirmed. Required image and SKU parameters have no values. The PostgreSQL
administrator password is a required secure parameter and has no value in this
repository. Do not add a populated parameter file or commit secret material.

Compile locally without contacting Azure (requires the Bicep CLI):

```powershell
bicep build infrastructure/azure/main.bicep --no-restore --outfile "$env:TEMP\streamshield-main.json"
```

The generated ARM JSON is a temporary local build artifact and is not committed.
This command was **not run** because `bicep` is unavailable. `az` is also
unavailable. No Azure-connected command is part of validation for this task.

## Before any future deployment

- Confirm subscription, region, resource group, allowed SKUs/quotas, API and
  worker sizing, backup/HA/retention, ingress and custom-domain requirements,
  and cost approval. East US in the plan is a pricing reference only.
- Design private routing and DNS across the Container Apps environment,
  PostgreSQL Flexible Server, and Managed Redis. The current Bicep has no
  Container Apps VNet/subnet, PostgreSQL delegated-subnet/private-DNS
  configuration, or Redis private endpoint/DNS. PostgreSQL public access is
  disabled, so a usable private path is a prerequisite, not a verified feature.
- Enable PostgreSQL Entra authentication, nominate its Entra administrator,
  create least-privilege database roles for each workload identity, and grant
  required schema permissions. The template currently sets
  `activeDirectoryAuth: Disabled`, `passwordAuth: Enabled`; it creates no Entra
  administrator or database roles. The application supports
  `DATABASE_AUTH_MODE=managed_identity`, but this is not wired in the Bicep.
- Configure Redis Entra data authentication/ACLs and network access, and
  authorize both Container Apps identities. The application expects
  `REDIS_AUTH_MODE=managed_identity` plus a TLS `REDIS_URL` at port 10000; the
  Bicep currently does not supply either value or grant data-plane access.
  Keep passwords in a protected secret store if a reviewed design selects
  password authentication instead.
- Supply immutable API/worker images from an approved registry (likely ACR
  after registry choice and cost approval) and configure managed registry pull
  authorization. The Bicep accepts image parameters but does not create a
  registry, build images, or establish pull authorization.
- Populate ACA app settings from confirmed endpoints: `DATABASE_URL`,
  `DATABASE_AUTH_MODE`, `REDIS_URL`, `REDIS_AUTH_MODE`, `APP_CORS_ORIGINS`,
  `TRUSTED_HOSTS`, `APP_FRONTEND_URL`, and `APP_PUBLIC_URL`. Store
  `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `AES_ENCRYPTION_KEY`, and any integration
  credentials as protected secrets. Do not use sample/default secret values.
  The current template only sets `PORT`/`APP_ENV` for the API and worker mode
  flags for the worker; it omits database/Redis endpoints and application
  secrets. Callback/webhook hostnames and the Vercel production origin also
  require confirmation.
- Review migration strategy before connecting a new database. API and worker
  startup both invoke database initialization and `run_startup_migrations`;
  that code performs schema changes. Require a verified backup/restore plan,
  schema/data parity checks, an authorized one-off migration window, rollback
  criteria, and a DNS/API cutover plan. Do not point either workload at a new
  database or move production data during preparation.
- Decide Fabric workspace/capacity, identity and licensing, ingestion
  schedule/volume, PostgreSQL-to-Fabric private connectivity or gateway, and
  tenant/RLS controls. No Fabric pipeline or Bicep resource exists here; the
  PBIP currently connects directly to BigQuery. Retargeting and report-parity
  validation are a separate gated workstream.
- Recheck prices and licensing with the Azure calculator and Microsoft
  purchasing terms before any purchase. The plan's Fabric F2/F64 and Pro
  figures are illustrative estimates, not quotes; PostgreSQL, Redis, Container
  Apps, ACR, networking, monitoring, OneLake, and workload costs are not fully
  estimated. Written cost approval is required before billable actions.

The API and worker receive separate system-assigned identities, but this
infrastructure task does not grant data-plane roles or change application
authentication. API ingress is external HTTPS for the Vercel frontend; the
worker has no ingress. Do not treat PostgreSQL or Redis as ready for application
access until private connectivity, endpoint exposure, and identity access have
been reviewed.
