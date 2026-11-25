# StreamShield Azure infrastructure (Bicep)

This template describes the Azure infrastructure boundary for the Python API and
worker. It contains Azure Container Apps, an Azure Database for PostgreSQL
Flexible Server/database, Azure Managed Redis, and Log Analytics for Container
Apps logs. The Vercel frontend and existing BigQuery pipeline remain outside
this deployment.

## Confirmed trial decisions

- Subscription: Azure for Students `beb4d6e4-38ab-4bc8-aacf-49e4c91db93f`.
- Region: East US 2.
- Window: 2026-11-25 18:00 through 2026-11-26 18:00, UTC-05:00.
- PostgreSQL starts empty; no historical snapshot or production data is used.
- The user accepted an unverified cost estimate and possible spend above
  US$50. This is not a spending cap or an estimate of actual charges.
- Vercel Production and Render production must remain untouched. Power BI and
  Fabric are deferred.

## Do not deploy: readiness blockers

No resource group exists and no Azure resource has been created. The current
`main.bicep` is **not deployment-ready**; local compilation does not validate
Azure provider behavior or prove a working end-to-end deployment. Do not use
this template to deploy until all of these are resolved:

- The template does not configure the required private network path for
  PostgreSQL and Redis, including the required subnets, private endpoint(s),
  private DNS, and Container Apps VNet integration.
- It does not configure Redis managed-identity authorization or the required
  PostgreSQL application identity/role. The existing database connection
  settings and application identity are not wired into the apps.
- It does not provision/configure a private ACR and managed-identity image
  pulls. There are no immutable, published API/worker image references. Do not
  invent tags or use placeholder images.
- Required application settings and secure values are not configured:
  `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `AES_ENCRYPTION_KEY`, HTTPS
  `APP_CORS_ORIGINS`, explicit `TRUSTED_HOSTS`, and the production PostgreSQL
  and Redis connection/authentication settings. Do not commit secret values.
- A dependable deletion automation for the dedicated resource group at the
  confirmed end time has not been implemented or verified. Do not rely on a
  local scheduled task or an untested subscription-wide deletion permission.
- Cost Management could not independently verify costs/credit, and no
  resource-group `what-if` or Azure provider validation has been run. User
  acceptance of cost uncertainty does not resolve the functional or cleanup
  blockers.
- The Docker daemon currently does not respond, so the images cannot be
  rebuilt and locally smoke-tested now. Vercel Preview configuration and its
  URL have not been supplied; production must not be changed.

The API initializes an empty schema at startup, so a historical snapshot is
not required. Only provider registration and read-only Azure checks have been
performed; there has been no deployment, image push, Vercel/Render change, or
data transfer.

Compile locally:

```powershell
az bicep build --file infrastructure\azure\main.bicep --stdout | Out-Null
```

This compiles without writing an ARM JSON artifact. Compilation alone does not
clear any readiness blocker above.

## Before any future deployment

Resolve and locally validate every blocker, pin available AVM module versions
where applicable, and independently verify the deletion automation is scoped
to only the dedicated trial group and runs at the confirmed end time. Then
review the complete template and deployment `what-if` before any provisioning.
Keep all secrets out of the repository and all changes isolated from
production. Do not deploy if any gate remains unresolved.
