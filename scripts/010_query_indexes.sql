BEGIN;

CREATE INDEX idx_orders_client_open_orders
    ON orders (client_id, created_at DESC, order_id DESC)
    WHERE status = 'NEW';

CREATE INDEX idx_orders_client_created_at
    ON orders (client_id, created_at DESC, order_id DESC);

CREATE INDEX idx_orders_created_at
    ON orders (created_at);

COMMIT;
