-- =============================================================================
-- Sprint 4 analytical store (DuckDB)
--
-- Written in plain ANSI SQL rather than DuckDB dialect, for the same reason
-- contracts/analytics-schema.sql is: the model should port to a hosted
-- warehouse without a rewrite. Quoted identifiers are used for "open",
-- "high", "low" and "close" so the DDL is safe on any target that reserves
-- them.
--
-- RELATIONSHIP TO contracts/analytics-schema.sql
--
-- These tables are ADDITIONS, not changes. Nothing here renames a column or
-- alters a table in the binding contract, so no consumer breaks.
--
-- The contract's FACT_TRADES is one row per ORDER: it carries account_key,
-- side, status and quantity. A market candle has none of those -- there is no
-- account behind an end-of-day price and no BUY/SELL on a daily bar. Loading
-- candles into FACT_TRADES would corrupt the grain the contract states and
-- break the Sprint 7 load. So candles get their own table, and FACT_TRADES is
-- left alone until Sprint 7 when the source becomes the platform's own order
-- flow.
--
-- This divergence is declared rather than quiet, as contracts/README.md
-- requires.
--
-- IDEMPOTENCY
--
-- DAILY_PRICE is merged on its natural key (symbol, trade_date): the loader
-- deletes the dates it is about to write, then inserts. Re-running a pull
-- cannot double-count. QUARANTINED_CANDLE is replaced per symbol for the same
-- reason.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- DAILY_PRICE
-- One row per symbol per trading day. The cleaned, typed, derived output of
-- the transform -- the rows that passed validation, including any that were
-- repaired.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_price (
    symbol            VARCHAR(20)    NOT NULL,
    trade_date        DATE           NOT NULL,
    date_key          INTEGER        NOT NULL,
    exchange          VARCHAR(20)    NOT NULL,
    currency          VARCHAR(3),

    "open"            DECIMAL(18,4)  NOT NULL,
    "high"            DECIMAL(18,4)  NOT NULL,
    "low"             DECIMAL(18,4)  NOT NULL,
    "close"           DECIMAL(18,4)  NOT NULL,
    adj_close         DECIMAL(18,4),
    volume            BIGINT,

    price_range       DECIMAL(18,4),
    price_change      DECIMAL(18,4),
    daily_return_pct  DECIMAL(18,6),
    turnover          DECIMAL(24,4),

    synthetic         BOOLEAN        NOT NULL,
    repaired          BOOLEAN        NOT NULL,
    repairs           VARCHAR,

    run_id            VARCHAR(40)    NOT NULL,
    loaded_at         TIMESTAMP      NOT NULL,

    CONSTRAINT pk_daily_price PRIMARY KEY (symbol, trade_date)
);

-- date_key          YYYYMMDD integer, matching DIM_DATE in the contract so
--                   this table can join to it when DIM_DATE is populated.
-- exchange          Derived from the Fauxnance symbol scheme, using the same
--                   rule the contract states for DIM_INSTRUMENT: .NS is NSE,
--                   .BO is BSE, an FX: prefix is FX, X: is crypto, a plain
--                   ticker is a US venue.
-- volume            Nullable. The live API emits a null volume, and a missing
--                   volume does not make the prices wrong.
-- synthetic         The vendor interpolated this candle rather than observing
--                   it. Carried through so a chart can exclude or mark it.
-- repaired          The transform corrected a defect in this row. Charts that
--                   need only observed data should filter on this.
-- repairs           JSON array of {code, detail} describing each correction.
--                   Stored as text rather than a JSON column so the DDL needs
--                   no extension and stays portable.
-- turnover          close * volume. NULL where volume is NULL, not zero: an
--                   unknown turnover is not a turnover of nothing.


-- -----------------------------------------------------------------------------
-- QUARANTINED_CANDLE
-- One row per candle the transform refused to load, with the original payload
-- attached.
--
-- This is the dead-letter table. It exists so that a rejected row is
-- recoverable and countable rather than invisible: rows_kept plus
-- rows_quarantined always reconciles to the candles that arrived, and that
-- reconciliation is checkable in SQL rather than only in a console log.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarantined_candle (
    run_id          VARCHAR(40)   NOT NULL,
    symbol          VARCHAR(20)   NOT NULL,
    raw_date        VARCHAR(40),
    reason          VARCHAR(40)   NOT NULL,
    detail          VARCHAR,
    candle_json     VARCHAR       NOT NULL,
    quarantined_at  TIMESTAMP     NOT NULL
);

-- raw_date      The date exactly as it arrived, unparsed. A row quarantined
--               for a bad date has no valid date to key on, so this is text.
-- reason        The stable reason code from the transform: DUPLICATE_DATE,
--               MISSING_FIELD, NOT_A_NUMBER, HIGH_BELOW_LOW, NEGATIVE_VOLUME,
--               BAD_DATE_FORMAT, NON_POSITIVE_PRICE.
-- candle_json   The original candle, untouched, as JSON text. Quarantine means
--               recoverable: a teammate can see exactly what arrived without
--               re-pulling.


-- -----------------------------------------------------------------------------
-- LOAD_RUN
-- One row per symbol per pipeline run. The ledger that answers "when did this
-- last load, what did it do, and do the numbers add up".
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS load_run (
    run_id            VARCHAR(40)   NOT NULL,
    symbol            VARCHAR(20)   NOT NULL,
    repair_enabled    BOOLEAN       NOT NULL,
    candles_in        INTEGER       NOT NULL,
    rows_kept         INTEGER       NOT NULL,
    rows_repaired     INTEGER       NOT NULL,
    rows_quarantined  INTEGER       NOT NULL,
    date_from         DATE,
    date_to           DATE,
    period_return_pct DECIMAL(18,6),
    avg_volume        DECIMAL(24,4),
    loaded_at         TIMESTAMP     NOT NULL,

    CONSTRAINT pk_load_run PRIMARY KEY (run_id, symbol)
);

-- candles_in    What arrived. candles_in = rows_kept + rows_quarantined is an
--               invariant, and the reconciliation query below checks it.
