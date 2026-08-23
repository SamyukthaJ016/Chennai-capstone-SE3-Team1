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

COMMIT;
