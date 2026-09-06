BEGIN;

CREATE TABLE clients (
    client_id       BIGSERIAL       PRIMARY KEY,
    account_number  VARCHAR(34)     REFERENCES bank_account(account_number),
    name            VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    NOT NULL UNIQUE,
    phone           VARCHAR(20),
    created_on      TIMESTAMP       NOT NULL DEFAULT now(),
    account_state   VARCHAR(10)     NOT NULL DEFAULT 'ACTIVE',
    wallet_balance  DECIMAL(18,2)   NOT NULL DEFAULT 0,
    CONSTRAINT chk_clients_account_state
        CHECK (account_state IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    CONSTRAINT chk_clients_wallet_balance_non_negative CHECK (wallet_balance >= 0)
);

ALTER TABLE bank_account
    ADD CONSTRAINT fk_bank_account_client
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX idx_clients_account_number ON clients(account_number);
CREATE INDEX idx_clients_account_state  ON clients(account_state);

CREATE OR REPLACE FUNCTION fn_clients_state_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'client % cannot be deleted; set account_state = ''CLOSED'' instead', OLD.client_id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.account_state = 'CLOSED' AND NEW.account_state <> 'CLOSED' THEN
        RAISE EXCEPTION
            'client % is CLOSED; that state is terminal and cannot be reopened (attempted %)',
            OLD.client_id, NEW.account_state
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clients_state_transition
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION fn_clients_state_transition();

CREATE TRIGGER trg_clients_no_delete
    BEFORE DELETE ON clients
    FOR EACH ROW EXECUTE FUNCTION fn_clients_state_transition();

COMMIT;
