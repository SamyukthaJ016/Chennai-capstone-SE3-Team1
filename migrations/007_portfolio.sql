BEGIN;

CREATE TABLE portfolio_holding (
    holding_id      BIGSERIAL       PRIMARY KEY,
    client_id       BIGINT          NOT NULL REFERENCES clients(client_id),
    instrument_id   VARCHAR(20)     NOT NULL REFERENCES instruments(instrument_id),
    quantity        INT             NOT NULL,
    price_per_unit  DECIMAL(18,4)   NOT NULL,
    overall_gains   DECIMAL(18,2)   NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_holding_client_instrument UNIQUE (client_id, instrument_id),
    CONSTRAINT chk_portfolio_holding_quantity_non_negative   CHECK (quantity       >= 0),
    CONSTRAINT chk_portfolio_holding_price_non_negative      CHECK (price_per_unit >= 0),
    CONSTRAINT chk_portfolio_holding_updated_not_before_created
        CHECK (updated_at >= created_at)
);

CREATE INDEX idx_portfolio_holding_client_id     ON portfolio_holding(client_id);
CREATE INDEX idx_portfolio_holding_instrument_id ON portfolio_holding(instrument_id);

CREATE TABLE portfolio_positions (
    position_id     BIGSERIAL       PRIMARY KEY,
    client_id       BIGINT          NOT NULL REFERENCES clients(client_id),
    instrument_id   VARCHAR(20)     NOT NULL REFERENCES instruments(instrument_id),
    quantity        INT             NOT NULL,
    price_per_unit  DECIMAL(18,4)   NOT NULL,
    overall_gains   DECIMAL(18,2)   NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_positions_client_instrument UNIQUE (client_id, instrument_id),
    CONSTRAINT chk_portfolio_positions_price_non_negative CHECK (price_per_unit >= 0),
    CONSTRAINT chk_portfolio_positions_updated_not_before_created
        CHECK (updated_at >= created_at)
);

CREATE INDEX idx_portfolio_positions_client_id     ON portfolio_positions(client_id);
CREATE INDEX idx_portfolio_positions_instrument_id ON portfolio_positions(instrument_id);

COMMIT;
