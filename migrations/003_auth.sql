-- =====================================================================
-- 003_auth.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- Login credentials, keyed on the client's email (clients.email is
-- UNIQUE, so it is a valid FK target).
--
-- password holds a HASH, never a plaintext password. The length is
-- sized for a bcrypt/argon2 encoded string.
-- =====================================================================
BEGIN;

CREATE TABLE auth (
    email       VARCHAR(150)    PRIMARY KEY REFERENCES clients(email),
    password    VARCHAR(255)    NOT NULL,
    created     TIMESTAMP       NOT NULL DEFAULT now(),
    updated     TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT chk_auth_password_not_blank CHECK (length(btrim(password)) > 0)
);

COMMENT ON TABLE  auth          IS 'Credentials for a client, one row per client email.';
COMMENT ON COLUMN auth.password IS 'Password HASH (bcrypt/argon2 encoded string). Never store plaintext.';

COMMIT;
