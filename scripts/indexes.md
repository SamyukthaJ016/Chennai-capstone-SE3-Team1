# Index Justifications

All six queries in `queries.sql` were run against the actual seed data
(loaded from `seed/*.csv` into a throwaway mirror, same rows `apply_db.py`
would load) to confirm each returns a sensible, correct result before any
indexing was reasoned about. Results:

- Query 1 (client 3, who has real open orders): returns order 15 (`RECEIVED`)
  and order 14 (`IN_PROGRESS`), newest first. Client 1, who has no open
  orders in the seed, correctly returns zero rows.
- Query 2 (client 1): returns their 5 seeded orders, newest `order_id` first.
- Query 3 (client 1): returns exactly their one non-zero delivery holding
  (RELIANCE, qty 45, avg 2887.0833); their intraday TCS position nets to 0
  and is correctly excluded.
- Query 4: structurally confirmed against all 23 seeded orders (see note on
  timestamps below).
- Query 5: resolving client 1's own `account_number` back to `clients`
  correctly returns exactly that one client.
- Query 6 (client 1): running total accumulates correctly across their 5
  filled orders (115020 → 173225 → 217475 → 313475 → 411043.75), and the
  rank-within-instrument column correctly splits into two independent rank
  sequences for instrument 1 and instrument 2.

## A note on `order_timestamp` in the seed data

`apply_db.py` loads all of `seed/*.csv` inside one transaction
(`README.md`, `scripts/apply_db.py`), and none of the seed CSVs supply a
value for `order_timestamp` or `transaction_timestamp` — both take their
column default, `now()`. Since `now()` returns the transaction start time,
not the statement time, every seeded row ends up with the *same*
`order_timestamp`. "Newest first" on timestamp alone is therefore not a
stable sort against this seed data — `order_id DESC` is used as an explicit
tiebreaker in Queries 1, 2, 4, and 6 for that reason, not just as a style
choice. Against real traffic, timestamps will actually differ and the
tiebreaker becomes a no-op for ties that no longer occur, so it's kept
either way.

## EXPLAIN ANALYZE

I don't have a live PostgreSQL instance in my environment to capture real
`EXPLAIN ANALYZE` timings (confirmed earlier in this thread — no network,
no `psql` binary, `apt-get install postgresql` fails). What follows is the
structural plan each query gets before and after indexing, reasoned from the
schema's existing indexes and standard PostgreSQL planner behaviour, which is
deterministic for these predicate/sort shapes regardless of exact row counts.
**The actual timed `EXPLAIN ANALYZE` output should be captured by running
these against the real database** (you already have one running) — paste
the output back and I'll fold the real numbers into this file.

To capture it yourself for any query below:

```sql
EXPLAIN ANALYZE
SELECT ...  -- the query, with a real value in place of the :param
```

run once before creating the new index, once after.

---

## Query 1 — all open orders for one account, newest first

**Before:** `orders` has `idx_orders_client_id` and `idx_orders_status`
separately (`005_orders.sql`). The planner can use one of them — most likely
`idx_orders_client_id`, since `client_id = :x` is more selective than
`status IN (...)` on a table where most orders eventually reach a terminal
state — then filter the `status` predicate row-by-row (`Filter:` in the plan,
not `Index Cond:`), and add an explicit `Sort` node for
`order_timestamp DESC` since neither index carries that order.

**New index:**

```sql
CREATE INDEX idx_orders_client_open_orders
    ON orders (client_id, order_timestamp DESC, order_id DESC)
    WHERE status IN ('RECEIVED', 'IN_PROGRESS');
```

A partial index, scoped to exactly the rows this query ever wants — closed
orders (the majority, over time) never enter this index at all, so it stays
small regardless of total order volume. `client_id` first for the equality
lookup, `order_timestamp DESC, order_id DESC` after it so the index already
holds rows in the exact output order — no separate `Sort` node needed.

**After:** `Index Scan` (or `Index Only Scan`) on
`idx_orders_client_open_orders`, `Index Cond: (client_id = :x)`, no `Sort`
node, no `Filter` on `status` (the partial index's `WHERE` already excludes
everything else).

**Cost on write:** every `INSERT`/`UPDATE` that touches `orders.status`
maintains this index — but only while a row's `status` is `RECEIVED` or
`IN_PROGRESS`; once a row transitions to `SUCCESS`/`FAILED` it drops out of
the index automatically (partial-index rows are added/removed as the `WHERE`
condition starts/stops matching). So the steady-state index size tracks the
open-order count, not the all-time order count — cheap indefinitely.

---

## Query 2 — last 50 orders for one account, any state, newest first

**Before:** same shape problem as Query 1 minus the status filter —
`idx_orders_client_id` narrows to the client, then a `Sort` on
`order_timestamp DESC` over however many orders that client has, then
`Limit 50`.

**New index:**

```sql
CREATE INDEX idx_orders_client_order_timestamp
    ON orders (client_id, order_timestamp DESC, order_id DESC);
```

Not partial — this one needs every order regardless of status, since the
query says "in any state."

**After:** `Index Scan` on `idx_orders_client_order_timestamp`,
`Index Cond: (client_id = :x)`, rows already delivered in the exact output
order, `Limit 50` stops the scan after 50 rows without reading the client's
full order history — the main win as an account's order count grows over
time.

**Cost on write:** every order insert/update maintains this index —
unavoidable, since every order for every client is in scope for this query.

---

## Query 4 — every order created since a given timestamp, across all accounts

**Before:** no existing index touches `order_timestamp` at all. This is a
full `Seq Scan` over `orders` with a `Filter: (order_timestamp > :ts)`, cost
proportional to total table size regardless of how few rows match.

**New index:**

```sql
CREATE INDEX idx_orders_order_timestamp ON orders (order_timestamp);
```

Single column, no partition by client — this query is explicitly
cross-account.

**After:** `Index Scan` on `idx_orders_order_timestamp`,
`Index Cond: (order_timestamp > :ts)` — cost proportional to the number of
matching rows, not total table size. This is the query that most needs an
index: it's the only one of the six with no `client_id` (or other already-
indexed column) in its predicate at all, so before this index it's the only
one of the six guaranteed to force a full scan.

**Cost on write:** every order insert maintains this index — one more
btree entry per order, same cost shape as the existing single-column indexes
on `orders`.

---

## Queries that need no new index

**Query 3 — everything one account currently holds.** Already served by
`idx_portfolio_holding_client_id` and `idx_portfolio_positions_client_id`
(both from `008_portfolio.sql`). `EXPLAIN` plan: `Index Scan` on each,
`Index Cond: (client_id = :x)`. Every client holds at most a handful of
instruments (`portfolio_holding`/`portfolio_positions` are one row per
`(client_id, instrument_id)` under a `UNIQUE` constraint — a client's row
count here is bounded by how many distinct instruments they've ever traded,
not by their order history), so there's nothing for a composite or covering
index to meaningfully improve — the per-client result set is already tiny by
construction.

**Query 5 — resolve an account from the customer-facing reference.**
Already served by `idx_clients_account_number` (`002_clients.sql`).
`EXPLAIN` plan: `Index Scan` on `idx_clients_account_number`,
`Index Cond: (account_number = :ref)`. This is exactly an equality lookup on
an indexed column — textbook case, nothing to add.

## Query 6 — no index

Per the ticket: answered with window functions
(`SUM() OVER`, `RANK() OVER`) rather than an index. The `WHERE client_id = :x`
predicate is already served by `idx_orders_client_id`, which narrows the
input to one client's orders before the window functions run over that
(small, per-client) row set — the window computation itself has nothing an
index can speed up, since it has to see every qualifying row regardless.
Brought to the design review as the ticket asks, not added here.
