-- H2-compatible schema for unit and integration tests.
-- Derived from migrations/001-009.sql, stripped of PostgreSQL-specific triggers,
-- PL/pgSQL functions, and deferred FK constraints that H2 does not support.
--
-- Each Spring test context re-initializes the shared in-memory testdb, so all
-- tables are dropped first to guarantee a deterministic empty state.

DROP TABLE IF EXISTS clients;
DROP TABLE IF EXISTS bank_account;
DROP TABLE IF EXISTS auth;
DROP TABLE IF EXISTS instruments;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS order_history;
DROP TABLE IF EXISTS portfolio_holding;
DROP TABLE IF EXISTS portfolio_positions;
DROP TABLE IF EXISTS positions;
DROP TABLE IF EXISTS holdings;

CREATE TABLE clients (
    client_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_number  VARCHAR(34),
    name            VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    NOT NULL UNIQUE,
    phone           VARCHAR(20),
    created_on      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    account_state   VARCHAR(10)     NOT NULL DEFAULT 'ACTIVE',
    wallet_balance  DECIMAL(18,2)   NOT NULL DEFAULT 0,
    version         INT             NOT NULL DEFAULT 0,
    updated_on      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bank_account (
    account_number  VARCHAR(34)     PRIMARY KEY,
    client_id       BIGINT          NOT NULL,
    name            VARCHAR(150)    NOT NULL,
    phone           VARCHAR(20),
    email           VARCHAR(150),
    account_balance DECIMAL(18,2)   NOT NULL DEFAULT 0,
    bank_name       VARCHAR(150)    NOT NULL,
    ifsc_code       VARCHAR(11)     NOT NULL
);

CREATE TABLE auth (
    email         VARCHAR(150)  PRIMARY KEY,
    password_hash VARCHAR(255)  NOT NULL,
    created       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version       INT           NOT NULL DEFAULT 0
);

CREATE TABLE instruments (
    instrument_id   VARCHAR(20)     PRIMARY KEY,
    instrument_name VARCHAR(150)    NOT NULL UNIQUE,
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    updated_on      TIMESTAMP
);

CREATE TABLE orders (
    order_id          UUID            PRIMARY KEY,
    client_id         BIGINT          NOT NULL,
    account_id        BIGINT          NOT NULL,
    instrument_id     VARCHAR(20)     NOT NULL,
    order_type        VARCHAR(8)      NOT NULL,
    side              VARCHAR(4)      NOT NULL,
    quantity          DECIMAL(18,4)   NOT NULL,
    price             DECIMAL(18,4)   NOT NULL,
    executed_price    DECIMAL(18,4),
    status            VARCHAR(10)     NOT NULL DEFAULT 'NEW',
    idempotency_key   VARCHAR(100)    NOT NULL,
    external_order_id VARCHAR(100),
    created_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_orders_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE order_history (
    history_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id          UUID          NOT NULL,
    event_type        VARCHAR(50)   NOT NULL,
    previous_status   VARCHAR(10),
    new_status        VARCHAR(10),
    external_status   VARCHAR(50),
    external_order_id VARCHAR(100),
    request_id        VARCHAR(100),
    failure_code      VARCHAR(50),
    failure_reason    VARCHAR(255),
    api_response      TEXT,
    event_timestamp   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE portfolio_holding (
    holding_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id       BIGINT          NOT NULL,
    instrument_id   VARCHAR(20)     NOT NULL,
    quantity        INT             NOT NULL,
    price_per_unit  DECIMAL(18,4)   NOT NULL,
    overall_gains   DECIMAL(18,2)   NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_portfolio_holding_client_instrument UNIQUE (client_id, instrument_id)
);

CREATE TABLE portfolio_positions (
    position_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    client_id       BIGINT          NOT NULL,
    instrument_id   VARCHAR(20)     NOT NULL,
    quantity        INT             NOT NULL,
    price_per_unit  DECIMAL(18,4)   NOT NULL,
    overall_gains   DECIMAL(18,2)   NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_portfolio_positions_client_instrument UNIQUE (client_id, instrument_id)
);

-- Tables referenced by PositionMapper (named differently from portfolio tables)
CREATE TABLE positions (
    account_id      BIGINT          NOT NULL,
    instrument_id   VARCHAR(20)     NOT NULL,
    quantity        INT             NOT NULL,
    avg_price       DECIMAL(18,4)   NOT NULL,
    CONSTRAINT uq_positions_account_instrument UNIQUE (account_id, instrument_id)
);

CREATE TABLE holdings (
    account_id      BIGINT          NOT NULL,
    instrument_id   VARCHAR(20)     NOT NULL,
    quantity        INT             NOT NULL,
    CONSTRAINT uq_holdings_account_instrument UNIQUE (account_id, instrument_id)
);
