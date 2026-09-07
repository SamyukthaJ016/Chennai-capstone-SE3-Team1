CREATE TABLE IF NOT EXISTS daily_price (
    symbol            VARCHAR(20)    NOT NULL,
    trade_date        DATE           NOT NULL,
    "interval"        VARCHAR(10)    NOT NULL,
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

    CONSTRAINT pk_daily_price PRIMARY KEY (symbol, trade_date, "interval")
);


CREATE TABLE IF NOT EXISTS quarantined_candle (
    run_id          VARCHAR(40)   NOT NULL,
    symbol          VARCHAR(20)   NOT NULL,
    raw_date        VARCHAR(40),
    reason          VARCHAR(40)   NOT NULL,
    detail          VARCHAR,
    candle_json     VARCHAR       NOT NULL,
    quarantined_at  TIMESTAMP     NOT NULL
);


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


CREATE TABLE IF NOT EXISTS run_metric (
    run_id      VARCHAR(40)    NOT NULL,
    symbol      VARCHAR(20)    NOT NULL,
    metric      VARCHAR(40)    NOT NULL,
    label       VARCHAR(80)    NOT NULL,
    unit        VARCHAR(10)    NOT NULL,
    value       DECIMAL(24,6)  NOT NULL,
    computed_at TIMESTAMP      NOT NULL,

    CONSTRAINT pk_run_metric PRIMARY KEY (run_id, symbol, metric)
);
