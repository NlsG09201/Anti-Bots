# StreamShield Azure infrastructure (Bicep)

This template describes the Azure infrastructure boundary for the Python API and
worker. It contains Azure Container Apps, an Azure Database for PostgreSQL
Flexible Server/database, Azure Managed Redis, and Log Analytics for Container
Apps logs. The Vercel frontend and existing BigQuery pipeline remain outside
this deployment.

## Provisioning is disabled

The template is intentionally **not deployed** by this task. The Azure for
Students subscription and East US 2 region are confirmed, but no resource group
exists; registry, SKU selection, and workload sizing remain unconfirmed. The
required image and SKU parameters have no sample values. The PostgreSQL
password is a required secure parameter and has no value in this repository.
Do not add a populated parameter file or commit secret material.

Compile locally without contacting Azure:

```powershell
bicep build infrastructure/azure/main.bicep --no-restore --outfile "$env:TEMP\streamshield-main.json"
```

The generated ARM JSON is a temporary local build artifact and is not committed.
No `az deployment`, resource-group, subscription, quota, or other
Azure-connected command is part of validation for this task.

## Before any future deployment

- Use the confirmed East US 2 region; verify quota and select PostgreSQL/Redis
  SKUs and API/worker sizing.
- Provide private connectivity (VNet integration for Container Apps and
  PostgreSQL, plus a private endpoint and DNS for Managed Redis) before enabling
  application access. PostgreSQL explicitly disables public network access.
  Managed Redis connectivity is not configured in this template and must be
  reviewed before use.
- Revisit PostgreSQL and Redis authentication. The app-service migration tasks
  must implement supported managed-identity authentication or wire secrets
  through an approved secret store; this template contains no credential
  values, connection strings, or Redis keys.
- Supply immutable API and worker image references from an approved registry,
  and configure registry pull authorization without embedding credentials.
- Review cost, backup/HA, monitoring retention, and API ingress exposure.
- Ensure deployment is explicitly authorized and use a protected parameter
  source for the secure PostgreSQL administrator parameter.

The API and worker receive separate system-assigned identities, but this
infrastructure task does not grant data-plane roles or change application
authentication. API ingress is external HTTPS for the Vercel frontend; the
worker has no ingress. PostgreSQL public access is disabled. Managed Redis networking is left
unconfigured; do not treat it as ready for application access until private
connectivity and endpoint exposure have been reviewed.
