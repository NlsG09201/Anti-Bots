# Modernization Plan: StreamShield Azure and Microsoft Fabric

**Project**: Anti-Bots / StreamShield

## Technical Framework

- **Language**: Python 3.11 for the in-scope backend; TypeScript for the frontend
- **Framework**: FastAPI for the API; Next.js frontend remains on Vercel
- **Build Tool**: pip/uv for Python; npm for the frontend
- **Database**: PostgreSQL and Redis on Render; BigQuery integration is disabled
  by default
- **Key Dependencies**: SQLAlchemy, asyncpg, Redis/arq, Celery, BigQuery client

## Overview

Move the Python API and worker from Render to Azure, replace the BigQuery
analytics destination with Microsoft Fabric Warehouse, and continue using the
existing Power BI project against the Azure analytics destination. Keep the
frontend on Vercel. The plan prepares and validates the migration without
creating Azure or Fabric resources; provisioning and production cutover require
a separate cost review and explicit authorization.

The application already builds dimensional analytics in PostgreSQL. BigQuery
is used by a separate scheduled/manual replication flow and by the current
PBIP source connection. The replacement must preserve data parity, tenant
isolation, and report behavior before BigQuery is retired.

## Migration Impact Summary

| Application | Original Service | New Azure Service | Authentication | Comments |
|-------------|------------------|-------------------|----------------|----------|
| Python API | Render | Azure Container Apps | Managed identity | Deployment gated |
| Worker | Render | Azure Container Apps | Managed identity | Separate workload |
| PostgreSQL | Render | Azure Database for PostgreSQL | Managed identity | Keep schema/data |
| Redis | Render | Azure Managed Redis | Managed identity | Keep queue/cache use |
| Analytics | Google BigQuery | Microsoft Fabric Warehouse | Entra identity | Replace replication flow |
| Power BI PBIP | BigQuery connector | Fabric Warehouse | Entra identity | Update model and refresh |
| Frontend | Vercel | Vercel | Existing auth | Remains unchanged |

## Infrastructure Plan

| Parameter | Value |
|-----------|-------|
| IaC Tool | Bicep |
| Provision | false |
| Region | East US is a pricing reference only; deployment region is unconfirmed |
| Subscription/resource group | Not confirmed for this deployment |

Target architecture:

```text
Vercel frontend
      |
      +---- Power BI embedded report
      |       Microsoft Fabric workspace / semantic model
      |                    |
      |             Fabric Warehouse
      |                    ^
      |          Fabric data pipeline
      |                    |
Azure Container Apps API + worker
      |                    |
Azure Database for PostgreSQL (operational + dimensional warehouse)
      |
Azure Managed Redis
```

The Fabric pipeline is expected to load the existing PostgreSQL dimensional
warehouse into Fabric. The final connectivity method must support the private
networking design and the selected Fabric workspace/capacity. Preserve the
current per-tenant data boundary with an explicit Fabric/Power BI security
design and cross-tenant access tests; do not rely solely on report filters.
The PBIP currently connects directly to BigQuery and must be retargeted to
Fabric. Do not remove the BigQuery path until historical data and report parity
are verified.

The existing Bicep is not ready to deploy: it lacks private connectivity and
application database/Redis configuration, PostgreSQL Entra authentication is
disabled, image references and SKUs are unresolved, and it does not provision
or configure Fabric workspaces, pipelines, or capacity. Address these gaps in
the infrastructure task, but keep provisioning disabled.

## Indicative Cost Estimate

The existing plan recorded prices checked **2026-11-24**, USD, using East US
only as a reference; they were not independently revalidated during this local
review. These are retail-price calculations, not a quote. They exclude
negotiated discounts, taxes, data transfer, storage growth, and usage above the
stated assumptions.

| Scenario/component | Assumption | Indicative monthly cost |
|---------------------|------------|-------------------------|
| Fabric F2 | 2 CU × $0.18/CU-hour × 730 hours; continuously running | **$262.80** |
| Fabric F64 | 64 CU × $0.18/CU-hour × 730 hours; continuously running | **$8,409.60** |
| Power BI Pro | Current US list price, annual billing | **$14 per licensed user** |
| Container Apps | Usage-based; existing Bicep sets one 0.5-vCPU/1-GiB API replica and one worker replica; price depends on active time and requests | Not included; needs workload estimate |
| PostgreSQL Flexible Server | SKU, HA, IOPS, retention, and actual storage are unselected | Not included |
| Azure Managed Redis | SKU and region are unselected; current public retail response did not return a price item | Not included |
| Log Analytics / OneLake | Depends on log ingestion/retention and stored data volume | Not included |

For F2, Microsoft licensing guidance says each user consuming Power BI content
requires Pro/PPU below F64. At ten licensed users, Fabric plus those licenses
would be about **$402.80/month** before the Azure application stack and
storage. F64 is the alternative scenario for free Power BI consumers and costs
about **$8,409.60/month** for capacity alone; publisher/admin licensing and
tenant-specific terms still need confirmation. Capacity can be paused to reduce
compute cost, but reports and warehouse workloads are unavailable while paused.

No complete monthly total is provided until PostgreSQL/Redis SKUs, API and
worker active hours, log volume, OneLake retention, Power BI user count, and
embedding/licensing model are confirmed. The Azure pricing calculator and
tenant-specific purchasing terms must be checked before any purchase or
provisioning.

Price and licensing sources:

- [Microsoft Fabric pricing](https://azure.microsoft.com/en-us/pricing/details/microsoft-fabric/)
- [Azure Retail Prices API — Microsoft Fabric, East US](https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode=USD&%24filter=serviceName%20eq%20%27Microsoft%20Fabric%27%20and%20armRegionName%20eq%20%27eastus%27)
- [Power BI pricing](https://www.microsoft.com/en-us/microsoft-fabric/features/power-bi/pricing)
- [Power BI embedded capacity and licensing](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embedded-capacity)
- [Azure Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
- [Azure Database for PostgreSQL pricing](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/)
- [Azure Managed Redis pricing](https://azure.microsoft.com/en-us/pricing/details/managed-redis/)
- [Azure Monitor pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/)

## Scope Boundaries

- **Included**: Python API/worker migration to Container Apps; PostgreSQL and
  Redis migration; replacement of BigQuery replication with a Fabric-based
  analytics pipeline; PBIP source update and Power BI embedding; Bicep
  preparation, cost estimation, mock-mode integration verification, and
  security/CVE review.
- **Unchanged**: Next.js frontend remains hosted on Vercel.
- **Excluded for now**: `backend-spring`; Azure/Fabric provisioning; production
  cutover; purchase of capacity or licenses. Those require a separate review
  and explicit approval.

## Open Questions & Questionnaire

- [x] Q: Should infrastructure be provisioned now? → A: No. Prepare the plan and
  estimate only; keep `provision: false` and do not create resources.
- [x] Q: Should integration testing be included? → A: Yes, mock mode until
  provisioned services are explicitly authorized and available.
- [x] Q: Should security/CVE remediation be included? → A: Yes.
- [x] Q: Which Azure deployment target should be used? → A: Azure Container Apps
  for the API and separate worker.
- [x] Q: Should containerization be separate? → A: No; it is covered by the
  Container Apps deployment task.
- [x] Q: Which analytics destination should replace BigQuery? → A: Microsoft
  Fabric Warehouse.
- [ ] Confirm Azure subscription, deployment region, resource group, and
  PostgreSQL/Redis/API sizing before final cost calculation or deployment.
- [ ] Confirm Fabric capacity/licensing scenario, number of report consumers,
  workspace/tenant configuration, expected data volume, refresh schedule, and
  OneLake retention.
- [ ] Confirm private connectivity from Fabric pipelines to the Azure
  PostgreSQL source and the tenant-isolation model before migration.
- [ ] Confirm Power BI Service workspace and report publication details before
  enabling embedding or production refresh.

## Local deployability review progress — 2026-11-24

**Status: preparation only; not Azure/Fabric deployable or deployed.** The
provided branch is `modernize/python-20261125010202`. Azure CLI and Bicep CLI
were not available locally. Subscription/authentication, permissions, quotas,
resources, registry, endpoints, cloud networking, and all Azure/Fabric
integration behavior remain unverified. No cloud tools, cloud calls,
provisioning, deployment, image publication, data transfer, or commit were
performed. Provisioning stays disabled.

### Findings and safe local artifact changes

- Updated `backend/.dockerignore` to exclude local environment files, local
  databases, virtual environments, caches, and audit/build scratch files from
  container contexts. Application data remains included.
- Added `backend/Dockerfile.aca` for the API. It uses Python 3.11, multi-stage
  dependency installation, an unprivileged user, Java runtime for the API's
  Weka dependency, port 8000, and a direct Uvicorn command. It avoids the
  Render-specific API preflight; FastAPI production startup checks remain in
  place. `backend/Dockerfile.worker` remains the dedicated worker entry point.
  Neither image was built or pushed.
- Updated `infrastructure/azure/README.md` and
  `business-intelligence/README.md` with current limitations, prerequisites,
  local validation status, and explicit cost/decision gates.
- Did not alter Bicep resource topology or choose region/SKUs/networking,
  identity roles, Fabric capacity/licensing, or migration method: those require
  owner decisions and cloud validation.

### Local validation record

| Check | Result |
|---|---|
| `Get-Command docker,bicep,az,python,py` availability probe | Docker and Python found; Bicep, Azure CLI (`az`), and Python launcher (`py`) unavailable. |
| Azure subscription/auth/resource read | Not run; `az` unavailable, per scope. |
| Bicep compile | Not run; Bicep CLI unavailable. |
| Docker image build/scan/push | Not run. No image was built, scanned, or published. |
| Managed identity / PostgreSQL / Redis live connectivity | Not run; no endpoints or credentials, and cloud access prohibited. |
| Fabric pipeline / Power BI refresh or publish | Not run; no Fabric pipeline exists and the PBIP still uses BigQuery. |
| Isolated auth unit tests | `Set-Location backend; .\.venv\Scripts\python.exe -m pytest tests/test_azure_postgres_auth.py tests/test_azure_managed_redis_auth.py tests/test_azure_celery_redis_auth.py -q` → **25 passed in 0.97s**. |
| Offline ACA Dockerfile/build-context assertions | Passed: Docker CMD parses as JSON, starts Uvicorn on port 8000, omits the Render preflight, and `.dockerignore` excludes env/database/temp artifacts while retaining application data. This is not a full Dockerfile build or syntax check. |
| Documentation status assertions | Passed for this plan, `infrastructure/azure/README.md`, and `business-intelligence/README.md`. |

Tool availability was checked locally with:

```powershell
$cmds = 'docker','bicep','az','python','py'
foreach ($name in $cmds) {
  $c = Get-Command $name -ErrorAction SilentlyContinue
  if ($c) { "${name}: $($c.Source)" } else { "${name}: unavailable" }
}
```

Result: Docker and Python were found; `bicep`, `az`, and `py` were unavailable.
Docker was not invoked for a build. No Azure/Fabric operations were attempted.

### Blockers and release gates

1. **Network:** select and approve a private network/DNS design for ACA,
   PostgreSQL, Managed Redis, and Fabric ingestion. Current Bicep has no ACA
   VNet integration or PostgreSQL/Redis private route configuration.
2. **PostgreSQL:** current Bicep disables Entra authentication and enables
   password authentication. Confirm Entra admin, per-workload database roles,
   schema grants, endpoint, and token-auth support before setting
   `DATABASE_AUTH_MODE=managed_identity`.
3. **Redis:** current Bicep does not wire `REDIS_URL`/`REDIS_AUTH_MODE`, private
   access, or data-plane permissions. Confirm endpoint and Entra ACLs for both
   API and worker before `REDIS_AUTH_MODE=managed_identity`.
4. **Endpoints/secrets:** approve production Vercel origin, ACA API hostname,
   callback/webhook URLs, database/Redis endpoints, required app settings, and
   protected-secret source. Do not put secret values in Bicep parameters,
   repository files, or image layers.
5. **Images/registry:** choose registry and immutable tags/digests, build and
   vulnerability scan locally under an approved process, then separately
   authorize registry publication and ACA pull identity. Current template
   creates no ACR.
6. **Migration/cutover:** API and worker startup initialize the database and
   run schema migration code. Before migration, validate backups/restores,
   schema/data parity, migration execution procedure, rollback, queue/cache
   compatibility, DNS/webhook changes, and a no-data-loss cutover window. Keep
   the existing service and data untouched until an authorized migration plan
   is approved.
7. **Fabric/Power BI:** choose Fabric capacity/workspace/licensing and service
   identities, ingestion schedule, private connectivity/gateway, tenant
   security/RLS, and report refresh behavior. Current Power Query expressions
   use `GoogleBigQuery.Database`; no Fabric loader/pipeline or Fabric PBIP
   source change was found. Retain BigQuery until data parity, tenant isolation,
   and report validation are proven.

### Cost and approval record

The cost section above is an indicative planning estimate, not a current quote
or approval. Its stated reference values are Fabric F2 at approximately
**$262.80/month**, Fabric F64 at approximately **$8,409.60/month**, and Power BI
Pro at approximately **$14/user/month** under the listed assumptions and date.
These exclude or do not resolve PostgreSQL, Managed Redis, ACA, ACR, private
networking, monitoring/retention, OneLake, data transfer, workload utilization,
taxes, and negotiated pricing. The total is therefore unknown. Recheck all
prices, regional SKU availability, quotas, licensing, and actual usage with the
owner before requesting written cost approval. No paid-resource action is
authorized by this review.
