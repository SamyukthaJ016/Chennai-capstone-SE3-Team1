BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    VARCHAR(255)    PRIMARY KEY,
    checksum    CHAR(64)        NOT NULL,
    applied_at  TIMESTAMP       NOT NULL DEFAULT now()
);

COMMIT;
