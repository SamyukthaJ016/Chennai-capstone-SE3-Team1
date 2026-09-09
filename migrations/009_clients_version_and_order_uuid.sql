BEGIN;

ALTER TABLE clients
    ADD COLUMN version INT NOT NULL DEFAULT 0,
    ADD COLUMN updated_on TIMESTAMP NOT NULL DEFAULT now();

ALTER TABLE orders
    ADD COLUMN order_uuid UUID NOT NULL DEFAULT gen_random_uuid();

ALTER TABLE orders
    ADD CONSTRAINT uq_orders_order_uuid UNIQUE (order_uuid);

COMMIT;