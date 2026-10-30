# Alert system: current implementation

This file replaces an obsolete implementation draft. The former draft described an unmounted, unauthenticated API and a second `Alert` model that conflicted with the active schema; those unreachable modules have been removed.

## Active API

Alert endpoints are registered through `backend/app/api/v1/attacks.py` under `/api/v1`:

- `GET /api/v1/alerts` lists alerts for the authenticated user's tenant. Optional `status` and `stream_id` filters are supported.
- `PATCH /api/v1/alerts/{alert_id}/acknowledge` acknowledges a tenant-owned alert.
- `PATCH /api/v1/alerts/{alert_id}/dismiss` dismisses a tenant-owned alert.

The routes use the operational `Alert` model in `backend/app/infrastructure/database/models.py`; cross-tenant alert IDs return not found. Alert generation and storage paths are documented in their respective services and tests.

## Schema changes

Do not apply the historical Alembic instructions from earlier copies of this document. The current Alembic chain has not been reconciled with the deployed schema and the legacy alerts migration defines a conflicting table. Review [`docs/DATABASE_MIGRATIONS.md`](docs/DATABASE_MIGRATIONS.md) before changing or applying migrations.
