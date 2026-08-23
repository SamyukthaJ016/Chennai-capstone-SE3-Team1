-- =====================================================================
-- 000_migration_ledger.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94 / SEC3-95
--
-- Bookkeeping table used by scripts/apply_db.py to record which
-- migrations have already run, so the apply command is safe to run
-- often (SEC3-95 note: "Run it often").
--
-- Uses IF NOT EXISTS so that a plain `psql -f` of every file in
-- filename order still rebuilds the database from these files alone,
-- with or without the Python apply command.
-- =====================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    VARCHAR(255)    PRIMARY KEY,
    checksum    CHAR(64)        NOT NULL,          -- sha256 of the file as applied
    applied_at  TIMESTAMP       NOT NULL DEFAULT now()
);

COMMENT ON TABLE  schema_migrations           IS 'One row per migration file already applied to this database.';
COMMENT ON COLUMN schema_migrations.checksum  IS 'sha256 of the file contents at apply time; a mismatch means a migration was edited after it was applied.';

COMMIT;
