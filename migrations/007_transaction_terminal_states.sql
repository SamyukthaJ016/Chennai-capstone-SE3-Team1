-- =====================================================================
-- 007_transaction_terminal_states.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- The two terminal outcomes. An order reaches EXACTLY ONE of them:
--   * order_id is UNIQUE within each table, so at most one row per
--     order in each;
--   * the trigger below rejects an insert into either table when the
--     order already has a row in the other one.
-- Together that is "exactly one terminal state, no half-filled state".
--
-- The trigger also advances orders.status, so the order row and the
-- terminal tables can never disagree.
-- =====================================================================
BEGIN;

CREATE TABLE transaction_success (
    transaction_id        SERIAL          PRIMARY KEY,
    order_id              INT             NOT NULL UNIQUE REFERENCES orders(order_id),
    quantity              INT             NOT NULL,
    transaction_timestamp TIMESTAMP       NOT NULL DEFAULT now(),
    value                 DECIMAL(18,2)   NOT NULL,
    CONSTRAINT chk_txn_success_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_txn_success_value_positive    CHECK (value    > 0)
);

CREATE TABLE transaction_failures (
    transaction_id        SERIAL          PRIMARY KEY,
    order_id              INT             NOT NULL UNIQUE REFERENCES orders(order_id),
    quantity              INT             NOT NULL,
    transaction_timestamp TIMESTAMP       NOT NULL DEFAULT now(),
    value                 DECIMAL(18,2)   NOT NULL,
    reason_for_failure    VARCHAR(255)    NOT NULL,
    CONSTRAINT chk_txn_failure_quantity_positive   CHECK (quantity > 0),
    CONSTRAINT chk_txn_failure_value_non_negative  CHECK (value   >= 0),
    CONSTRAINT chk_txn_failure_reason_not_blank    CHECK (length(btrim(reason_for_failure)) > 0)
);

CREATE OR REPLACE FUNCTION fn_enforce_single_terminal_state()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_TABLE_NAME = 'transaction_success' THEN
        IF EXISTS (SELECT 1 FROM transaction_failures WHERE order_id = NEW.order_id) THEN
            RAISE EXCEPTION 'order % already has a FAILED terminal state', NEW.order_id
                USING ERRCODE = 'check_violation';
        END IF;
        UPDATE orders SET status = 'SUCCESS' WHERE order_id = NEW.order_id;

    ELSIF TG_TABLE_NAME = 'transaction_failures' THEN
        IF EXISTS (SELECT 1 FROM transaction_success WHERE order_id = NEW.order_id) THEN
            RAISE EXCEPTION 'order % already has a SUCCESS terminal state', NEW.order_id
                USING ERRCODE = 'check_violation';
        END IF;
        UPDATE orders SET status = 'FAILED' WHERE order_id = NEW.order_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transaction_success_terminal
    BEFORE INSERT ON transaction_success
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_single_terminal_state();

CREATE TRIGGER trg_transaction_failures_terminal
    BEFORE INSERT ON transaction_failures
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_single_terminal_state();

COMMENT ON TABLE transaction_success  IS 'Terminal SUCCESS outcome. At most one row per order, and never alongside a transaction_failures row.';
COMMENT ON TABLE transaction_failures IS 'Terminal FAILED outcome. At most one row per order, and never alongside a transaction_success row.';

COMMIT;
