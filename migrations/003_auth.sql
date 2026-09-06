BEGIN;

CREATE TABLE auth (
    email         VARCHAR(150)  PRIMARY KEY REFERENCES clients(email),
    password_hash VARCHAR(255)  NOT NULL,
    created       TIMESTAMP     NOT NULL DEFAULT now(),
    updated       TIMESTAMP     NOT NULL DEFAULT now(),
    version       INT           NOT NULL DEFAULT 0,
    CONSTRAINT chk_auth_password_not_blank    CHECK (length(btrim(password_hash)) > 0),
    CONSTRAINT chk_auth_version_non_negative  CHECK (version >= 0),
    CONSTRAINT chk_auth_updated_not_before_created CHECK (updated >= created)
);

COMMIT;
