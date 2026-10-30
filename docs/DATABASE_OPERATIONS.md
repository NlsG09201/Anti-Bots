# Database operations

## PostgreSQL connection pool

The API pool is configured per process with these environment variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `DATABASE_POOL_SIZE` | 10 | Persistent connections per process |
| `DATABASE_MAX_OVERFLOW` | 5 | Temporary connections above the pool |
| `DATABASE_POOL_TIMEOUT_SECONDS` | 30 | Seconds to wait for a connection |
| `DATABASE_POOL_RECYCLE_SECONDS` | 1800 | Recycle age for pooled connections |

Settings validate safe ranges at startup. SQLite does not use these pool options. Compute the potential total as `(pool size + max overflow) × processes × replicas`; keep it below the database connection limit with headroom for workers, migrations, administration, and other clients. Reduce the values when using a constrained hosted database or pooler. Increasing the pool does not increase database capacity by itself.

## Query and index review

The ORM models define indexes for event stream/type and creation time, event idempotency, tenant-scoped alert status, and stream/status attack and incident queries. Additional operational indexes are listed in `backend/sql/enterprise_indexes.sql`, but are not guaranteed to exist in every deployment.

Before adding indexes, capture slow queries and inspect `EXPLAIN (ANALYZE, BUFFERS)` on a representative staging copy. Add schema changes through a tested, versioned migration. Do not create indexes on large production tables during API startup; index builds can block writes and consume substantial I/O.

## Migration and recovery status

See [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md) for the current Alembic baseline limitations and safe change process. See [DATABASE_BACKUP_RECOVERY.md](DATABASE_BACKUP_RECOVERY.md) for backup verification and restore steps. Production migrations require a verified backup and a rehearsed restore path.
