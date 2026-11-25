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
operational and dimensional PostgreSQL database and Redis service to Azure.
The existing API analytics already queries the PostgreSQL dimensional
warehouse, so Phase 1 will use Azure PostgreSQL for application analytics and
will not depend on BigQuery.

Keep the Next.js frontend on Vercel. Defer Microsoft Fabric, Power BI Service
publication, and report embedding because Fabric F2 alone exceeds the confirmed
US$50/month total-consumption budget. No resources will be provisioned until
the minimum Azure stack is costed against that budget and the user approves the
specific resources.

## Migration Impact Summary

| Application | Original Service | New Azure Service | Authentication | Comments |
|-------------|------------------|-------------------|----------------|----------|
| Python API | Render | Azure Container Apps | Managed identity | Deployment gated |
| Worker | Render | Azure Container Apps | Managed identity | Separate workload |
| PostgreSQL and analytics | Render PostgreSQL | Azure Database for PostgreSQL | Managed identity | Preserve warehouse |
| Redis | Render | Azure Managed Redis | Managed identity | Queues/cache |
| Frontend | Vercel | Vercel | Existing auth | Unchanged |

## Infrastructure Plan

| Parameter | Value |
|-----------|-------|
| IaC Tool | Bicep |
| Provision | false |
| Subscription | Azure for Students (enabled; no resource groups found) |
| Region | East US 2 (confirmed by the user) |
| Monthly consumption limit | US$50 maximum, including Azure credits |

The current Azure account has an enabled subscription, but no resource group
exists. East US 2 was confirmed after PostgreSQL was found unavailable in East
US. The subscription quota lookup returned inconclusive Container Apps values
and could not read network quota; a separate availability tool could not access
the subscription. Azure CLI and Bicep CLI are unavailable in the local
environment, and the Bicep template is not yet deployable. It lacks private
networking, complete database/Redis endpoint configuration, PostgreSQL Entra
enablement and roles, and registry/image setup. The template has not been
validated with Bicep in this environment.

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

The user's hard limit is **US$50/month of total Azure consumption**, including
Azure for Students credits. A complete itemized estimate for the application
stack has not been validated. Retail catalog results provide candidate minimum
rates for PostgreSQL and Managed Redis, but Container Apps usage, storage,
networking, monitoring, and actual workload are not fully costed. SKU-specific
pricing queries for several services returned no results, and quota
availability could not be verified. Do not provision based on an incomplete
estimate, and do not assume student credits make consumption free.

The user-provided Azure for Students screenshot shows US$100 of US$100 credit
available, expiration on 24 November 2027, and US$0 November cost. This is
user-provided billing evidence, not an independently queried balance. It does
not change the US$50/month consumption cap; credit application and overage
behavior remain unverified.

The user authorized planning an isolated 24-hour Azure test from 25 November
2026 at 18:00 through 26 November 2026 at 18:00 (UTC−05:00), with all Azure
resources created for the test deleted at the end. Existing Vercel/Render
production traffic is to remain unchanged. This window does not approve
unestimated charges or bypass quota, readiness, or cost gates.

The previously checked Fabric reference is outside this phase: Fabric F2
running continuously is approximately US$262.80/month before application
services. Power BI licensing and the user count are also unconfirmed. The user
has deferred Fabric/embedding; Power BI consumers were marked pending.

Before any deployment, produce a current estimate for the exact SKUs and
settings, verify subscription credit/overage behavior, and ensure the full
monthly total stays within US$50. If it cannot, ask the user to change the
budget or scope. Provisioning and production cutover require separate explicit
approval after the estimate.

## Scope Boundaries

- **Included**: Prepare a deployable Azure design for the Python API/worker,
  PostgreSQL analytics warehouse, and Redis; mock-mode tests; security/CVE
  review; cost validation before deployment.
- **Unchanged**: Frontend remains hosted on Vercel.
- **Deferred**: Fabric migration, Power BI PBIP source update, Power BI Service
  publication, and embedding.
- **Excluded**: `backend-spring/` Java service, resource provisioning without
  approval, and any deployment that exceeds the US$50 monthly cap.

## Open Questions & Questionnaire

- [x] Q: Should infrastructure be provisioned now? → A: The user later asked to
  begin deployment; resource creation remains gated on a complete estimate,
  quota/access verification, and approval of the specific resources.
- [x] Q: How should the one-day deployment be used and ended? → A: Isolated
  Azure test, keep current production unchanged, run 25 November 2026 18:00 to
  26 November 2026 18:00 UTC−05:00, then delete the test resources.
- [x] Q: Should integration testing be included? → A: Yes, use mock mode until
  Azure resources are available.
- [x] Q: Should security/CVE remediation be included? → A: Yes.
- [x] Q: Which Azure deployment target should be used? → A: Azure Container
  Apps for the API and separate worker.
- [x] Q: Which subscription and region? → A: Azure for Students, East US 2.
  The user confirmed East US 2 after PostgreSQL was found unavailable in East
  US. The subscription is enabled; no resource groups are present.
- [x] Q: How should Phase 1 handle analytics within the budget? → A: Use the
  Azure PostgreSQL dimensional warehouse; defer Fabric and Power BI embedding.
- [x] Q: What is the monthly Azure consumption limit? → A: US$50 total,
  including student credits.
- [ ] Confirm the exact PostgreSQL, Redis, Container Apps, networking, registry,
  and monitoring SKUs and a complete estimate within the cap.
- [x] Q: What Azure for Students credit is available? → A: The user-provided
  screenshot shows US$100 available, expiring 24 November 2027, and US$0
  November cost.
- [ ] Confirm credit application and whether Azure blocks or bills consumption
  beyond available credit before creating billable resources.
- [ ] Confirm Power BI consumer count and the future Fabric/workspace/licensing
  model before resuming the deferred BI work.
