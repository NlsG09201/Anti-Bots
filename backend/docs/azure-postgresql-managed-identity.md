# Azure Database for PostgreSQL authentication

The backend defaults to `DATABASE_AUTH_MODE=password`, which preserves the
existing local and Render `DATABASE_URL` behavior. To use Microsoft Entra
managed identity, set `DATABASE_AUTH_MODE=managed_identity` and provide a
password-free `DATABASE_URL` using the `postgresql+asyncpg` driver with the
target host, Entra database-role username, and database name. The connection
uses TLS with certificate verification, and the backend obtains a fresh
`https://ossrdbms-aad.database.windows.net/.default` token when opening each
pooled physical connection. `AZURE_CLIENT_ID` can select a user-assigned
identity through the Azure Identity credential chain.

This mode does not create Azure resources, configure Entra authentication, or
grant database permissions. Before enabling it, the target server must have
Microsoft Entra authentication enabled, the API and worker identities must
exist, and each identity must have a PostgreSQL role with the application's
required schema permissions. The current local Bicep template disables
Active Directory authentication and does not create those database roles, so
managed-identity connectivity is not ready to activate. No endpoint, identity,
tenant, or Azure database resource has been confirmed for this local-preparation
task.

This change does not copy data or run schema migrations against Azure. Preserve
the current database until a target, network path, permissions, backup, and
authorized migration window are available.
