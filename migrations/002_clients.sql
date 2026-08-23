-- =====================================================================
-- 002_clients.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- The three account states required by SEC3-94:
--   ACTIVE     - normal, can trade
--   SUSPENDED  - reversible; ACTIVE <-> SUSPENDED both directions allowed
--   CLOSED     - terminal; the row is never deleted, only marked
--
-- CLOSED being one-way is a transition rule, not a row rule, so it is
-- enforced by the trigger below rather than by a CHECK (a CHECK can only
-- see the new row, never the old one).
-- =====================================================================
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

-- CLOSED is terminal: block any transition out of it, and block DELETE
-- outright so a closed account is never removed from the table.
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

COMMENT ON TABLE  clients        IS 'A trading client. Rows are never deleted; closing sets status = CLOSED.';
COMMENT ON COLUMN clients.status IS 'ACTIVE | SUSPENDED | CLOSED. ACTIVE<->SUSPENDED is reversible; CLOSED is terminal.';

COMMIT;
