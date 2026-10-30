# Data stores — PostgreSQL, Redis, and optional MongoDB

## Production (current)

| Store | Role | Service |
|-------|------|---------|
| **PostgreSQL (Neon)** | OLTP: users, streams, sessions, attacks, audit | Primary source of truth |
| **Redis (Upstash)** | Rate limits, event streams, baselines, pub/sub | Real-time layer |

Indexes: `backend/sql/enterprise_indexes.sql` is a manual optimization script and is not guaranteed to have been applied in every environment. Alembic's current history is not verified for new or existing databases; review [`docs/DATABASE_MIGRATIONS.md`](../docs/DATABASE_MIGRATIONS.md) before applying schema changes.

Redis keys: see `backend/app/infrastructure/cache/redis_schema.py`.

## MongoDB (optional — not required)

StreamShield does **not** require MongoDB today. For analytics at **millions of events/day**, you may add MongoDB Atlas as a **cold archive**:

- Collection `raw_events` with TTL 90 days
- Compound index `{ tenant_id: 1, stream_id: 1, created_at: -1 }`
- Write path: async worker after Postgres `stream_events` insert

Use the MongoDB plugin skills when you enable this path.

## Scaling checklist

1. Apply `enterprise_indexes.sql`
2. Enable `EVENT_PIPELINE_ENABLED` + arq worker
3. Deploy multiple API instances behind one Redis
4. Set `event_stream_max_len` and consumer `batch_size` per load
5. Postgres read replica for dashboard read queries (future)
