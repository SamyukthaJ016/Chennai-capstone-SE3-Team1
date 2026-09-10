# JIRA: Global Exception Handler — Presentation Overview

## 1. What the JIRA is

Build the single, contract-mandated error mechanism for the platform: every failure any endpoint raises must leave the exact envelope defined in `contracts/trade-api.yaml`:

```json
{
  "errorCode": "ORD-409",
  "message": "Duplicate order"
}
```

Nothing else — no Spring whitelabel page, no stack trace, no SQL fragment, no class name, no internal identifier.

## 2. Acceptance Criteria

As fixed by the binding contract:

| # | Criterion |
|---|---|
| 1 | One global handler (`@RestControllerAdvice`) intercepts every failure for the whole service |
| 2 | Every response body is exactly the 2-field envelope `errorCode` + `message` |
| 3 | Codes and HTTP statuses match the contract catalogue exactly |
| 4 | Clients branch on `errorCode`, never on status alone — because 404 and 409 each carry more than one code |
| 5 | Envelope never leaks internal detail (OWASP A05): no account keys, amounts, idempotency keys, SQL, class names in the message |
| 6 | Bean-validation failures (`@Valid`) and query/path type-mismatches map to `VAL-422` |
| 7 | Unexpected failures still return an envelope (never a whitelabel page) |
| 8 | The contract's DELETE quirk is honoured: order not found → HTTP 404 with `ORD-409` `"Order not found"` |

## 3. The Error Catalogue

| Code | HTTP | Meaning |
|---|---:|---|
| `ACC-404` | 404 | Account not found |
| `ACC-403` | 403 | Account not active / not reachable with this token |
| `INS-404` | 404 | Instrument not found / not tradable |
| `ORD-400` | 400 | Insufficient funds |
| `ORD-409` | 409 | Insufficient holdings / duplicate order / order not cancellable |
| `VAL-422` | 422 | Invalid input |
| `AUTH-401` | 401 | Unauthorised / invalid token |
| `INTERNAL-500` | 500 | Undocumented catch-all added so even unexpected failures keep the envelope — no whitelabel |

## 4. Deliverables / Files Created

### API Layer — `sprint-06-api`

| File | Role |
|---|---|
| `api/exception/GlobalExceptionHandler.java` | The `@RestControllerAdvice`; one `@ExceptionHandler` per failure family |
| `api/exception/ErrorCatalogue.java` | Single source of truth: code → `HttpStatus` map + the 8 code constants |
| `api/dto/ErrorResponse.java` | The envelope DTO — deliberately only two fields |

### Domain Layer — `sprint-05-domain-engine`

Shared JAR, re-installed to the local Maven repository.

| File | Role |
|---|---|
| `domain/exception/DomainException.java` | Abstract base: carries the `errorCode` string |

### Concrete Exceptions

There are 11 concrete exceptions:

| Exception | Error Code | Purpose |
|---|---|---|
| `AccountNotFoundException` | `ACC-404` | Account not found |
| `AccountNotActiveException` | `ACC-403` | Account inactive/not reachable |
| `InstrumentNotFoundException` | `INS-404` | Instrument not found/not tradable |
| `InsufficientFundsException` | `ORD-400` | Insufficient funds |
| `InsufficientHoldingsException` | `ORD-409` | Insufficient holdings |
| `DuplicateOrderException` | `ORD-409` | Duplicate order |
| `OrderNotFoundException` | `ORD-409` | Order not found |
| `OrderNotCancellableException` | `ORD-409` | Order cannot be cancelled |
| `OrderConflictException` | `ORD-409` | Order conflict |
| `InvalidOrderException` | `VAL-422` | Invalid order |
| `AuthenticationException` | `AUTH-401` | Authentication/invalid token failure |

Each concrete exception hard-codes its own `CODE` and `MESSAGE` constants.

For example:

```java
OrderNotFoundException.CODE = "ORD-409";
OrderNotFoundException.MESSAGE = "Order not found";
```

This ensures that the domain and API layers can never drift apart.

## 5. How It Works — Flow

The exception handling flow is:

```text
Controller / Service
        |
        | throws DomainException
        | OR
        | Spring raises validation/type-mismatch exception
        v
GlobalExceptionHandler
        |
        +-- handleDomainException
        |
        +-- handleValidation
        |
        +-- handleTypeMismatch
        |
        +-- handleUnexpected
        |
        v
ErrorResponse
        |
        v
HTTP Response
```

### Step-by-Step

1. A controller/service throws a `DomainException` or Alternatively, Spring raises:
   - `MethodArgumentNotValidException`
   - `MethodArgumentTypeMismatchException`

2. Spring routes the exception to `GlobalExceptionHandler`.

3. The handler uses one of four handling methods:

   - **`handleDomainException`**
     - Gets the status from `ErrorCatalogue.statusFor(code)`.
     - `OrderNotFoundException` is specially forced to HTTP `404`.
     - This implements the contract's DELETE special case.

   - **`handleValidation`**
     - Maps the error to `VAL-422`.

   - **`handleTypeMismatch`**
     - Maps the error to `VAL-422`.

   - **`handleUnexpected`**
     - Maps unexpected failures to `INTERNAL-500`.
     - Ensures that no Spring whitelabel error page reaches the client.

4. The response envelope is created:

```text
envelope(code, message, status)
        ↓
ResponseEntity<ErrorResponse>
```

5. Investigation details are extracted using `detailFor(e)`.

These details may include:

- `accountId`
- `symbol`
- amounts
- `idempotencyKey`

They are written **only to server logs**.

They are **never included in the response body**.

This prevents sensitive internal state from leaking to clients.

## 6. How It Cooperates With the Rest of the System

### Domain Exceptions

Domain exceptions from the JIRA 5 shared JAR are thrown by:

- `OrderService`
- `AccountService`

The handler processes them directly.

There is no guessing — the code and message come from the exception instance.

### Business Rule Ordering

`OrderService.placeOrder` throws on the first failing business rule.

The handler converts each exception into the documented code/status:

```text
ACC-404
   ↓
ACC-403
   ↓
INS-404
   ↓
VAL-422
   ↓
ORD-400
   ↓
ORD-409
```

### JWT / JIRA 8

`AuthenticationException` and the `AUTH-401` envelope branch are already prepared in:

- `ErrorCatalogue`
- `GlobalExceptionHandler`

However, actual token verification and HTTP 401 enforcement belong to the **JIRA 8 security-filter work**.

Therefore:

> This JIRA provides the error-handling mechanism; JIRA 8 provides the authentication trigger.

### Controllers

Controllers do **not** contain:

- `try/catch` blocks
- manually constructed error responses
- duplicated error-handling logic

They rely entirely on `GlobalExceptionHandler`.

This keeps the contract shape uniform across all six endpoints.

### Tests

The handler is verified at two levels:

- Unit level
- HTTP slice level

## 7. Test Evidence

### `GlobalExceptionHandlerTest`

**Type:** Pure unit tests  
**Total:** 19 tests

#### Catalogue — 7 tests

Verifies that:

- Every documented error code maps to its exact HTTP status.
- Unknown codes map to `500`.
- The handler never returns a misleading status.

#### Execution Paths — 8 tests

Verifies:

- Each domain exception returns the correct code.
- Each domain exception returns the correct status.
- Each domain exception returns the correct message.
- Bean validation maps to `VAL-422`.
- Bad token maps to `AUTH-401`.

#### Branchability — 4 tests

Verifies:

- `ACC-404` and `INS-404` share HTTP `404` but have different error codes.
- `ORD-409` can represent different business failures using different messages.
- Messages never leak internal identifiers.
- The response envelope contains exactly two fields using a reflection check.

### `GlobalExceptionHandlerWebTest`

**Type:** `@WebMvcTest` slice  
**Total:** 13 tests

Uses a test-only probe controller with no database or container.

Tests include:

- Correct HTTP status
- Correct `errorCode`
- Exact JSON response body
- Order-not-found → `404` + `ORD-409`
- Order-not-cancellable → `409`
- Type mismatch → `422`
- Bad token → `401`
- Unexpected exception → `INTERNAL-500`

### Overall Test Result

```text
GlobalExceptionHandlerTest      → 19 tests
GlobalExceptionHandlerWebTest   → 13 tests
                                  ---------
Total for this JIRA             → 32 tests
```

These are part of the **83-test green `mvn clean verify`** for `sprint-06-api`.

## 8. Key Points to Call Out in the Presentation

### 1. The 404 + ORD-409 Case

This is the strongest demonstration that:

> **Clients must branch on `errorCode`, not HTTP status alone.**

For example:

```text
HTTP 404
errorCode = ACC-404
→ Account not found
```

versus:

```text
HTTP 404
errorCode = ORD-409
→ Order not found
```

The HTTP status alone does not tell the client what actually happened.

### 2. INTERNAL-500 Is a Deliberate Safety Net

`INTERNAL-500` is intentionally outside the documented catalogue.

Its purpose is to ensure that even an unexpected server-side failure produces:

```json
{
  "errorCode": "INTERNAL-500",
  "message": "Internal server error"
}
```

instead of:

- Spring whitelabel page
- stack trace
- SQL error
- Java class name
- internal implementation details

This guarantees that the Angular client always receives a predictable, parseable envelope.

### 3. Two Aligned Sources of Truth

There are two important sources of truth:

```text
Domain Exceptions
       |
       | own
       ↓
  code + message


ErrorCatalogue
       |
       | owns
       ↓
  code → HTTP status
```

The tests pin both together so that the domain and API layers cannot silently drift apart.

### 4. Deliberate Scope Boundary

The handler is capable of returning:

```text
AUTH-401
```

However, it does **not** perform actual JWT validation.

The responsibility is split intentionally:

```text
JIRA — Global Exception Handler
        ↓
Provides AUTH-401 response mechanism

JIRA 8 — Security Filter
        ↓
Provides actual JWT verification
        ↓
Triggers AUTH-401
```

This keeps each JIRA focused on its intended responsibility.
