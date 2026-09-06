BEGIN;

CREATE TABLE bank_account (
    account_number  VARCHAR(34)     PRIMARY KEY,
    client_id       BIGINT          NOT NULL,
    name            VARCHAR(150)    NOT NULL,
    phone           VARCHAR(20),
    email           VARCHAR(150),
    account_balance DECIMAL(18,2)   NOT NULL DEFAULT 0,
    bank_name       VARCHAR(150)    NOT NULL,
    ifsc_code       VARCHAR(11)     NOT NULL,
    CONSTRAINT chk_bank_account_balance_non_negative CHECK (account_balance >= 0),
    CONSTRAINT chk_bank_account_number_not_blank     CHECK (length(btrim(account_number)) > 0)
);

CREATE INDEX idx_bank_account_client_id ON bank_account(client_id);

COMMIT;
