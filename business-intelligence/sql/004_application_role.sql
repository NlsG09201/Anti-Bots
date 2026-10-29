-- Run as the database administrator before setting DATABASE_URL for API/ETL.
-- Replace values; obtain the password from AWS Secrets Manager or another vault.
\set app_user 'streamshield_app'
\set app_password 'REPLACE_WITH_RANDOM_SECRET'
\set app_database 'streamshield'

SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec
ALTER ROLE :"app_user" LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"app_database" TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"app_user" IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"app_user" IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO :"app_user";

GRANT USAGE, CREATE ON SCHEMA bi TO :"app_user";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bi TO :"app_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bi TO :"app_user";
GRANT EXECUTE ON PROCEDURE bi.refresh_warehouse(uuid, date) TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"app_user" IN SCHEMA bi
    GRANT ALL PRIVILEGES ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"app_user" IN SCHEMA bi
    GRANT ALL PRIVILEGES ON SEQUENCES TO :"app_user";
