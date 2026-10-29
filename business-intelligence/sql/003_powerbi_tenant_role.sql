-- Run as the database administrator once for each tenant.
-- Replace the three values below with the tenant's dedicated BI login/password and UUID.
-- The password should be randomly generated, sent through a secret manager, and never committed.
\set bi_user 'powerbi_tenant_001'
\set bi_password 'REPLACE_WITH_RANDOM_SECRET'
\set tenant_id '00000000-0000-0000-0000-000000000000'
\set bi_database 'streamshield'

SELECT format('CREATE ROLE %I LOGIN', :'bi_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'bi_user')
\gexec
ALTER ROLE :"bi_user" LOGIN PASSWORD :'bi_password';
INSERT INTO bi.user_tenant_access(db_role, tenant_id)
VALUES (:'bi_user'::name, :'tenant_id'::uuid)
ON CONFLICT (db_role) DO UPDATE SET tenant_id = EXCLUDED.tenant_id;

GRANT CONNECT ON DATABASE :"bi_database" TO :"bi_user";
GRANT USAGE ON SCHEMA bi TO :"bi_user";
GRANT SELECT ON bi.dim_date, bi.dim_platform,
    bi.vw_powerbi_stream_snapshot,
    bi.vw_powerbi_viewer_session,
    bi.vw_powerbi_attack,
    bi.vw_powerbi_chat_activity,
    bi.vw_powerbi_fact_stream_snapshot,
    bi.vw_powerbi_fact_viewer_session,
    bi.vw_powerbi_fact_attack,
    bi.vw_powerbi_fact_chat_activity,
    bi.vw_powerbi_dim_stream,
    bi.vw_powerbi_dim_streamer
TO :"bi_user";
