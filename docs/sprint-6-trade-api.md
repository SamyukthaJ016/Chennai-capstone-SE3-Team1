# Sprint 6 — Trade Order API Technical Documentation

Status: implemented and verified. `mvn clean verify` is green: **230 tests, 0 failures** (62 test suites), covering controllers (unit + WebMvc slice + `@SpringBootTest` integration), the error catalogue, mappers on H2, JWT verification/filter, services, and the domain layer. The service also ships as a multi-stage Docker image joined to the local orchestration.

Scope: Sprint 6 technical reference — architecture, acceptance-criteria evidence, setup (local and Docker), build/testing commands, runtime configuration, endpoint walk-throughs, and the Linux VM runbook for `sprint-06-api`.

---

## 1. Stack

| Concern        | Choice                                             |
|----------------|----------------------------------------------------|
| Language       | Java 21 (`pom.xml` → `java.version`)               |
| Framework      | Spring Boot 3.5.3 (web + validation + actuator)    |
| Persistence    | MyBatis (Spring Boot starter 3.0.5), annotation mappers |
| Database       | PostgreSQL 17 (runtime) / H2 in-memory (tests only) |
| Security       | JWT HS256 verification, `OncePerRequestFilter` on `/api/v1/**` |
| Build          | Maven. Wrapper pins **Apache Maven 3.9.16**        |
| Tests          | JUnit 5 + Spring `@WebMvcTest` / `@SpringBootTest`, no test containers |
| Runtime image  | `eclipse-temurin:21-jre`, non-root user            |

Maven wrapper: `.mvn/wrapper/maven-wrapper.properties` → `distributionUrl` `apache-maven/3.9.16`. Build is reproducible via `./mvnw` (bash) / `.\mvnw.cmd` (PowerShell); the Docker build uses the `maven:3.9.16-eclipse-temurin-21` image directly.

---

## 2. Repository layout

```
.
├── .env.example                 # Postgres + Sprint 6 (JWT_SECRET, TRADE_*) template
├── docs/
│   ├── erd.md / erd.mmd / erd.png
│   ├── order_lifecycle.mmd / order_lifecycle.png
│   └── sprint-6-trade-api.md    # THIS DOCUMENT
├── infra/postgres/docker-compose.yml   # Postgres + trade-api orchestration
├── migrations/                  # SQL migrations (volume-mounted into compose)
├── seed/                        # CSV seed data (020_clients.csv, 040_instruments.csv, ...)
├── sprint-05-domain-engine/     # Spring 5 module (kept; the domain is ALSO source in sprint-06-api)
└── sprint-06-api/               # self-contained: domain is source here, one `mvn package` builds it
    ├── pom.xml                  # no domain-engine dependency; web+validation+actuator+mybatis
    ├── Dockerfile               # multi-stage: maven build → temurin:21-jre runtime
    ├── .dockerignore
    ├── contracts/trade-api.yaml # Sprint 6 binding contract
    ├── contracts/auth-api.yaml  # JWT claims contract
    └── src/
        ├── main/java/com/team1/trading/
        │   ├── api/{controller,service,mapper,security,exception,dto}/
        │   └── domain/{entity,entity.types,exception,service,dto}/   # DOMAIN AS SOURCE
        ├── main/resources/{application.properties, application-test.properties}
        └── test/{java,...resources/{schema.sql, data.sql}}
```

---

## 3. Architecture & layering

Layering is enforced by package discipline; the domain code was kept framework-free in Sprint 5 and is now **source in this module** (no artifact, no `mvn install`). A Docker build starts from an empty `~/.m2`, so the domain must be source for the image to build with one `mvn package` — which is exactly how it now is.

| Layer      | Package                                | May see                                     | Must not see                       |
|------------|----------------------------------------|---------------------------------------------|------------------------------------|
| Controller | `com.team1.trading.api.controller`     | DTOs, status codes, validation annotations  | SQL, MyBatis mappers, business rules |
| Service    | `com.team1.trading.api.service`        | domain, mappers (inside one `@Transactional`) | HTTP types, request/response DTOs |
| Mapper     | `com.team1.trading.api.mapper`         | entities (MyBatis `@Mapper`)                | HTTP types, servlet, Spring MVC    |
| Domain     | `com.team1.trading.domain.*`           | plain Java                                  | servlet, Spring, MyBatis, JDBC     |

> Layering nit (known, minor): the transport DTO `PlaceOrderRequest` lives in `com.team1.trading.domain.dto`. It uses only `jakarta.validation` annotations — no servlet/Spring/MyBatis type — so the strict "no HTTP type in the domain" rule holds; it is simply unimplemented design to relocate transport DTOs beside the API layer.

---

## 4. API surface (Sprint 6 contract)

Base path: `/api/v1`. All routes are JWT-protected (`Authorization: Bearer <token>`).

| Method   | Path                       | Purpose                          | Errors                              |
|----------|----------------------------|----------------------------------|-------------------------------------|
| GET      | `/api/v1/accounts/{id}`    | Account profile + cash balance   | `ACC-404`, `ACC-403`, `AUTH-401`     |
| GET      | `/api/v1/accounts/{id}/balance` | Cash balance               | `ACC-404`, `ACC-403`, `AUTH-401`     |
| GET      | `/api/v1/accounts/{id}/positions` | Open positions          | `ACC-404`, `ACC-403`, `AUTH-401`     |
| GET      | `/api/v1/accounts/{id}/orders` | Order history            | `ACC-404`, `AUTH-401`               |
| POST     | `/api/v1/orders`            | Place order (fills synchronously) | `ACC-404`, `ORD-400`, `VAL-422`, `ORD-409`, `AUTH-401` |
| DELETE   | `/api/v1/orders/{id}`       | Cancel a `NEW` order             | `ORD-409` (incl. 404 "Order not found"), `AUTH-401` |

Out-of-contract extras (not Sprint 6 ACs, outside `/api/v1` so not JWT-gated): `/api/clients`, `/api/bank-accounts`.

### Error envelope
Every failure returns the same body: `{ "errorCode": "ACC-404", "message": "Account not found" }`.

| Code        | HTTP  | Raised by                                     |
|-------------|-------|-----------------------------------------------|
| `ACC-404`   | 404   | Unknown account                               |
| `ACC-403`   | 403   | Account not `ACTIVE`, or token `accountId` ≠ path id |
| `INS-404`   | 404   | Unknown instrument (`symbol`)                 |
| `ORD-400`   | 400   | Insufficient funds on purchase                |
| `ORD-409`   | 409   | Idempotent retry, insufficient holdings, order not cancellable, optimistic-lock lost |
| `VAL-422`   | 422   | Bean-validation or type-mismatch errors, invalid quantity/price |
| `AUTH-401`  | 401   | Any JWT verification failure (identical body) |
| `INTERNAL-500` | 500 | Defensive fallback; keeps the envelope        |

`OrderNotFoundException` is served as HTTP 404 with code `ORD-409` (contract: DELETE "Order not found"); clients branch on `errorCode`.

---

## 5. Security (JWT verification)

`JwtVerificationFilter` (`OncePerRequestFilter`, `/api/v1/**`) wraps `JwtValidator`. Order: **signature → expiry → algorithm → issuer/claims**. Every failure — missing header, wrong scheme, malformed/expired/forged token, wrong issuer — returns byte-identical `AUTH-401` bodies; reasons are logged server-side only.

Claims (`contracts/auth-api.yaml`): `sub` (UUID/human id), `accountId` (integer = `ACCOUNTS.id`), `roles` array, `iat`/`exp` (epoch seconds), `iss: "auth-service"`, HS256 signed with `JWT_SECRET`.

Authorisation gate (`AccountService.resolve`, AccountService.java:79-90): token `accountId` must equal path `{id}`, account must be `ACTIVE` → else `ACC-403`.

---

## 6. Concurrency (optimistic locking)

- Purchases: `AccountMapper.updateCashGuarded` — `UPDATE clients SET wallet_balance = wallet_balance - #{...}, version = version + 1 WHERE client_id = ? AND version = #{update.expectedVersion}`. 0 rows → `OrderConflictException` → `ORD-409`.
- Cancellation: guarded state transition (`NEW` only) via `markCancelled`.
- `placeOrder` and `cancel` are `@Transactional`.

---

## 7. Acceptance-criteria evidence (all eight PASS)

| # | Criterion                                     | Status | Evidence |
|---|-----------------------------------------------|--------|----------|
| 1 | Six endpoints implement the contract          | PASS   | `AccountController` (4 GETs), `OrderController` (POST/DELETE); envelope via `GlobalExceptionHandler` |
| 2 | Layering respected                            | PASS*  | Domain framework-free; controllers contain no SQL. *Transport-DTO nit in §3 |
| 3 | MyBatis parameterised, no `${}`               | PASS   | All 6 mappers annotation style; zero `${` in mappers and domain source |
| 4 | `@ControllerAdvice` handles every exception   | PASS   | `DomainException`, `MethodArgumentNotValidException`, `MethodArgumentTypeMismatchException`, `JwtAuthenticationException`, `Exception`; 19 catalogue/branch/path tests + 13 over-HTTP |
| 5 | Order placement transactional                 | PASS   | `@Transactional` on `placeOrder` and `cancel` |
| 6 | Optimistic lock on `version`                  | PASS   | `updateCashGuarded`; 0 rows → `ORD-409` |
| 7 | `/api/v1/**` rejects invalid token → `AUTH-401` | PASS | `JwtVerificationFilter` + `JwtValidator`; identical-body tests |
| 8 | Multi-stage Dockerfile + orchestration join   | PASS   | `sprint-06-api/Dockerfile` (build → JRE runtime, non-root, cache-ordered copies, EXPOSE, HEALTHCHECK); `infra/postgres/docker-compose.yml` adds `trade-api` (build block, shared network, published port, DB+JWT env from `.env`, `depends_on: service_healthy`, healthcheck) |

Engineering-contract checklist: Maven 3.9.16 ✓ · Java 21 ✓ · Spring Boot 3.5.3 + web + validation + MyBatis + Postgres ✓ · sources `src/main/java` / tests `src/test/java` ✓ · **`mvn clean verify` on a machine that has never seen the code ✓** (domain is source; no artifact) · **domain as source, no `mvn install` ✓** · **multi-stage Dockerfile ✓** · **service in local orchestration ✓**.

---

## 8. Setup — local (no Docker for the app)

### 8.1 Prerequisites
- JDK 21 (Adoptium) — `java -version` → 21.x
- Maven 3.9+ (or use `./mvnw` — pinned to 3.9.16)

### 8.2 Environment variables
```bash
export JWT_SECRET="a-long-random-string-shared-with-the-auth-service"
export JWT_ISSUER="auth-service"   # optional; default auth-service
export DB_PASSWORD="postgres"      # optional; default postgres
export TRADE_CURRENCY="USD"        # optional; default USD
```
`jwt.secret` has **no default** — the app will not start without `JWT_SECRET`.

### 8.3 Database (PostgreSQL 17)
The compose file starts Postgres with migrations + seeds mounted:
```bash
cd <repo-root>
cp .env.example .env        # then edit .env → set JWT_SECRET to a long random string
docker compose -f infra/postgres/docker-compose.yml up -d postgres
docker compose -f infra/postgres/docker-compose.yml ps   # postgres: healthy
```

---

## 9. Build, test, run — local

Run from `sprint-06-api/`.

```bash
./mvnw clean verify                              # full build + tests (230, H2 in-memory)
./mvnw test -Dtest=OrderServiceTest              # one class
./mvnw test -Dtest=AccountReadIntegrationTest    # one integration class
./mvnw spring-boot:run                           # run against Postgres (needs JWT_SECRET)
```
> Do **not** run two concurrent `mvn clean verify` against the same `target/` — a second build can delete `.class` files mid-first-build and produce misleading `No qualifying bean`/`@SpringBootConfiguration` failures. One build at a time.

Test profile (`application-test.properties`): H2 memory DB per context (unique URL each), `jwt.secret=test-secret-key`, `jwt.issuer=auth-service`.

### Test inventory (230)
- Controllers: `AccountReadControllerTest` (3) · `AccountReadIntegrationTest` (4) · `TradeApiControllerWebTest` `$AccountReadTests` (8) `$PlaceOrderTests` (5) `$CancelOrderTests` (3)
- Exceptions: `GlobalExceptionHandlerTest` `$CatalogueTests` (7) `$BranchabilityTests` (4) `$ExecutionPathTests` (8) · `GlobalExceptionHandlerWebTest` `$EnvelopeOverHttpTests` (13)
- Mappers: `AccountMapperTest` (3) · `OrderMapperTest` (4)
- Security: `JwtValidatorTest` (27) · `JwtVerificationFilterTest` (13) · `HeaderTokenAccountIdResolverTest` (7)
- Services: `AccountServiceTest` (8) · `OrderServiceTest` (19)
- Domain (source of truth for the rules): `AccountTest` (32) · `OrderLogicTest` (38) · `PlaceOrderRequestTest` (24)
- Context: `Sprint06ApiApplicationTests` (1)

---

## 10. Docker & orchestration

### Image
`docker build` uses the module alone as context (domain is source → one `mvn package`):
```bash
cd sprint-06-api
docker build -t team1-sprint6/trade-api:0.0.1 .
```
Stages: `maven:3.9.16-eclipse-temurin-21` (resolve deps → `mvn package -DskipTests`) → `eclipse-temurin:21-jre` (non-root `app` user, only the jar, `EXPOSE 8080`, `HEALTHCHECK` on `/actuator/health`). Copies are ordered so source edits don't invalidate the dependency layer.

### Orchestration (repo root, or `infra/postgres/`)
`infra/postgres/docker-compose.yml` now defines `postgres` + `trade-api` on a shared network. `trade-api` has: build block (context `../../sprint-06-api`), `depends_on: postgres: service_healthy`, DB/JWT env from `.env`, published port `${TRADE_API_PORT:-8080}:8080`, healthcheck on `/actuator/health`.
```bash
cd <repo-root>
docker compose -f infra/postgres/docker-compose.yml up -d --build
docker compose -f infra/postgres/docker-compose.yml ps      # BOTH healthy
docker logs -f team1_trade_api                              # app log
docker compose -f infra/postgres/docker-compose.yml down    # stop (volumes kept)
docker compose -f infra/postgres/docker-compose.yml down -v # stop + drop db volume
```
Postgres is reached by service name; `localhost` inside a container is the container.

---

## 11. Linux VM runbook

Everything from a fresh clone:

```bash
# 1. Clone
git clone <repo-url> && cd Chennai-capstone-SE3-Team1

# 2. Prereqs
java -version          # must be 21.x
docker --version       # Docker 24+ with compose plugin
docker compose version

# 3. Configure secrets (used by compose + app)
cp .env.example .env
nano .env              # set JWT_SECRET=<long random string>; check POSTGRES_* / TRADE_*
export JWT_SECRET="$(grep '^JWT_SECRET=' .env | cut -d= -f2-)"

# 4. Verify the build standalone (no Docker, no ~/.m2 shortcut needed - domain is source)
cd sprint-06-api
./mvnw clean verify            # expects 230 tests, 0 failures
cd ..

# 5. Build the image
cd sprint-06-api
docker build -t team1-sprint6/trade-api:0.0.1 .
cd ..

# 6. Run the stack
docker compose -f infra/postgres/docker-compose.yml up -d --build
docker compose -f infra/postgres/docker-compose.yml ps      # both healthy
sleep 5; docker logs team1_trade_api | tail -n 20

# 7. Exercise the API (token must be HMAC-signed with the SAME JWT_SECRET)
PAYLOAD='{"alg":"HS256","typ":"JWT"}'
NOW=$(date +%s)
BODY=$(printf '{"sub":"test-user-1","accountId":1,"roles":["CUSTOMER"],"iat":%s,"exp":%s,"iss":"auth-service"}' "$NOW" "$((NOW+3600))" | base64 -w0 | tr '+/' '-_' | tr -d '=')
HDR=$(printf '%s' "$PAYLOAD" | base64 -w0 | tr '+/' '-_' | tr -d '=')
SIG=$(printf '%s.%s' "$HDR" "$BODY" | openssl dgst -sha256 -hmac "$JWT_SECRET" -binary | base64 -w0 | tr '+/' '-_' | tr -d '=')
TOKEN="$HDR.$BODY.$SIG"

curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/accounts/1
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/accounts/1/balance
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/accounts/1/orders
QUANTITY=10; PRICE=2500.00; KEY=$(uuidgen)
curl -sS -X POST http://localhost:8080/api/v1/orders \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d "{\"accountId\":1,\"symbol\":\"RELIANCE\",\"side\":\"BUY\",\"quantity\":$QUANTITY,\"price\":$PRICE,\"idempotencyKey\":\"$KEY\"}"
# 401 without a token:
curl -sS -i http://localhost:8080/api/v1/accounts/1 | head -n 1
```

Notes:
- `accountId: 1` only authorises `/accounts/1*` (ACC-403 otherwise); account 4 is `SUSPENDED` → ACC-403.
- To re-test a clean DB after a compose `down -v`, Postgres re-runs migrations/seeds on `up`.
- Bruno (API client): URL `http://localhost:8080/api/v1/accounts/1`, header `Authorization: Bearer $TOKEN` from step 7, or use a pre-request script with `require("jsonwebtoken")` + the same `JWT_SECRET`.

---

## 12. Open items

1. `PlaceOrderRequest` (transport DTO) still lives in the domain package — relocate next to the API layer if the reviewer objects (no functional impact).
2. No Kafka (correct — nothing this sprint needs it).
3. Watch out that the domain engine remains a plain-Java package when new code is added; the Sprint 5 enforcer no longer guards it inside this module.