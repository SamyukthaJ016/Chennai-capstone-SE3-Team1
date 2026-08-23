BEGIN;

CREATE TABLE portfolio_holding (
    holding_id      SERIAL          PRIMARY KEY,
    client_id       INT             NOT NULL REFERENCES clients(client_id),
    instrument_id   INT             NOT NULL REFERENCES instruments(instrument_id),
    quantity        INT             NOT NULL,
    avg_price       DECIMAL(18,4)   NOT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated         TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_holding_client_instrument UNIQUE (client_id, instrument_id),
    CONSTRAINT chk_portfolio_holding_quantity_non_negative  CHECK (quantity  >= 0),
    CONSTRAINT chk_portfolio_holding_avg_price_non_negative CHECK (avg_price >= 0)
);

CREATE INDEX idx_portfolio_holding_client_id     ON portfolio_holding(client_id);
CREATE INDEX idx_portfolio_holding_instrument_id ON portfolio_holding(instrument_id);

CREATE TABLE portfolio_positions (
    position_id     SERIAL          PRIMARY KEY,
    client_id       INT             NOT NULL REFERENCES clients(client_id),
    instrument_id   INT             NOT NULL REFERENCES instruments(instrument_id),
    quantity        INT             NOT NULL,
    avg_price       DECIMAL(18,4)   NOT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated         TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_positions_client_instrument UNIQUE (client_id, instrument_id),
    CONSTRAINT chk_portfolio_positions_avg_price_non_negative CHECK (avg_price >= 0)
);

CREATE INDEX idx_portfolio_positions_client_id     ON portfolio_positions(client_id);
CREATE INDEX idx_portfolio_positions_instrument_id ON portfolio_positions(instrument_id);

COMMIT;
