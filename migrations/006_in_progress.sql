-- =====================================================================
-- 006_in_progress.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- The working queue. An order that has been picked up for execution
-- gets a row here (and orders.status moves to IN_PROGRESS); when it
-- resolves it lands in transaction_success or transaction_failures.
--
-- instrument_id is a COMPOSITE foreign key together with order_id:
--
--     FOREIGN KEY (order_id, instrument_id)
--       REFERENCES orders (order_id, instrument_id)
--
-- and NOT a plain reference to instruments. The column duplicates
-- orders.instrument_id, and a plain FK to instruments would only prove
-- the instrument exists - it would happily let a queue row claim order 5
-- is for INFY while the order itself says RELIANCE. The composite FK
-- makes that disagreement impossible, and the instrument is still
-- guaranteed to exist transitively, because orders.instrument_id has its
-- own FK to instruments.
--
-- NOTE: order_id is deliberately NOT unique here. A retried execution
-- attempt can legitimately re-enter the queue. Uniqueness of the
-- OUTCOME is what matters, and that is enforced in 007.
-- =====================================================================
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

COMMENT ON TABLE  in_progress               IS 'Orders currently being executed. One order may re-enter on retry; the terminal outcome is what is unique.';
COMMENT ON COLUMN in_progress.instrument_id IS 'Must match the order''s instrument: enforced by the composite FK to orders (order_id, instrument_id).';

COMMIT;
