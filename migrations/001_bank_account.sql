BEGIN;

CREATE TABLE bank_account (
    account_number  VARCHAR(34)     PRIMARY KEY,
    name            VARCHAR(150)    NOT NULL,
    phone           VARCHAR(20),
    email           VARCHAR(150),
    balance         DECIMAL(18,2)   NOT NULL DEFAULT 0,
    bank_name       VARCHAR(150)    NOT NULL,
    ifsc_code       VARCHAR(11)     NOT NULL,
    version         INT             NOT NULL DEFAULT 0,
    CONSTRAINT chk_bank_account_balance_non_negative CHECK (balance >= 0),
    CONSTRAINT chk_bank_account_version_non_negative CHECK (version  >= 0)
);

COMMIT;
