BEGIN;

CREATE INDEX idx_orders_client_open_orders
    ON orders (client_id, order_timestamp DESC, order_id DESC)
    WHERE status IN ('RECEIVED', 'IN_PROGRESS');

CREATE INDEX idx_orders_client_order_timestamp
    ON orders (client_id, order_timestamp DESC, order_id DESC);

CREATE INDEX idx_orders_order_timestamp
    ON orders (order_timestamp);

COMMIT;
