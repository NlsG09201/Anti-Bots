-- =============================================================================
-- StreamShield / Anti-Bots — esquema PostgreSQL para Neon
-- =============================================================================
-- Uso en Neon Console → SQL Editor (base de datos: Anti-Bot):
--   1. Pega y ejecuta este script completo en una base vacía, O
--   2. Si ya tienes tablas (init_postgres / deploy previo), no lo ejecutes de nuevo.
--
-- Equivalente a: python -m scripts.init_postgres
-- Fuente de verdad en código: backend/app/infrastructure/database/models.py
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- -----------------------------------------------------------------------------
-- Tipos ENUM (nombres generados por SQLAlchemy)
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE userrole AS ENUM (
        'super_admin', 'admin', 'analyst', 'streamer', 'viewer'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE platform AS ENUM ('twitch', 'kick', 'youtube');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE attacktype AS ENUM (
        'viewbot', 'followbot', 'chat_raid', 'spam',
        'fake_engagement', 'coordinated', 'distributed'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alertseverity AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE mitigationaction AS ENUM (
        'none', 'quarantine', 'shadow_ban', 'timeout', 'ban', 'mute',
        'rate_limit', 'captcha', 'js_challenge'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- -----------------------------------------------------------------------------
-- Tablas (orden por dependencias de FK)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role userrole NOT NULL DEFAULT 'streamer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMPTZ,
    mfa_secret VARCHAR(255),
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_tenant_email UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    ip_address VARCHAR(45),
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS token_blacklist (
    id UUID PRIMARY KEY,
    jti VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS streams (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform platform NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    channel_name VARCHAR(255) NOT NULL,
    is_live BOOLEAN NOT NULL DEFAULT FALSE,
    viewer_count INTEGER NOT NULL DEFAULT 0,
    oauth_token_encrypted TEXT,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stream_events (
    id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    platform_user_id VARCHAR(255),
    platform_username VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent VARCHAR(512),
    fingerprint_hash VARCHAR(64),
    asn INTEGER,
    country_code VARCHAR(2),
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    is_vpn BOOLEAN NOT NULL DEFAULT FALSE,
    is_tor BOOLEAN NOT NULL DEFAULT FALSE,
    is_datacenter BOOLEAN NOT NULL DEFAULT FALSE,
    risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id VARCHAR(64),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fingerprints (
    id UUID PRIMARY KEY,
    hash VARCHAR(64) NOT NULL UNIQUE,
    canvas_hash VARCHAR(64),
    webgl_hash VARCHAR(64),
    audio_hash VARCHAR(64),
    screen_resolution VARCHAR(20),
    timezone VARCHAR(50),
    language VARCHAR(20),
    platform VARCHAR(50),
    plugins VARCHAR[],
    fonts VARCHAR[],
    is_headless BOOLEAN NOT NULL DEFAULT FALSE,
    is_selenium BOOLEAN NOT NULL DEFAULT FALSE,
    is_puppeteer BOOLEAN NOT NULL DEFAULT FALSE,
    is_playwright BOOLEAN NOT NULL DEFAULT FALSE,
    automation_flags VARCHAR[] NOT NULL DEFAULT '{}',
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ip_reputations (
    id UUID PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL UNIQUE,
    reputation_score DOUBLE PRECISION NOT NULL DEFAULT 50,
    abuse_reports INTEGER NOT NULL DEFAULT 0,
    asn INTEGER,
    asn_org VARCHAR(255),
    country_code VARCHAR(2),
    is_proxy BOOLEAN NOT NULL DEFAULT FALSE,
    is_vpn BOOLEAN NOT NULL DEFAULT FALSE,
    is_tor BOOLEAN NOT NULL DEFAULT FALSE,
    is_datacenter BOOLEAN NOT NULL DEFAULT FALSE,
    is_hosting BOOLEAN NOT NULL DEFAULT FALSE,
    threat_categories VARCHAR[] NOT NULL DEFAULT '{}',
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attacks (
    id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    attack_type attacktype NOT NULL,
    severity alertseverity NOT NULL DEFAULT 'medium',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_ips VARCHAR[] NOT NULL DEFAULT '{}',
    fingerprints VARCHAR[] NOT NULL DEFAULT '{}',
    affected_users INTEGER NOT NULL DEFAULT 0,
    correlation_id VARCHAR(64) NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    mitigation_action mitigationaction NOT NULL DEFAULT 'none',
    mitigated_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    attack_id UUID REFERENCES attacks(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity alertseverity NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    source VARCHAR(50) NOT NULL DEFAULT 'detection_engine',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bans (
    id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target_type VARCHAR(20) NOT NULL,
    target_value VARCHAR(255) NOT NULL,
    reason TEXT NOT NULL,
    ban_type VARCHAR(20) NOT NULL DEFAULT 'ban',
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID,
    is_automated BOOLEAN NOT NULL DEFAULT FALSE,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent VARCHAR(512),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS viewer_sessions (
    id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    platform_user_id VARCHAR(255),
    platform_username VARCHAR(255),
    ip_address VARCHAR(45) NOT NULL,
    fingerprint_hash VARCHAR(64),
    user_agent VARCHAR(512),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    watch_duration_seconds INTEGER NOT NULL DEFAULT 0,
    chat_messages INTEGER NOT NULL DEFAULT 0,
    risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_suspected_bot BOOLEAN NOT NULL DEFAULT FALSE,
    behavior_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- Índices
-- -----------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_slug ON tenants (slug);

CREATE INDEX IF NOT EXISTS ix_users_tenant_role ON users (tenant_id, role);

CREATE UNIQUE INDEX IF NOT EXISTS ix_refresh_tokens_jti ON refresh_tokens (jti);

CREATE UNIQUE INDEX IF NOT EXISTS ix_token_blacklist_jti ON token_blacklist (jti);

CREATE INDEX IF NOT EXISTS ix_streams_platform_external ON streams (platform, external_id);

CREATE INDEX IF NOT EXISTS ix_stream_events_stream_type ON stream_events (stream_id, event_type);
CREATE INDEX IF NOT EXISTS ix_stream_events_correlation ON stream_events (correlation_id);
CREATE INDEX IF NOT EXISTS ix_stream_events_created ON stream_events (created_at);
CREATE INDEX IF NOT EXISTS ix_stream_events_ip_address ON stream_events (ip_address);
CREATE INDEX IF NOT EXISTS ix_stream_events_fingerprint_hash ON stream_events (fingerprint_hash);

CREATE INDEX IF NOT EXISTS ix_fingerprints_hash ON fingerprints (hash);
CREATE INDEX IF NOT EXISTS ix_fingerprints_risk ON fingerprints (risk_score);

CREATE INDEX IF NOT EXISTS ix_ip_reputations_address ON ip_reputations (ip_address);
CREATE INDEX IF NOT EXISTS ix_ip_reputations_score ON ip_reputations (reputation_score);
CREATE INDEX IF NOT EXISTS ix_ip_reputations_asn ON ip_reputations (asn);

CREATE INDEX IF NOT EXISTS ix_attacks_stream_status ON attacks (stream_id, status);
CREATE INDEX IF NOT EXISTS ix_attacks_type_severity ON attacks (attack_type, severity);
CREATE INDEX IF NOT EXISTS ix_attacks_correlation_id ON attacks (correlation_id);

CREATE INDEX IF NOT EXISTS ix_alerts_tenant_status ON alerts (tenant_id, status);

CREATE INDEX IF NOT EXISTS ix_bans_stream_target ON bans (stream_id, target_type, target_value);

CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_created ON audit_logs (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX IF NOT EXISTS ix_viewer_sessions_stream ON viewer_sessions (stream_id, is_active);
CREATE INDEX IF NOT EXISTS ix_viewer_sessions_suspected ON viewer_sessions (stream_id, is_suspected_bot) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS ix_viewer_sessions_fingerprint ON viewer_sessions (fingerprint_hash);

-- -----------------------------------------------------------------------------
-- Verificación
-- -----------------------------------------------------------------------------
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
