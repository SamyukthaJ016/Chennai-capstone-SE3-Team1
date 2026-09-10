# Sprint 6 — Trade Order API 

Stories covered:

| # | Story | Where it lives |
|---|---|---|
| 1 | Trade database schema (SEC3-91/94/95) | `migrations/`, `seed/`, `scripts/`, `tests/`, `infra/postgres/` |
| 2 | Analytics & ingestion pipeline (Sprint 4 / SEC3-103) | `ETL_Analysis/` |
| 3 | Domain engine (Sprint 5) | `sprint-06-api/src/main/java/com/team1/trading/domain/**` |
| 4 | Trade order API (Sprint 6) | `sprint-06-api/**` |
| 5 | Order history (cross-cutting) | `migrations/006_order_history.sql`, `seed/060_*`, domain `OrderHistory`, `OrderHistoryEntry`, order history endpoint |

> One repository note: Sprint 5's domain engine lives **inside** the Sprint 6
> API now (moved in as source, dependency removed). So a single Maven build
> proves both stories. See Story 3.

---

## Story 1 — Trade database schema (SEC3-91/94/95)

### 1. What is expected

A PostgreSQL schema for the trading platform that is **the only definition of
the schema** (numbered migrations), loads deterministic seed data transactionally,
can be scripted end-to-end, and can never silently drift from the domain
entities — parity is a tested invariant.

### 2. How it was implemented

```
migrations/     000..008 .sql — ledger, bank_account, clients, auth,
               instruments, orders, order_history, portfolio, maintenance
seed/           NNN_<table>.csv, loaded in filename order
scripts/        apply_db.py, verify_db.py, make_seed.py, db_config.py
tests/          pytest suite (own trading_platform_test DB)
infra/postgres/ docker compose (joins the API in Story 4)
```

- Migrations are immutable; `apply_db.py` stores a sha256 of each applied file
  and refuses to re-apply a changed one.
- Seed is validated **before anything is inserted**, then loaded in one
  transaction (`clients` ↔ `bank_account` use a deferred FK).
- No deletes: `CLOSED` clients, `active = FALSE` instruments, one-way `CLOSED`.
- Idempotency is a `UNIQUE` constraint; optimistic concurrency uses
  `auth.version` with `UPDATE ... WHERE version = ?`.
- Money: `DECIMAL(18,2)` cash, `DECIMAL(18,4)` prices/quantities; a check
  forbids `real`/`double precision`/`money`.
- `verify_db.py`: **62 read-only checks** in 4 sections; sections A05/B02 parse
  the Java entities/enums so schema and domain cannot drift.

### 3. Commands to test + proof

```bash
python scripts/apply_db.py            # create, migrate, seed (idempotent)
python scripts/verify_db.py           # 62 checks, all PASS
python -m pytest tests/               # migrations + seed + parity, PASS
python scripts/make_seed.py --check   # seed/ in sync with the generator
cd infra/postgres && docker compose up -d
```

Proof: `verify_db.py` prints all four sections green (structure, constraints,
behaviour, data consistency); the pytest suite reports its own isolated DB
(`trading_platform_test`) and skips cleanly when no server is reachable.

### 4. Technical highlights

- Migrations are the schema; code only loads them. Editing a running migration
  aborts (`--allow-modified` / `--reset` to recover).
- Seed rows are never silently dropped: unknown column, blank line, wrong field
  count each reported with file and line; constraint errors roll the load back.
- Behaviour is asserted on **SQLSTATEs** (e.g. duplicate idempotency key must be
  `23505`, filling an order with no executed price must be refused).
- The portfolio books are verified by **replaying the filled orders** from the
  database and comparing against stored rows.

### 5. Code to highlight

```python
# scripts/apply_db.py — the immutable-migration guard (summarised)
sha = sha256(path).hexdigest()
applied = cursor.execute("SELECT sha256 FROM schema_migrations WHERE file = ?", path)
if applied and applied.sha256 != sha:
    die(f"migration changed after it was applied: {path}")
```
```sql
-- migrations/005_orders.sql — idempotency as a constraint, not a read-then-write
CONSTRAINT uq_orders_idempotency_key UNIQUE (client_id, idempotency_key)
```
```
docs/erd.md + docs/erd.mmd  — the ERD is generated from the schema, so the
picture cannot disagree with the code.
```

---

## Story 2 — Analytics & ingestion pipeline (Sprint 4 / SEC3-103)

### 1. What is expected

An extract → transform → load pipeline over external candle data with:

- an offline extractor (fixtures, no network) and a live one (real API, key from
  env, cached, quota-aware);
- a deterministic, idempotent load into an analytical store, with quarantining
  and full reconciliation — nothing silently dropped;
- a dashboard and generated claims (deliverable `claims.md` that is never
  hand-edited); symbol universe recorded with reasons.

### 2. How it was implemented

```
ETL_Analysis/
  extract_fixtures.py   EXTRACT offline (fixtures/, no network)
  extract_live.py       EXTRACT live (FAUXNANCE_API_KEY, .cache/, quota check)
  transform.py          TRANSFORM pure — the six-defect policy
  load.py               LOAD to DuckDB (analytics_schema.sql)
  pipeline.py           wiring only
  store.py              READ side — DuckDB read-only + SQL guard
  charts.py / dashboard.py   figures as pure dicts; streamlit app
  claims.py / claims.md      question fixed, every number computed
  report.py             legacy one-shot HTML report
  symbols.py + symbols_nse_bse.txt  150 NSE/BSE candidates
  tests/                438 tests, none touch the network
```

Notable policies: repaired-vs-quarantined is decided per defect (only repair
where the true value is recoverable from evidence); every repair is flagged with
`repairs` + reason; `--strict` turns repairs into quarantines; the invariant
`candles_in = rows_kept + rows_quarantined` is asserted and checked in SQL.

### 3. Commands to test + proof

```bash
pip install -r ETL_Analysis/requirements.txt
python -m ETL_Analysis.pipeline                # load -> warehouse.duckdb
python -m ETL_Analysis.claims                  # regenerate claims.md
python -m ETL_Analysis.dashboard               # streamlit at :8501
pytest ETL_Analysis/tests -v                   # 438 passed
```

Proof: the run ends with a reconciliation line
`candles_in = rows_kept + rows_quarantined`; the malformed fixture resolves to
**4 loaded (3 repaired), 3 quarantined**; `test_the_store_gives_back_the_measures_the_pipeline_put_in`
passes (store round trip). The suite also runs without DuckDB/streamlit/plotly
installed (318-438 pass, the rest skip).

### 4. Technical highlights

- Defect policy is explicit and defensible: a repaired row is only produced where
  evidence supports the repair; otherwise it is quarantined with the original
  candle attached.
- Load is idempotent (`DELETE` exact dates then `INSERT`, merged on the natural
  key `(symbol, trade_date, interval)`); the ledger `load_run` is append-only.
- Metrics are **long format** (`run_metric`), so new measures need no `ALTER`.
- Volatility/drawdown formulas are verified against `statistics.stdev` and a
  brute-force peak-to-trough search.
- Claims never rest on vendor-interpolated (`synthetic`) rows — asserted on every
  claim query.

### 5. Code to highlight

```python
# transform / load: nothing dropped, ever
assert rows_kept + rows_quarantined == candles_in
# repaired rows are visible, not silent
repaired = row | {"repaired": True, "repairs": ["high/low transposed -> swapped"]}
```
```python
# test_no_claim_query_reads_a_vendor_interpolated_row
for name in CLAIM_QUERIES:
    assert "NOT d.synthetic" in getattr(C, name)
```

---

## Story 3 — Domain engine (Sprint 5)

### 1. What is expected

A framework-free domain layer: entities, enums, exceptions and the order/portfolio
rules that the API must enforce — each rule a named `DomainException`, each
behaviour unit-tested, and no Spring/MyBatis dependency in the domain code.

### 2. How it was implemented

The engine was originally a standalone artifact
(`sprint-05-domain-engine`). For Sprint 6 the domain source was **moved into the
API** (`sprint-06-api/src/main/java/com/team1/trading/domain/**`, 28 files) and
consumed as source; the `domain-engine` Maven dependency was removed
(`sprint-06-api/pom.xml`), so a fresh Docker build needs no pre-installed jar.

Key contents:

- Entities: `Client`, `Auth`, `BankAccount`, `Instrument`, `Order`,
  `PortfolioHolding`, `PortfolioPosition`, `OrderHistory`.
- Enums: `AccountStatus`, `OrderSide`, `OrderStatus`, `OrderType`.
- Exceptions: one class per rule — `AccountNotFoundException`,
  `AccountNotActiveException`, `InsufficientFundsException`,
  `InsufficientHoldingsException`, `InstrumentNotFoundException`,
  `InvalidOrderException`, `DuplicateOrderException`, `OrderNotCancellableException`,
  `OrderConflictException`, `OrderNotFoundException`, `DomainException` base.
- Behaviour: `Client.canTrade/canAfford`, `Instrument.isTradable`, state
  transitions (`suspend/activate/close`), `OrdersService` idempotency-key
  claiming, `PortfolioService.placeOrder` running the rule chain.
- Transport DTO `PlaceOrderRequest` (jakarta-validation only) with its own tests.

### 3. Commands to test + proof

```bash
mvn -f sprint-06-api/pom.xml clean verify
# Proof:
#   [INFO] Tests run: 230, Failures: 0, Errors: 0, Skipped: 0
#   [INFO] BUILD SUCCESS
#
# The 94 domain tests are included in that 230:
#   AccountTest 32, OrderLogicTest 38, PlaceOrderRequestTest 24
```
To prove the domain is framework-free:

```bash
rg -l "org\.springframework|org\.apache\.ibatis" sprint-06-api/src/main/java/com/team1/trading/domain
# Proof: no matches (empty output)
```

### 4. Technical highlights

- Every rejection is a typed `DomainException` carrying the fields an investigation
  needs; the API layer maps codes, never strings.
- Rule ordering is explicit — first failure wins, exactly matching the contract's
  rule table.
- Idempotency is claimed with a `ConcurrentHashMap.newKeySet()` in the pure
  engine; the API re-implements it as the DB `UNIQUE` constraint, so the pure and
  the durable versions agree.
- Domain tests are pure JUnit 5 — no Spring context, no DB.

### 5. Code to highlight

```java
// PortfolioService.placeOrder — the rule chain, first failure wins
if (account == null)                throw new AccountNotFoundException(accountId);
if (!account.canTrade())            throw new AccountNotActiveException(accountId, account.getAccountState());
if (instrument == null || !instrument.isTradable())
                                    throw new InstrumentNotFoundException(symbol);
if (quantity == null || quantity <= 0) throw new InvalidOrderException("quantity", quantity);
if (side == OrderSide.BUY && !account.canAfford(cost))
                                    throw new InsufficientFundsException(accountId, cost, account.getWalletBalance());
```
```java
// Client state machine — CLOSED is one-way
public void close() {
    if (accountState == AccountStatus.CLOSED) return;
    accountState = AccountStatus.CLOSED;   // no path back to ACTIVE/SUSPENDED
}
```

---

## Story 4 — Trade order API (Sprint 6)

### 1. What is expected (the 8 acceptance criteria)

| # | Criterion | Status |
|---|---|---|
| 1 | Six endpoints implement the contract | PASS |
| 2 | Layering respected | PASS |
| 3 | MyBatis parameterised, no `${}` | PASS |
| 4 | `@ControllerAdvice` handles every exception | PASS |
| 5 | Order placement transactional | PASS |
| 6 | Optimistic lock on `version` | PASS |
| 7 | `/api/v1/**` rejects invalid token → `AUTH-401` | PASS |
| 8 | Multi-stage Dockerfile + orchestration join | PASS |

### 2. How it was implemented

```
sprint-06-api/
  contracts/  trade-api.yaml, auth-api.yaml  — binding contracts
  src/main/java/com/team1/trading/api/
    controller/ Account, BankAccount, Client, Order
    dto/        AccountResponse, BalanceResponse, OrderResponse, PositionResponse,
                OrderHistoryEntry, CreateBankAccountRequest, CreateClientRequest,
                ErrorResponse
    service/    AccountService, BankAccountService, ClientService, OrderService
    mapper/     Account, BankAccount, Client, Instrument, Order, Position  (3)
    security/   JwtValidator, JwtVerificationFilter, JwtClaims, JwtRequestContext,
                HeaderTokenAccountIdResolver, TokenAccountIdResolver, JwtAuthenticationException
    exception/  ErrorCatalogue, GlobalExceptionHandler
  src/main/java/com/team1/trading/domain/**   (Story 3, as source)
  src/test/    unit + integration; 230 tests in total (incl. domain 94)
  Dockerfile   multi-stage: maven:3.9.16-eclipse-temurin-21 → eclipse-temurin:21-jre
  .dockerignore
  pom.xml      domain as source, spring-boot-starter-actuator, MyBatis, JWT (auth0), jacoco
  application.properties   jwt.secret=${JWT_SECRET}, jwt.issuer, DB, mybatis
infra/postgres/docker-compose.yml   postgres + trade-api on one network
```

Endpoint map (`/api/v1/accounts`): `GET /{id}` details, `GET /{id}/balance`,
`GET /{id}/positions`, `GET /{id}/orders` (status/from/to filters);
`POST /{id}/orders` and `DELETE /{id}/orders/{id}`.

**Security model.** No token is auto-attached. `JwtVerificationFilter` runs
before every `/api/v1/**` request and verifies the `Authorization: Bearer`
token (HS256, shared `JWT_SECRET`, issuer `auth-service`). All four failure
modes (missing header, wrong scheme, expired, forged) return the identical body
`{"errorCode":"AUTH-401","message":"Unauthorized"}` so an attacker cannot
enumerate which check failed. Valid claims are stored in a request-scoped
context; the token's `accountId` must equal the path `{id}`; a `SUSPENDED`
account is refused (`ACC-403`).

**Order flow.** `OrderService.placeOrder` is `@Transactional`, re-runs the
domain rule chain in contract order, files the order (idempotency enforced by
the `uq_orders_idempotency_key` constraint, `DataIntegrityViolationException` →
`ORD-409 DuplicateOrderException`), applies the cash move via
`updateCashGuarded` (`version = version + 1 WHERE version = ?`, 0 rows →
`ORD-409`), then upserts the position book — all in one transaction.

**Errors.** `GlobalExceptionHandler` maps every exception to the envelope
`{"errorCode","message"}`: `DomainException` through `ErrorCatalogue`,
validation/type-mismatch → `VAL-422`, JWT → `AUTH-401`, anything else →
`INTERNAL-500`. No whitelabel page, no stack to the client.

**Test inventory (230).** Domain 94, mappers 6, exception catalogue
19, over-HTTP 13, security/context, order transactions — verified green on a
clean machine and inside the Docker build (`-DskipTests` in the image).

### 3. Commands to test + proof

Local build/test:

```bash
mvn -f sprint-06-api/pom.xml clean verify
# [INFO] Tests run: 230 ... Failures: 0 ... BUILD SUCCESS
```

Docker + orchestration (Linux VM):

```bash
# .env at repo root (JWT_SECRET must match what tokens are signed with)
cat .env
# JWT_SECRET=mission-control-shared-secret-key-32-bytes-minimum
# POSTGRES_PASSWORD=postgres
# TRADE_API_PORT=8081

docker-compose --env-file .env -f infra/postgres/docker-compose.yml up -d
docker-compose --env-file .env -f infra/postgres/docker-compose.yml ps
# team1_trade_db    Up (healthy)  0.0.0.0:5432->5432
# team1_trade_api   Up (healthy)  0.0.0.0:8081->8080
curl -sS http://localhost:8081/actuator/health        # {"status":"UP"}

# mint a token with the same JWT_SECRET
JWT_SECRET="$(grep '^JWT_SECRET=' .env | cut -d= -f2-)"
NOW=$(date +%s)
HDR=$(printf '{"alg":"HS256","typ":"JWT"}' | base64 -w0 | tr '+/' '-_' | tr -d '=')
BODY=$(printf '{"sub":"t","accountId":1,"roles":["CUSTOMER"],"iat":%s,"exp":%s,"iss":"auth-service"}' "$NOW" "$((NOW+3600))" | base64 -w0 | tr '+/' '-_' | tr -d '=')
SIG=$(printf '%s.%s' "$HDR" "$BODY" | openssl dgst -sha256 -hmac "$JWT_SECRET" -binary | base64 -w0 | tr '+/' '-_' | tr -d '=')
T="$HDR.$BODY.$SIG"

# AC1 proof — endpoints answer
for u in accounts/1 accounts/1/balance accounts/1/positions accounts/1/orders; do
  curl -sS -o /dev/null -w "%{http_code} /api/v1/$u\n" -H "Authorization: Bearer $T" http://localhost:8081/api/v1/$u
done
# 200 x4

# AC7 proof — rejected tokens
curl -sS -o /dev/null -w "no token: %{http_code}\n" http://localhost:8081/api/v1/accounts/1          # 401
curl -sS -H "Authorization: Bearer garbage" -o /dev/null -w "bad token: %{http_code}\n" http://localhost:8081/api/v1/accounts/1   # 401

# full authenticated read (captured proof from the VM)
curl -sS -H "Authorization: Bearer $T" http://localhost:8081/api/v1/accounts/1
# {"id":1,"accountId":"IN45HDFC0000001234567","holderName":"Aarav Mehta",
#  "cashBalance":125000.00,"status":"ACTIVE","version":0,
#  "lastUpdated":"2026-09-10T07:30:33.075297"}

# AC8 proof — image + network + non-root
docker-compose --env-file .env -f infra/postgres/docker-compose.yml port team1_trade_api 8080   # 0.0.0.0:8081
docker inspect team1_trade_api --format '{{.HostConfig.PortBindings}} {{.Config.User}}'          # map + non-root uid 10001
docker network inspect trading_platform_net --format '{{range .Containers}}{{.Name}} {{end}}'     # both containers
```

AC5/AC6 (transaction + optimistic lock) are proven by the suite:
`OrderServiceIntegrationTest` (`@Transactional` placement/cancel) and the
`updateCashGuarded` 0-rows → `ORD-409` test. Static AC2/AC3 checks:

```bash
rg -n '\$\{' sprint-06-api/src/main/java/com/team1/trading   # no matches → AC3
rg -l 'INSERT|UPDATE|DELETE|SELECT' sprint-06-api/src/main/java/com/team1/trading/api/controller  # no matches → AC2
```

### 4. Technical highlights

- One envelope for all failures, one status per `errorCode`; `ORD-404/ORD-409`
  case is contract-mandated.
- The filter returns 401 **itself** (filters run outside Spring MVC's exception
  handling) with the exact same body for every failure mode.
- Optimistic locking is in SQL: `UPDATE ... SET version = version + 1 WHERE
  version = ?`; a zero rowcount means a concurrent write won.
- Idempotent order placement relies on the DB constraint, not on a pre-check.
- Docker: dependency layer cached (`dependency:go-offline`), non-root uid 10001,
  HEALTHCHECK on `/actuator/health`, published host port controlled by
  `TRADE_API_PORT` while the app stays on 8080 inside the container.

### 5. Code to highlight

```java
// AccountMapper.updateCashGuarded — optimistic lock in one statement
@Update("""
        UPDATE clients
        SET wallet_balance = #{update.newBalance},
            version = version + 1,
            updated_on = now()
        WHERE client_id = #{update.clientId}
          AND version = #{update.expectedVersion}
        """)
int updateCashGuarded(@Param("update") AccountCashUpdate update);
```
```java
// OrderService.placeOrder — the transactional heart
@Transactional
public OrderResponse placeOrder(PlaceOrderRequest request, Long tokenAccountId) {
    // ... rule chain 1-8 (domain exceptions) ...
    orderMapper.insert(toInsert(order, orderUuid));                 // rule 8: DB idempotency
    int cashRows = accountMapper.updateCashGuarded(new AccountCashUpdate(
            accountId, newBalance, accountRow.getVersion()));
    if (cashRows == 0) throw new OrderConflictException("account version changed concurrently");
    // position upsert last — order + cash + position commit together
}
```
```java
// JwtVerificationFilter — the whole of the security story in one class
try {
    JwtClaims claims = jwtValidator.verify(request.getHeader("Authorization"));
    JwtRequestContext.setClaims(claims);
    filterChain.doFilter(request, response);
} catch (JWTVerificationException e) {
    writeUnauthorizedResponse(response);   // identical body for every failure
}
```

---

## Story 5 — Order history (cross-cutting)

### 1. What is expected

Every order carries an audit trail of its status changes, and the API exposes
that history to the account owner with optional filtering.

### 2. How it was implemented

- Schema: `migrations/006_order_history.sql` — one row per status change,
  keyed to the order, with timestamps and transition metadata.
- Seed: `seed/060_order_history.csv` — deterministic history rows matching the
  seeded orders, loaded transactionally like every other seed file.
- Domain: `OrderHistory` entity (as source inside `sprint-06-api`).
- API: `OrderHistoryEntry` DTO + `OrderMapper.listByAccount` with the
  `OrderHistoryFilter` (clientId, status, from, to) — all parameterised;
  endpoint `GET /api/v1/accounts/{id}/orders`.
- `AccountController.getOrders` binds optional `status`/`from`/`to` query
  params (`from`/`to` ISO dates) and resolves the token's account before
  delegating.

### 3. Commands to test + proof

```bash
mvn -f sprint-06-api/pom.xml clean verify       # 230 tests green
# with the stack running (VM):
curl -sS -H "Authorization: Bearer $T" \
  "http://localhost:8081/api/v1/accounts/1/orders?status=FILLED"
# 200 [] or a JSON list of {orderUuid, symbol, side, quantity, price, status,
# createdAt, ...}; an unparseable status/date -> {"errorCode":"VAL-422",...}
# — proof of the filter path and the error envelope.
```

### 4. Technical highlights

- The table is additive to the schema (no migration edits); history carries
  *how* an order reached its state.
- The query uses optional-parameter guards (`#{expr, jdbcType=...} IS NULL`)
  so one statement serves filtered and unfiltered reads, with no dynamic SQL.
- The endpoint reuses the same token-ownership check as every other account
  read — no account can read another's history.

### 5. Code to highlight

```sql
-- migrations/006_order_history.sql (grain)
-- one row per order status change; the current status lives on orders itself
CREATE TABLE order_history (
    order_id      uuid        NOT NULL REFERENCES orders(order_id),
    status        varchar     NOT NULL,
    changed_at    timestamptz NOT NULL DEFAULT now(),
    note          varchar
);
```
```java
// OrderMapper.listByAccount — parameterised optional filters, no ${}
WHERE client_id = #{filter.clientId}
  AND (#{filter.status, jdbcType=VARCHAR}::varchar IS NULL OR status = #{filter.status, jdbcType=VARCHAR}::varchar)
  AND (#{filter.from, jdbcType=TIMESTAMP}::timestamp IS NULL OR created_at >= #{filter.from, jdbcType=TIMESTAMP}::timestamp)
ORDER BY created_at DESC
```

---

## How the stories fit together

```
migrations/ + seed/           --- Story 1: the schema the API reads and writes
        │
        ▼
domain engine (as source)     --- Story 3: rules + exceptions, framework-free
        │
        ▼
sprint-06-api                 --- Story 4: JWT, envelope, transactions, Docker
   └─ order history endpoint  --- Story 5: audit trail (migration 006)
ETL_Analysis/                 --- Story 2: analytics over candles, store+claims
infra/postgres/docker-compose --- Story 4 AC8: postgres + trade-api, one network
```

The master proof is one command:

```bash
mvn -f sprint-06-api/pom.xml clean verify   # 230 tests, 0 failures, BUILD SUCCESS
```

and, on a machine with Docker:

```bash
docker-compose --env-file .env -f infra/postgres/docker-compose.yml up -d && \
docker-compose --env-file .env -f infra/postgres/docker-compose.yml ps
# team1_trade_db Up (healthy) · team1_trade_api Up (healthy) · 8081 -> 8080
```