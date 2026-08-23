-- =====================================================================
-- 005_orders.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- An order is recorded the moment it is RECEIVED and then walks:
--     RECEIVED -> IN_PROGRESS -> SUCCESS | FAILED
-- exactly one terminal state, no half-filled state (SEC3-94).
--
-- product_type is what decides where a fill eventually lands:
--     INTRADAY -> portfolio_positions   (squared off same day)
--     DELIVERY -> portfolio_holding     ("normal", settles into holdings)
-- It is NOT NULL with NO DEFAULT on purpose. A default would let a
-- caller that forgot to set it silently book an intraday fill into
-- long-term holdings - exactly the "mapping bug becomes missing data
-- nobody notices" failure SEC3-95 warns about. Make the caller say it.
--
-- idempotency_key is UNIQUE at the database level, not checked with a
-- read-then-write, so two concurrent identical requests cannot both
-- pass; the loser gets SQLSTATE 23505 (SEC3-94, and Sprint 6 depends on
-- that unique violation being detectable).
-- =====================================================================
BEGIN;

CREATE TABLE orders (
    order_id        SERIAL          PRIMARY KEY,
    instrument_id   INT             NOT NULL REFERENCES instruments(instrument_id),
    client_id       INT             NOT NULL REFERENCES clients(client_id),
    price_per_unit  DECIMAL(18,4)   NOT NULL,
    type            VARCHAR(4)      NOT NULL,
    product_type    VARCHAR(8)      NOT NULL,
    quantity        INT             NOT NULL,
    exchange        VARCHAR(20)     NOT NULL,
    order_timestamp TIMESTAMP       NOT NULL DEFAULT now(),
    idempotency_key VARCHAR(100)    NOT NULL,
    status          VARCHAR(12)     NOT NULL DEFAULT 'RECEIVED',
    CONSTRAINT uq_orders_idempotency_key UNIQUE (idempotency_key),
    -- Redundant on its own (order_id is already the PK), but a composite FK
    -- needs a matching unique key to point at. in_progress uses it to
    -- guarantee its instrument_id agrees with this order's. See 006.
    CONSTRAINT uq_orders_order_instrument UNIQUE (order_id, instrument_id),
    CONSTRAINT chk_orders_type          CHECK (type         IN ('BUY', 'SELL')),
    CONSTRAINT chk_orders_product_type  CHECK (product_type IN ('INTRADAY', 'DELIVERY')),
    CONSTRAINT chk_orders_status        CHECK (status       IN ('RECEIVED', 'IN_PROGRESS', 'SUCCESS', 'FAILED')),
    CONSTRAINT chk_orders_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_orders_price_positive    CHECK (price_per_unit > 0)
);

CREATE INDEX idx_orders_client_id     ON orders(client_id);
CREATE INDEX idx_orders_instrument_id ON orders(instrument_id);
CREATE INDEX idx_orders_status        ON orders(status);
CREATE INDEX idx_orders_product_type  ON orders(product_type);

COMMENT ON TABLE  orders                 IS 'Every order as received. RECEIVED -> IN_PROGRESS -> exactly one of SUCCESS / FAILED.';
COMMENT ON COLUMN orders.type            IS 'Side of the trade: BUY or SELL.';
COMMENT ON COLUMN orders.product_type    IS 'INTRADAY settles into portfolio_positions; DELIVERY settles into portfolio_holding. No default: the caller must be explicit.';
COMMENT ON COLUMN orders.idempotency_key IS 'Caller-supplied dedupe key. UNIQUE in the database, so a retry raises SQLSTATE 23505 instead of double-booking.';
COMMENT ON COLUMN orders.price_per_unit  IS 'Limit/traded price, DECIMAL(18,4).';

COMMIT;
