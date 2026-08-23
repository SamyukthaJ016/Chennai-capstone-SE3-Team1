BEGIN;

CREATE TABLE clients (
    client_id       SERIAL          PRIMARY KEY,
    account_number  VARCHAR(34)     REFERENCES bank_account(account_number),
    name            VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    NOT NULL UNIQUE,
    phone           VARCHAR(20),
    created_on      TIMESTAMP       NOT NULL DEFAULT now(),
    status          VARCHAR(10)     NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT chk_clients_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE INDEX idx_clients_account_number ON clients(account_number);
CREATE INDEX idx_clients_status         ON clients(status);

CREATE OR REPLACE FUNCTION fn_clients_status_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'client % cannot be deleted; set status = ''CLOSED'' instead', OLD.client_id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.status = 'CLOSED' AND NEW.status <> 'CLOSED' THEN
        RAISE EXCEPTION
            'client % is CLOSED; that state is terminal and cannot be reopened (attempted %)',
            OLD.client_id, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clients_status_transition
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION fn_clients_status_transition();

CREATE TRIGGER trg_clients_no_delete
    BEFORE DELETE ON clients
    FOR EACH ROW EXECUTE FUNCTION fn_clients_status_transition();

COMMIT;
