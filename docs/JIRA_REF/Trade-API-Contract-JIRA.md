# JIRA 2 — Implement the Provided Trade API Contract

## 1. Goal

Make the Spring Boot service (`sprint-06-api`) honour the **binding** `contracts/trade-api.yaml` exactly: six REST endpoints for order placement/cancellation and account reads, full business-rule enforcement, and a single error envelope over a shared error catalogue. The Angular UI generates its typed client from the same YAML, so "implemented exactly" is the acceptance bar — a renamed field is a compile error there.

## 2. What the contract mandates

### Endpoints

| Endpoint | Request | 200 response |
|---|---|---|
| `POST /api/v1/orders` | `PlaceOrderRequest` | `OrderResponse` (`FILLED`/`REJECTED` this sprint; `NEW` from Sprint 7) |
| `DELETE /api/v1/orders/{id}` | uuid path (no `ORD-` prefix) | `OrderResponse` `CANCELLED` |
| `GET /api/v1/accounts/{id}` | — | `AccountResponse` |
| `GET /api/v1/accounts/{id}/balance` | — | `BalanceResponse` |
| `GET /api/v1/accounts/{id}/positions` | — | `PositionResponse[]` |
| `GET /api/v1/accounts/{id}/orders?status&from&to` | optional filters | `OrderHistoryEntry[]` (audit trail, newest first) |

### Business rules — evaluated in this exact order, first failure wins

| # | Rule | Code / HTTP |
|---|---|---|
| 1 | Account exists | `ACC-404` / 404 |
| 2 | Account `ACTIVE` | `ACC-403` / 403 |
| 3 | Instrument exists and tradable | `INS-404` / 404 |
| 4 | `quantity > 0` | `VAL-422` / 422 |
| 5 | `price > 0` (2 dp, no `double` money) | `VAL-422` / 422 |
| 6 | BUY: cash ≥ qty×price | `ORD-400` / 400 |
| 7 | SELL: held ≥ order qty | `ORD-409` / 409 |
| 8 | Idempotency key unique | `ORD-409` / 409 |
| 9–10 | Cash + position update atomically; every order recorded (audit trail) | — |

Rule 8 must be enforced by the **unique constraint, not read-then-write** (that races). Cancellation is a **guarded state transition** inside the transaction (`status='NEW'` guard), so it can never race the Executor.

### Error envelope + identifiers

- Everything (success or failure) uses the catalogue from JIRA 7: `{"errorCode", "message"}`; clients branch on `errorCode`, never on status alone — **404 and 409 each carry two codes** (`ACC-404`/`INS-404`, `ORD-409` for holdings/duplicate/not-cancellable/not-found).
- `orderId` is displayed as `ORD-<uuid>`; the DELETE path takes the bare uuid.
- `accountId` (path, body, claim) = the numeric key everywhere, **except** `AccountResponse.accountId` which is the business string `ACC-…` — the one deliberate name collision the contract calls out.
- Error messages must never leak stack traces/SQL/class names (OWASP A05).

## 3. Deliverables — files created

**Controllers** (`sprint-06-api/src/main/java/com/team1/trading/api/controller/`)

- `OrderController.java` — `POST /orders`, `DELETE /orders/{id}`; `@Valid` body, `id.trim()`, resolves account from the header per request.
- `AccountController.java` — the four account GETs, `@DateTimeFormat` on `from`/`to`; bad enum/date → `VAL-422`.

**Services** (`.../api/service/`)

- `OrderService.java` — full rule-1–8 gate, synchronous Sprint-6 fill (BUY: cash down, position upsert w/ weighted average; SELL: **LIFO-walk of buy records** → `executedPrice`, position reduce), optimistic-lock retry on the cash row, singleton idempotency, one-NEW-order-per-account, and the batch txn shape for Sprint-7's migration.
- `AccountService.java` — every read funnels through one `resolve(accountId, tokenAccountId)` gate (missing → `ACC-404`; token/account mismatch → `ACC-403`; inactive via domain `Client.canTrade()` → `ACC-403`), plus `parseStatus` for `VAL-422`.

**DTOs** (`.../api/dto/`)

`PlaceOrderRequest` lives in the domain (`sprint-05-domain-engine/src/main/java/com/team1/trading/domain/dto/PlaceOrderRequest.java`: `@NotNull`/`@Min`/`@DecimalMin`/`@Digits`/`@Size` ~ the contract's `additionalProperties: false`).

- `AccountResponse` (`id`, `accountId`, `holderName`, `cashBalance`, `status`, `version`, `lastUpdated`)
- `BalanceResponse` (`accountId`, `cashBalance`, `currency`, `asOf`)
- `PositionResponse` (`accountId`, `symbol`, `quantity`, `averageCost`)
- `OrderHistoryEntry` (`orderId`, `accountId`, `symbol`, `side`, `quantity`, `price`, `executedPrice`, `status`, `idempotencyKey`, `createdOn`)
- `OrderResponse` (`orderId`, `status`, `message`, `symbol`, `side`, `quantity`, `price`)

Field names mirror the YAML exactly.

**Mappers** (`.../api/mapper/`, parameterised MyBatis ⇒ OWASP-A03-safe)

- `AccountMapper` — `findRow`, guarded optimistic `updateCashGuarded … WHERE version = :expectedVersion`.
- `OrderMapper` — insert, `findByUuid`, `markCancelled … WHERE status='NEW'` (the guarded transition), and NULL-safe filtered `listByAccount`.
- `PositionMapper` — buy upserts + sell reduces on **both** `portfolio_positions` and `portfolio_holding`, sell guarded by `quantity >= :qty` (no shorts).

**Auth wiring**

`TokenAccountIdResolver` interface + `HeaderTokenAccountIdResolver` (reads the `accountId` JWT claim; missing header → `null`, i.e. "shared-account read" tolerated until JIRA 8 enforces `AUTH-401`).

## 4. How it works with the rest of the codebase

```
HTTP ─▶ Controller ─▶ Service ─▶ Mapper ─▶ Postgres
            │            │
            │            ├── domain-engine JAR (sprint-05):
            │            │     Client.canTrade(), Instrument/Market/TargetPrice,
            │            │     repo stubs, domain exceptions, PlaceOrderRequest, enums
            │            ▼
            └──── TokenAccountIdResolver ──► GlobalExceptionHandler (JIRA 7)
                                            ErrorCatalogue / ErrorResponse envelope
```

- **Order flow:** `OrderController` → `OrderService.placeOrder` → rule gate (domain objects decide product truth, the API never re-implements it) → guarded updates → `OrderResponse` with `ORD-` display id. The staged/in-memory repositories stand in for the DB-backed implementation from the JIRA-4/5 mapper sprint, and the transaction/unique-constraint notes in YAML map onto `version`-guarded SQL the mappers already expose.
- **Failure flow:** any domain exception thrown here is turned into the JSON envelope by **JIRA 7's** `GlobalExceptionHandler` — this JIRA both consumes and (through its tests) exercises that catalogue end-to-end.
- **Auth boundary:** this JIRA provisions the resolver; **JIRA 8** validates the JWT itself (its filter enforces `/api/v1/**`).
- **The Angular client:** any shape drift from the YAML (hence the DTOs' exact field names) would be a compile error on the front end.

## 5. Design decisions worth a slide

1. **Sprint-6 synchronous fill** (`FILLED`/`REJECTED` in the response) with a structure that slides into Sprint-7's async `NEW` + Kafka post easily.
2. **Money is `BigDecimal`** end to end; `@Digits(integer=12, fraction=2)` on input.
3. **Idempotency by unique key**, not read-then-write; duplicate `idempotencyKey` rejected before any balance/position touch.
4. **Order-of-rules correctness is a guarantee**, tested per-rule (first failure wins, no later rule evaluated).
5. **LIFO buy-record walk** produces a real `executedPrice` for sells and keeps `averageCost` unchanged on sell (YAML: "what makes realised P&L computable later").
6. **Single envelope even for 500s** so no whitelabel page can ever reach the UI.

## 6. Test evidence (all green)

| Test class | # | Proves |
|---|---|---|
| `OrderServiceTest` | 19 | rules 1–8 in order, optimistic-lock retry, LIFO pricing, buy-then-sell, cancel paths incl. 404/not-cancellable/reject-after-partial |
| `TradeApiControllerWebTest` | 16 | MockMvc slice — status/body per catalogued code, `ORD-` format, route map, history filters, token-based permission |
| `AccountServiceTest` | 8 | reads + `ACC-404`/`ACC-403` gate, bad-`status` → `VAL-422` |
| `HeaderTokenAccountIdResolverTest` | 7 | scheme/casing/decode edges, missing header → null |
| (J7 shared) `GlobalExceptionHandlerTest` + `GlobalExceptionHandlerWebTest` | 32 | the envelope + every code, incl. the 404+`ORD-409` / 409+`ORD-409` quirks |

**Coverage (JaCoCo, scoped report):** `OrderController` 100%, `AccountController` 100%, `OrderService` 100% instr / 86% branches, `AccountService` 99%, `HeaderTokenAccountIdResolver` 100%. The only misses are structural — unused JSON **setters** (nothing deserialises a response) and defensive fallback branches. Report: `target/site/jacoco/index.html`, generated via `mvn clean verify "-Dtest=!AccountMapperTest,!OrderMapperTest,!AccountReadIntegrationTest"` (those three are Postgres-backed teammate tests).

## 7. Open boundaries

- `AUTH-401` enforcement = JIRA 8 (this JIRA only wires the resolver).
- REJECTED orders are not yet persisted as rows — the "every order recorded" rule is covered in-memory today; the mapper INSERT is written and lands with the DB sprint.
- The 3 DB-backed test classes (`AccountMapperTest`, `OrderMapperTest`, `AccountReadIntegrationTest`) and a live smoke test need Postgres on `localhost:5432` (seed: account 1 "Aarav Mehta", `ACC-000001`, balance 125000.00) — offer `docker compose -f infra/postgres/docker-compose.yml up` once Docker is available.