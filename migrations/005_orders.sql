BEGIN;

CREATE TABLE orders (
    order_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id         BIGINT          NOT NULL REFERENCES clients(client_id),
    account_id        BIGINT          NOT NULL,
    instrument_id     VARCHAR(20)     NOT NULL REFERENCES instruments(instrument_id),
    order_type        VARCHAR(8)      NOT NULL,
    side              VARCHAR(4)      NOT NULL,
    quantity          DECIMAL(18,4)   NOT NULL,
    price             DECIMAL(18,4)   NOT NULL,
    executed_price    DECIMAL(18,4),
    status            VARCHAR(10)     NOT NULL DEFAULT 'NEW',
    idempotency_key   VARCHAR(100)    NOT NULL,
    external_order_id VARCHAR(100),
    created_at        TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_orders_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT chk_orders_order_type CHECK (order_type IN ('POSITION', 'HOLDING')),
    CONSTRAINT chk_orders_side       CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_orders_status
        CHECK (status IN ('NEW', 'FILLED', 'REJECTED', 'CANCELLED')),
    CONSTRAINT chk_orders_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_orders_price_positive
        CHECK (price > 0),
    CONSTRAINT chk_orders_executed_price_positive
        CHECK (executed_price IS NULL OR executed_price > 0),
    CONSTRAINT chk_orders_filled_has_executed_price
        CHECK (status <> 'FILLED' OR executed_price IS NOT NULL),
    CONSTRAINT chk_orders_executed_price_only_when_filled
        CHECK (status = 'FILLED' OR executed_price IS NULL),
    CONSTRAINT chk_orders_updated_not_before_created
        CHECK (updated_at >= created_at)
);

CREATE INDEX idx_orders_client_id     ON orders(client_id);
CREATE INDEX idx_orders_account_id    ON orders(account_id);
CREATE INDEX idx_orders_instrument_id ON orders(instrument_id);
CREATE INDEX idx_orders_status        ON orders(status);
CREATE INDEX idx_orders_order_type    ON orders(order_type);

COMMIT;
