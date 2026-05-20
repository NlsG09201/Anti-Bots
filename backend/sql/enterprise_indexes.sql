-- StreamShield enterprise indexes (PostgreSQL / Neon)
-- Run after base schema. CONCURRENTLY recommended in production.

-- Stream events: time-series queries per stream
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stream_events_stream_created
  ON stream_events (stream_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_stream_events_tenant_created
  ON stream_events (tenant_id, created_at DESC);

-- Viewer sessions: active viewers per stream
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_viewer_sessions_stream_status
  ON viewer_sessions (stream_id, status)
  WHERE status IN ('active', 'suspected');

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_viewer_sessions_stream_risk
  ON viewer_sessions (stream_id, risk_score DESC)
  WHERE status = 'suspected';

-- Attacks: SOC dashboard
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attacks_stream_status
  ON attacks (stream_id, status, started_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attacks_tenant_active
  ON attacks (tenant_id, status)
  WHERE status = 'active';

-- Fingerprints
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fingerprints_hash
  ON fingerprints (fingerprint_hash);

-- Bans: enforcement lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bans_stream_active
  ON bans (stream_id, is_active)
  WHERE is_active = true;

-- Streams: platform listing
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_streams_tenant_platform
  ON streams (tenant_id, platform, is_live);

-- Audit (compliance)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_tenant_created
  ON audit_logs (tenant_id, created_at DESC);
