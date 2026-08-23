-- =====================================================================
-- 001_bank_account.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- The funding account a client trades from.
--   * balance is DECIMAL(18,2)  - money is exact, never float (SEC3-94).
--   * version is the optimistic-concurrency counter: a balance writer
--     reads (balance, version), then writes with
--         UPDATE bank_account SET balance = ?, version = version + 1
--          WHERE account_number = ? AND version = ?
--     and a rowcount of 0 tells the second concurrent writer that it
--     lost the race (SEC3-94: "the second writer ... discovers that it
--     lost").
-- =====================================================================
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

COMMENT ON TABLE  bank_account                IS 'Funding account backing a client. Never hard-deleted.';
COMMENT ON COLUMN bank_account.balance        IS 'Settled cash, DECIMAL(18,2). Never negative.';
COMMENT ON COLUMN bank_account.version        IS 'Optimistic-concurrency counter; bump on every balance write and match it in the WHERE clause.';

COMMIT;
