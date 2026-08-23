BEGIN;

CREATE TABLE in_progress (
    progress_id       SERIAL        PRIMARY KEY,
    order_id          INT           NOT NULL,
    instrument_id     INT           NOT NULL,
    quantity          INT           NOT NULL,
    entered_timestamp TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT fk_in_progress_order_instrument
        FOREIGN KEY (order_id, instrument_id)
        REFERENCES orders (order_id, instrument_id),
    CONSTRAINT chk_in_progress_quantity_positive CHECK (quantity > 0)
);

CREATE INDEX idx_in_progress_order_id      ON in_progress(order_id);
CREATE INDEX idx_in_progress_instrument_id ON in_progress(instrument_id);

COMMIT;
