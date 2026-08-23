-- =====================================================================
-- 008_portfolio.sql
-- Team 1 - Trade Database (Postgres) | SEC3-94
--
-- Two structurally identical portfolio tables. Which one a fill lands
-- in is decided by orders.product_type, NOT by anything in these rows:
--
--     orders.product_type = 'DELIVERY'  ->  portfolio_holding
--     orders.product_type = 'INTRADAY'  ->  portfolio_positions
--
-- They are kept as separate tables rather than one table with a flag so
-- that the application layer can treat the two datasets differently
-- (different valuation, different end-of-day handling, different
-- reporting) without every query having to remember a filter.
--
-- THE ONE DELIBERATE DIFFERENCE:
--   portfolio_holding.quantity  >= 0   - you cannot hold negative stock.
--   portfolio_positions.quantity       - UNCONSTRAINED. An intraday
--     position may be SHORT, so a negative quantity is valid data here
--     and means "sold first, still to be bought back". avg_price is the
--     average price of the open leg either way.
--
-- Settlement (reading a terminal transaction and upserting the right
-- table) is handled in the application layer, not in the database.
-- =====================================================================
BEGIN;

-- ---------------------------------------------------------------------
-- PORTFOLIO_HOLDING - delivery / "normal" positions, held overnight
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- PORTFOLIO_POSITIONS - intraday positions, squared off same day
-- ---------------------------------------------------------------------
CREATE TABLE portfolio_positions (
    position_id     SERIAL          PRIMARY KEY,
    client_id       INT             NOT NULL REFERENCES clients(client_id),
    instrument_id   INT             NOT NULL REFERENCES instruments(instrument_id),
    quantity        INT             NOT NULL,
    avg_price       DECIMAL(18,4)   NOT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT now(),
    updated         TIMESTAMP       NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_positions_client_instrument UNIQUE (client_id, instrument_id),
    -- NO non-negative CHECK on quantity: an intraday SHORT is negative.
    CONSTRAINT chk_portfolio_positions_avg_price_non_negative CHECK (avg_price >= 0)
);

CREATE INDEX idx_portfolio_positions_client_id     ON portfolio_positions(client_id);
CREATE INDEX idx_portfolio_positions_instrument_id ON portfolio_positions(instrument_id);

COMMENT ON TABLE  portfolio_holding            IS 'DELIVERY positions. One row per (client, instrument). Quantity is never negative.';
COMMENT ON TABLE  portfolio_positions          IS 'INTRADAY positions. Same shape as portfolio_holding, but quantity may be negative (short).';
COMMENT ON COLUMN portfolio_positions.quantity IS 'Signed: positive = long, negative = short, 0 = squared off.';
COMMENT ON COLUMN portfolio_holding.avg_price  IS 'Weighted-average cost of the open quantity, DECIMAL(18,4).';
COMMENT ON COLUMN portfolio_positions.avg_price IS 'Weighted-average price of the open leg, DECIMAL(18,4).';

COMMIT;
