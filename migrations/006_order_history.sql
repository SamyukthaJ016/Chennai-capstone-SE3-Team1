BEGIN;

CREATE TABLE order_history (
    history_id        BIGSERIAL     PRIMARY KEY,
    order_id          UUID          NOT NULL REFERENCES orders(order_id),
    event_type        VARCHAR(50)   NOT NULL,
    previous_status   VARCHAR(10),
    new_status        VARCHAR(10),
    external_status   VARCHAR(50),
    external_order_id VARCHAR(100),
    request_id        VARCHAR(100),
    failure_code      VARCHAR(50),
    failure_reason    VARCHAR(255),
    api_response      TEXT,
    event_timestamp   TIMESTAMP     NOT NULL DEFAULT now(),
    created_at        TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT chk_order_history_event_type_not_blank
        CHECK (length(btrim(event_type)) > 0),
    CONSTRAINT chk_order_history_previous_status
        CHECK (
            previous_status IS NULL
            OR previous_status IN ('NEW', 'FILLED', 'REJECTED', 'CANCELLED')
        ),
    CONSTRAINT chk_order_history_new_status
        CHECK (
            new_status IS NULL
            OR new_status IN ('NEW', 'FILLED', 'REJECTED', 'CANCELLED')
        ),
    CONSTRAINT chk_order_history_status_actually_changed
        CHECK (
            previous_status IS NULL
            OR new_status IS NULL
            OR previous_status <> new_status
        )
);

CREATE INDEX idx_order_history_order_id
    ON order_history(order_id, event_timestamp);

CREATE INDEX idx_order_history_new_status
    ON order_history(new_status);

COMMIT;
