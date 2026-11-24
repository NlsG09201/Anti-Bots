# Modernization Plan: StreamShield Azure and Power BI

**Project**: Anti-Bots / StreamShield

## Technical Framework

- **Language**: Python 3.11 for the in-scope backend; TypeScript for the frontend
- **Framework**: FastAPI 0.161.1; Next.js frontend remains on Vercel
- **Build Tool**: pip/uv for Python; npm for the frontend
- **Database**: PostgreSQL and Redis on Render
- **Key Dependencies**: SQLAlchemy, asyncpg, Redis/arq, Celery, BigQuery client

## Overview

This modernization moves the StreamShield Python API, separate worker, PostgreSQL
database, and Redis service from Render to Azure while preserving the existing
BigQuery analytics pipeline and Vercel-hosted frontend. Azure Container Apps is
the target for the API and worker. The plan also prepares Bicep for a future
Azure environment and includes publication of the existing Power BI project
artifacts and embedding of a Power BI report in the application.

The work is staged so that:

- The Azure service configuration and Bicep can be prepared without provisioning
  any resources.
- The API and worker can move to the planned Azure services after an Azure
  subscription and resources are available.
- The Power BI PBIP artifacts can be published and embedded after the required
  Power BI Service workspace and capacity are confirmed.
- Integration verification uses mock mode until an Azure environment is
  available.

## Migration Impact Summary

| Application | Original Service | New Azure Service | Authentication | Comments |
|-------------|------------------|-------------------|----------------|----------|
| Python API | Render | Azure Container Apps | Managed identity | Deployment is gated |
| Worker | Render | Azure Container Apps | Managed identity | Separate worker workload |
| PostgreSQL | Render | Azure Database for PostgreSQL | Managed identity | Keep data and schema |
| Redis | Render | Azure Managed Redis | Managed identity | Preserve queue/cache use |
| Power BI | Local PBIP artifacts | Power BI Service | Service principal | Workspace/capacity TBD |
| Frontend | Vercel | Vercel | Existing auth | Remains out of Azure scope |

## Infrastructure Plan

**Plan configuration**

| Parameter | Value |
|-----------|-------|
| IaC Tool | Bicep |
| Provision | false |
| Subscription | Not available; obtain before future deployment |

The plan prepares Bicep for the Azure target architecture, but does not create,
configure, or provision Azure resources. Azure Container Apps is the default
compute target for the API and worker. Azure Database for PostgreSQL and Azure
Managed Redis are the intended managed data services. No resource identifiers,
credentials, or subscription details are known or included.

```text
Vercel frontend (unchanged)
        |
        +---- Power BI embedded report (Power BI Service; prerequisites TBD)
        |
Azure Container Apps: FastAPI API + separate worker
        |                         |
Azure Database for PostgreSQL   Azure Managed Redis
        |
Existing BigQuery analytics pipeline (unchanged)
```

Power BI publication targets the existing PBIP artifacts under
`business-intelligence/powerbi`. No published report or Power BI Service
workspace is confirmed. Use the app-owns-data/service-principal approach for
embedding, subject to tenant configuration, a workspace, suitable capacity or
licensing, and the required Power BI permissions. These prerequisites and their
cost implications must be documented before publication or embedding. Do not
place credentials or service-principal secrets in source control or the plan.

## Scope Boundaries

- **Included**: `backend/` Python 3.11 API and worker, PostgreSQL, Redis,
  Bicep generation without provisioning, future Azure Container Apps
  deployment, Power BI PBIP publication and application embedding, mock-mode
  integration tests, and security/CVE remediation.
- **Unchanged**: `frontend/` stays hosted on Vercel; the existing BigQuery
  pipeline and data destination remain in place.
- **Excluded**: `backend-spring/` Java 21 service; BigQuery-to-Fabric migration;
  Azure resource provisioning; and any runtime upgrade.

## Open Questions & Questionnaire

- [x] Q: Should the plan include environment/infrastructure provisioning? →
  A: Generate Bicep for a future Azure setup, but do not provision resources
  (`provision: false`). No Azure subscription or resources are currently
  available.
- [x] Q: Should the plan include integration testing? →
  A: Yes, use mock mode because no Azure environment is available, and include
  the mandatory `setupBaseline` task.
- [x] Q: Should the plan include security/CVE remediation? →
  A: Yes, include security/CVE remediation by default.
- [x] Q: Which Azure deployment target should the plan use? →
  A: Azure Container Apps for the API and separate worker; future deployment is
  gated on an Azure subscription and resources.
- [x] Q: Should containerization be a separate task? →
  A: No. Containerization is covered by the Azure Container Apps deployment
  task.
- [x] Q: Is the confirmed plan scope correct? →
  A: Yes. The freeform response “cuaslquiera” is treated as a typo with no
  actionable scope change.
- [ ] Which Microsoft Entra tenant, Power BI workspace, and Power BI capacity
  identifiers should be used? No Power BI Service workspace or published
  report has been confirmed. Confirm identifiers and capacity/licensing before
  publishing or embedding.
- [ ] Which Azure subscription, region, resource group, and service sizing
  should be used when the future deployment is authorized?
