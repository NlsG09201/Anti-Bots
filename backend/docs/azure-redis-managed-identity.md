# Azure Managed Redis authentication

The API and platform worker use Microsoft Entra managed identity when
`REDIS_AUTH_MODE` is `managed_identity`. `REDIS_URL` must be the Azure Managed
Redis TLS endpoint and must not contain a username or password. Set the same
mode and endpoint for both workloads. Leave
`REDIS_MANAGED_IDENTITY_CLIENT_ID` unset for a system-assigned identity; set it
only when the workload uses a user-assigned identity.

The application uses a refreshable Entra credential provider for the Redis
cache client, ARQ queues, and the Celery Redis result backend. The platform
worker must start through `scripts/platform_monitor_worker.py`; that runner
injects the authenticated ARQ pool. The default ARQ CLI does not support this
provider path. Celery's existing AMQP broker configuration is unchanged.

Before enabling this mode, the Azure Redis resource must be reachable from the
Container Apps environment over TLS, Entra authentication must be enabled, and
the API and worker identities must have the service's required data-plane
permissions. The deployment must provide the real endpoint and identity
assignment. This repository does not contain those resource values or any
credentials.

Upstash REST is not a substitute for the native Redis connection: it does not
provide ARQ queues, Redis Streams, or Pub/Sub. The existing password mode
remains available for local development and Render.

No Azure connection or live Redis authentication was performed during local
preparation. Verify the configured identities and data-plane permissions
against the provisioned Azure resource before switching production workloads.
