BEGIN;

CREATE TABLE auth (
    email       VARCHAR(150)    PRIMARY KEY REFERENCES clients(email),
    password    VARCHAR(255)    NOT NULL,
    created     TIMESTAMP       NOT NULL DEFAULT now(),
    updated     TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT chk_auth_password_not_blank CHECK (length(btrim(password)) > 0)
);

COMMIT;
