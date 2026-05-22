-- Añade TikTok al enum platform (idempotente en PostgreSQL 12+)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'platform' AND e.enumlabel = 'tiktok'
    ) THEN
        ALTER TYPE platform ADD VALUE 'tiktok';
    END IF;
END $$;
