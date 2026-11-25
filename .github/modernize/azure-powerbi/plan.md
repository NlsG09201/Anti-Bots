# Modernization Plan: StreamShield Azure Phase 1

**Project**: Anti-Bots / StreamShield

## Technical Framework

- **Language**: Python 3.11 for the backend; TypeScript for the frontend
- **Framework**: FastAPI API; Next.js frontend remains on Vercel
- **Build Tool**: pip/uv and npm
- **Database**: PostgreSQL and Redis currently hosted outside Azure
- **Key Dependencies**: SQLAlchemy, asyncpg, Redis/arq, Celery

## Overview

Move the Python API and worker to Azure Container Apps and migrate the
operational services to Azure PostgreSQL and Azure Managed Redis. The trial
database starts empty and the application initializes its schema; no
historical data or dimensional warehouse contents are copied. The API's
analytics continues to use PostgreSQL and will not depend on BigQuery.

Keep the Next.js frontend on Vercel. Defer Microsoft Fabric, Power BI Service
publication, and report embedding because Fabric F2 alone exceeds the confirmed
US$50/month planning target. The user authorized an isolated one-day trial
despite unverified costs and explicitly accepts possible charges above US$50.
Keep Vercel and Render production unchanged. Use an empty PostgreSQL database;
do not copy production data.

## Migration Impact Summary

| Application | Original Service | New Azure Service | Authentication | Comments |
|-------------|------------------|-------------------|----------------|----------|
| Python API | Render | Azure Container Apps | Managed identity | Deployment gated |
| Worker | Render | Azure Container Apps | Managed identity | Separate workload |
| PostgreSQL and analytics | Render PostgreSQL | Azure Database for PostgreSQL | To be configured | Empty database for trial |
| Redis | Render | Azure Managed Redis | Managed identity | Queues/cache |
| Frontend | Vercel | Vercel | Existing auth | Unchanged |

## Infrastructure Plan

| Parameter | Value |
|-----------|-------|
| IaC Tool | Bicep |
| Provision status | Authorized for the trial; held until technical readiness passes |
| Subscription | Azure for Students (enabled; no resource groups found) |
| Region | East US 2 (confirmed by the user) |
| Cost decision | User accepts unverified cost and possible charges above US$50 |

The current Azure account has an enabled subscription, but no resource group
exists. East US 2 was confirmed after PostgreSQL was found unavailable in East
US. Required resource providers are now registered. Current quota checks report
one Container Apps managed environment, 10 sandbox cores, 16 PostgreSQL cores
(including 8 burstable), sufficient network quota, and no fixed Redis/ACR
quota limit. These values do not validate SKU availability. Azure Cost
Management requests fail with HTTP 404 from the cost provider, so actual spend,
credit application, and an itemized estimate remain unverified. Azure CLI
2.93.0 is installed and signed in to the selected subscription. Docker Desktop
is running; API and worker images build locally and pass Python syntax
compilation. Bicep 0.49.2 compiles the template locally, but it has not passed
Azure provider validation or `what-if`. The Bicep template remains incomplete:
it lacks private networking, complete database/Redis endpoint configuration,
PostgreSQL Entra enablement and roles, and registry/image setup.

```text
Vercel frontend (unchanged)
        |
Azure Container Apps: FastAPI API + separate worker
        |                         |
Azure Database for PostgreSQL   Azure Managed Redis
        |
PostgreSQL dimensional warehouse used by API analytics
```

BigQuery synchronization is optional and disabled by default; it will not be
required by this phase. The existing PBIP still points to BigQuery and is not
retargeted in Phase 1. Fabric, Power BI Service publication, and embedding
remain deferred; do not describe them as operational.

## Cost and Deployment Gate

The earlier **US$50/month** limit is not a guaranteed cap. The user explicitly
authorized proceeding with an unverified cost estimate and accepts that
charges may exceed US$50. Cost Management still returns HTTP 404, so current
spend, credit application, and actual charges remain unverified. Retail
catalog results provide indicative rates only; Container Apps usage, storage,
networking, monitoring, and workload are not fully costed. Do not describe
Azure for Students credits or Azure budgets as a spending stop. Technical
readiness and safe-cleanup gates remain in force regardless of this cost
decision.

The local Docker Linux engine is currently unavailable. The current Bicep
template is incomplete for deployment. There is no validated automatic
cleanup mechanism for the test window. No billable Azure resources or
Vercel/Render changes have been created.

Retail-price scenario for one day (USD), assuming one continuously active
0.5-vCPU/1-GiB API replica and one matching worker replica, no Redis HA, and
one 1-GiB Log Analytics ingestion cap:

| Component | 24-hour estimate |
|-----------|------------------:|
| PostgreSQL B1MS compute | $0.41 |
| PostgreSQL 32-GiB storage | $0.12 |
| Managed Redis Balanced_B0 | $0.38 |
| ACR Basic | $0.17 |
| Container Apps, up to 2 million requests | $3.39 |
| Log Analytics, maximum 1 GiB ingested | $2.30 |
| **Known subtotal before network** | **$6.77** |
| Example: 100 GiB internet egress at up to $0.087/GiB | $8.70 |

This gives an indicative **US$15.47** for the listed services with that egress
scenario, before private-endpoint charges, image storage over the included
allowance, Redis high-availability, and other unverified usage. A private
endpoint allowance has not been validated. Egress is not capped by this
estimate, so US$15.47 is not a hard maximum and cannot certify the US$50/month
limit. Azure Cost Management returns HTTP 404 for this subscription, preventing
an independent current-spend/credit check; the available US$100 credit and
US$0 November cost are from the user's screenshot. The user accepts this
uncertainty and possible overage; confirm the exact private-networking/HA
configuration for disclosure, not as a cost-approval gate. Azure budgets are
alerts, not a guaranteed spend stop.

The user-provided Azure for Students screenshot shows US$100 of US$100 credit
available, expiration on 24 November 2027, and US$0 November cost. This is
user-provided billing evidence, not an independently queried balance. It does
does not verify credit application or overage behavior.

The user authorized an isolated Azure test from 25 November 2026 at 18:00
through 26 November 2026 at 18:00 (UTC-05:00), and confirmed to keep that
scheduled start rather than deploy immediately. The user accepts the
unverified-cost risk. A Vercel Preview may use the temporary Azure API while
existing Vercel/Render production traffic remains unchanged. All trial
resources must be deleted at the end. Do not deploy unless the technical
readiness and cleanup gates are verified.

The latest user decision is to use an empty database. No source database
credentials or snapshot are needed for this trial, and no production data has
been read or copied. Do not access or transfer production data.

The previously checked Fabric reference is outside this phase: Fabric F2
running continuously is approximately US$262.80/month before application
services. Power BI licensing and the user count are also unconfirmed. The user
has deferred Fabric/embedding; Power BI consumers were marked pending.

Before the scheduled deployment, complete private networking, identity,
image-publishing, application configuration, and cleanup implementation;
validate the template and run Azure `what-if`. The user has approved the
cost-uncertain trial but has not approved any change to production. Stop if a
technical validation fails or reliable cleanup cannot be verified.

## Scope Boundaries

- **Included**: Prepare and deploy an isolated Azure trial for the Python
  API/worker, empty PostgreSQL database, and Redis; mock-mode tests;
  security/CVE review; disclose unverified cost and possible overage.
- **Unchanged**: Frontend remains hosted on Vercel.
- **Deferred**: Fabric migration, Power BI PBIP source update, Power BI Service
  publication, and embedding.
- **Excluded**: `backend-spring/` Java service, production changes, and
  historical data migration.

## Open Questions & Questionnaire

- [x] Q: Should infrastructure be provisioned now? → A: The user authorized an
  isolated trial despite unverified cost and possible charges above US$50;
  resource creation remains gated on technical readiness and cleanup.
- [x] Q: How should the one-day deployment be used and ended? → A: Isolated
  Azure test with a Vercel Preview connected to Azure; keep current production
  unchanged, run 25 November 2026 18:00 to 26 November 2026 18:00 UTC-05:00,
  then delete the test resources.
- [x] Q: What data should the isolated test use? → A: Empty database; no
  snapshot or historical production data.
- [x] Q: Should integration testing be included? → A: Yes, use mock mode until
  Azure resources are available.
- [x] Q: Should security/CVE remediation be included? → A: Yes.
- [x] Q: Which Azure deployment target should be used? → A: Azure Container
  Apps for the API and separate worker.
- [x] Q: Which subscription and region? → A: Azure for Students, East US 2.
  The user confirmed East US 2 after PostgreSQL was found unavailable in East
  US. The subscription is enabled; no resource groups are present.
- [x] Q: How should Phase 1 handle analytics? → A: Use Azure PostgreSQL with an
  empty database for the trial; defer Fabric and Power BI embedding.
- [x] Q: Is the US$50 monthly limit a hard deployment gate? → A: The user
  explicitly accepted proceeding with unverified cost and possible charges
  above US$50; this does not establish a spending cap.
- [ ] Resolve technical readiness: validate SKUs and template, complete private
  connectivity and identity, publish real images, and verify timed cleanup.
- [x] Q: What Azure for Students credit is available? → A: The user-provided
  screenshot shows US$100 available, expiring 24 November 2027, and US$0
  November cost.
- [ ] Confirm credit application and whether Azure blocks or bills consumption
  beyond available credit before creating billable resources.
- [ ] Confirm Power BI consumer count and the future Fabric/workspace/licensing
  model before resuming the deferred BI work.
