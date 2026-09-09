# JIRA: Global Exception Handler — Presentation Overview

## 1. What the JIRA is

Build the single, contract-mandated error mechanism for the platform: every failure any endpoint raises must leave the exact envelope defined in `contracts/trade-api.yaml`:

```json
{ "errorCode": "ORD-409", "message": "Duplicate order" }
```

Nothing else — no Spring whitelabel page, no stack trace, no SQL fragment, no class name, no internal identifier.

## 2. Acceptance criteria (as fixed by the binding contract)

| # | Criterion |
|---|---|
| 1 | One global handler (`@RestControllerAdvice`) intercepts every failure for the whole service |
| 2 | Every response body is exactly the 2-field envelope `errorCode` + `message` |
| 3 | Codes and HTTP statuses match the contract catalogue exactly (table below) |
| 4 | Clients branch on `errorCode`, never on status alone — because 404 and 409 each carry more than one code |
| 5 | Envelope never leaks internal detail (OWASP A05): no account keys, amounts, idempotency keys, SQL, class names in the message |
| 6 | Bean-validation failures (`@Valid`) and query/path type-mismatches map to `VAL-422` |
| 7 | Unexpected failures still return an envelope (never a whitelabel page) |
| 8 | The contract's DELETE quirk is honoured: order not found → HTTP 404 with `ORD-409` "Order not found" |

## 3. The error catalogue (code → HTTP)

| Code | HTTP | Meaning |
|---|---|---|
| `ACC-404` | 404 | Account not found |
| `ACC-403` | 403 | Account not active / not reachable with this token |
| `INS-404` | 404 | Instrument not found / not tradable |
| `ORD-400` | 400 | Insufficient funds |
| `ORD-409` | 409 | Insufficient holdings / duplicate order / order not cancellable |
| `VAL-422` | 422 | Invalid input |
| `AUTH-401` | 401 | Unauthorised / invalid token |
| `INTERNAL-500` | 500 | (Undocumented catch-all added so even unexpected failures keep the envelope — no whitelabel) |

## 4. Deliverables / files created

### API layer — `sprint-06-api`

| File | Role |
|---|---|
| `api/exception/GlobalExceptionHandler.java` | The `@RestControllerAdvice`; one `@ExceptionHandler` per failure family |
| `api/exception/ErrorCatalogue.java` | Single source of truth: code → `HttpStatus` map + the 8 code constants |
| `api/dto/ErrorResponse.java` | The envelope DTO — deliberately only two fields |

### Domain layer — `sprint-05-domain-engine` (shared jar, re-installed to local Maven repo)

| File | Role |
|---|---|
| `domain/exception/DomainException.java` | Abstract base: carries the `errorCode` string |
| 11 concrete exceptions | `AccountNotFoundException` (`ACC-404`), `AccountNotActiveException` (`ACC-403`), `InstrumentNotFoundException` (`INS-404`), `InsufficientFundsException` (`ORD-400`), `InsufficientHoldingsException`, `DuplicateOrderException`, `OrderNotFoundException`, `OrderNotCancellableException`, `OrderConflictException` (`ORD-409`), `InvalidOrderException` (`VAL-422`), `AuthenticationException` (`AUTH-401`) |

Each concrete exception hard-codes its own `CODE` and `MESSAGE` constants (e.g. `OrderNotFoundException.CODE = "ORD-409"`, `MESSAGE = "Order not found"`), so domain and API can never drift.

## 5. How it works (flow)

1. A controller/service throws a `DomainException` (or Spring raises `MethodArgumentNotValidException` / `MethodArgumentTypeMismatchException`).
2. Spring routes it to `GlobalExceptionHandler` — one of four handlers:
   - `handleDomainException` — status from `ErrorCatalogue.statusFor(code)`, except `OrderNotFoundException` forced to HTTP 404 (the contract's special case, `GlobalExceptionHandler.java:55`).
   - `handleValidation` → `VAL-422`; `handleTypeMismatch` → `VAL-422`.
   - `handleUnexpected` → `INTERNAL-500` fallback so no whitelabel page ever reaches a client.
3. Envelope is built: `envelope(code, message, status)` → `ResponseEntity<ErrorResponse>()`.
4. In parallel, `detailFor(e)` extracts the investigation detail (accountId, symbol, amounts, idempotencyKey) to the **server log only** — that is where the internal state lives, never in the body (`GlobalExceptionHandler.java:103`).

## 6. How it cooperates with the rest of the system

- **Domain exceptions (JIRA 5 jar)** → thrown by `OrderService` (rules 1–8) and `AccountService`; handled here. No guessing: the code and message come from the exception instance.
- **Business-rule ordering** — `OrderService.placeOrder` throws on first failing rule; the handler turns each into the documented code/status (`ACC-404` → `ACC-403` → `INS-404` → `VAL-422` → `ORD-400` → `ORD-409`).
- **JWT / JIRA 8** — `AuthenticationException` and the `AUTH-401` envelope branch are ready in the catalogue and handler; actual token verification/401 enforcement is the JIRA 8 security-filter work (this JIRA provides the mechanism, JIRA 8 provides the trigger).
- **Controllers** — no controller contains try/catch or manually builds errors; they rely entirely on this handler, which keeps the contract shape uniform across all six endpoints.
- **Tests** — the handler is verified at unit and HTTP-slice level (below).

## 7. Test evidence

### `GlobalExceptionHandlerTest` (pure unit, direct handler calls — 19 tests)

- **Catalogue (7):** every documented code maps to its exact status; unknown code → 500, never a lying status.
- **Execution paths (8):** each domain exception → correct code + status + message; bean-validation → `VAL-422`; bad token → `AUTH-401`.
- **Branchability (4):** `ACC-404`/`INS-404` share 404 but differ; `ORD-409` carries different messages; message never leaks an internal identifier; envelope has exactly two fields (reflection check).

### `GlobalExceptionHandlerWebTest` (`@WebMvcTest` slice, no DB/container — 13 tests)

Real HTTP requests through a test-only probe controller, asserting status + `errorCode` + exact JSON body including the contract quirks: order-not-found → 404 + `ORD-409`, not-cancellable → 409, type-mismatch → 422, bad token → 401, unexpected → `INTERNAL-500`.

**Total: 32 tests for this JIRA**, part of the 83-test green `mvn clean verify` for `sprint-06-api`.

## 8. Points to call out in the presentation

- The **404-with-`ORD-409`** case is the demonstration that "branch on the code, not the status" is real, not decoration.
- `INTERNAL-500` is intentionally outside the documented catalogue — a deliberate safety net so the Angular client always gets a parseable envelope.
- **Two aligned sources of truth:** domain exceptions own code+message; `ErrorCatalogue` owns code→status — the tests pin both so they can't drift.
- **One deliberate scope boundary:** the handler can emit `AUTH-401`, but enforcement of real JWTs is JIRA 8's deliverable.