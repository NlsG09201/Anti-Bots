# Docker environments

Docker uses isolated workflows: local development has its own Postgres and Redis volumes, tests use in-memory SQLite in a one-shot container, and staging/production use separate environment files and Compose project names. The production VPS setup keeps the existing external PostgreSQL and Caddy architecture; the Next.js frontend can remain on Vercel or be built as the standalone image in `frontend/Dockerfile`.

## Local development

From the repository root:

```sh
docker compose -f deploy/local/docker-compose.dev.yml up --build
```

The stack exposes the UI at `http://localhost:3000`, API at `http://localhost:8000`, and local Postgres/Redis on loopback only. The named Postgres volume persists between runs. Stop with `docker compose -f deploy/local/docker-compose.dev.yml down`; this retains data. `down -v` deletes the local database and should only be used when intentionally resetting it.

Optional resource setting: `API_MEMORY_LIMIT` (defaults to `2G`). Local credentials are disposable development-only values; never reuse them outside a developer machine.

## Tests

Run the backend suite in a clean, disposable container:

```sh
docker compose -f deploy/local/docker-compose.test.yml run --build --rm backend-tests
```

This test environment does not start or connect to development, staging, or production databases/Redis.

## Staging and production VPS

Create an environment file from `deploy/vps/env.example` for production or `deploy/vps/env.staging.example` for staging. Fill in unique secrets, a database dedicated to that environment, hostnames, and provider credentials as needed. Keep the resulting files out of version control and restrict their filesystem permissions.

```sh
docker compose -p anti-bots-staging --env-file deploy/vps/.env.staging up -d --build
docker compose -p anti-bots-production --env-file deploy/vps/.env up -d --build
```

Both environments use the VPS API + Caddy stack, but separate project names, databases, hostnames, and credentials. The staging database must be provisioned separately; Compose does not create or migrate an external database. The optional local Redis cache is enabled with `--profile redis`; set `REDIS_URL` to use it. Back up external databases and keep Compose environment files out of Git.

The API image excludes tests and development dependencies, runs as an unprivileged user, and has a health check. The frontend image uses Next.js standalone output and a non-root runtime. Frontend Docker builds should provide intended public API URLs and `API_PROXY_TARGET` at build time because Next.js rewrites are compiled into the server bundle.
