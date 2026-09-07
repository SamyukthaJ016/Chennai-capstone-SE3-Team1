# Index Justifications

All six queries in `queries.sql` were run against the actual seed data to confirm
each returns a correct result before any indexing was reasoned about. Query 1
(client 3) returns their two open orders newest first; query 3 returns their
non-zero holdings and their open TATAMOTORS position; query 6 accumulates a
running total across their filled orders and ranks independently per instrument.

## How the plans below were captured

Every `EXPLAIN ANALYZE` in this file is real output from PostgreSQL 17.11, not a
predicted plan.

The seed data is 23 orders, which is too small for the planner to do anything
but sequential scans, so the plans were captured against a copy of the schema
loaded with **200,023 orders** — the 23 seeded ones plus 200,000 generated
across the same 6 clients and 8 instruments, 70% `FILLED`, 10% `NEW`, spread
over a 55-hour window of `created_at`. `ANALYZE` was run before each capture.

Reproduce it with `scripts/apply_db.py --dbname plans_probe --reset`, the bulk
insert in the section below, then `EXPLAIN ANALYZE` each query.

The three tables that queries 3 and 5 touch (`portfolio_holding`,
`portfolio_positions`, `clients`) were left at seed size, because their row
count is bounded by distinct instruments traded per client and by client count
respectively — neither grows with order volume.

---

## Query 1 — all open orders for one account, newest first

**Before**, with only `idx_orders_client_id` and `idx_orders_status` from
`005_orders.sql`:

```
Sort  (cost=3972.84..3981.18 rows=3335) (actual time=9.338..9.340 rows=2 loops=1)
  Sort Key: created_at DESC, order_id DESC
  ->  Bitmap Heap Scan on orders  (actual time=0.991..9.309 rows=2 loops=1)
        Recheck Cond: ((status)::text = 'NEW'::text)
        Filter: (client_id = 3)
```

The planner used `idx_orders_status`, then filtered `client_id` row by row, then
sorted. It touched every one of the 20,002 `NEW` rows to return 2.

**New index:**

```sql
CREATE INDEX idx_orders_client_open_orders
    ON orders (client_id, created_at DESC, order_id DESC)
    WHERE status = 'NEW';
```

Partial, scoped to exactly the rows this query wants. Orders that reach a
terminal state leave the index automatically.

**After:**

```
Sort  (cost=3712.11..3720.32 rows=3286) (actual time=0.053..0.053 rows=2 loops=1)
  ->  Bitmap Heap Scan on orders  (actual time=0.027..0.028 rows=2 loops=1)
        Recheck Cond: ((client_id = 3) AND ((status)::text = 'NEW'::text))
        Heap Blocks: exact=1
        ->  Bitmap Index Scan on idx_orders_client_open_orders (actual time=0.014..0.014 rows=2)
              Index Cond: (client_id = 3)
Execution Time: 0.088 ms
```

**9.34 ms → 0.088 ms**, and one heap block instead of a scan over 20,002 rows.

The `Sort` node survives because the planner chose a bitmap scan, which does not
preserve index order. At this row count that sorts 2 rows and costs nothing. A
client with enough open orders for the sort to matter would get a plain index
scan instead, which is already ordered.

**Index size:** 808 kB against 4408 kB for the unfiltered equivalent, because
only the ~10% of rows that are `NEW` are in it.

**Cost on write:** maintained only while a row's status is `NEW`. Once an order
is filled, rejected or cancelled it drops out. Steady-state size tracks the open
order count, not the all-time order count.

---

## Query 2 — last 50 orders for one account, any state, newest first

**Before:**

```
Limit  (actual time=23.108..23.113 rows=50 loops=1)
  ->  Sort  (actual time=23.106..23.107 rows=50 loops=1)
        Sort Key: created_at DESC, order_id DESC
        Sort Method: top-N heapsort  Memory: 38kB
        ->  Bitmap Heap Scan on orders (actual time=1.667..15.330 rows=33341 loops=1)
              Recheck Cond: (client_id = 3)
```

All 33,341 of the client's orders read and sorted to return 50.

**After:**

```
Limit  (cost=0.70..16.53 rows=50) (actual time=0.090..0.118 rows=50 loops=1)
  ->  Incremental Sort  (actual time=0.088..0.114 rows=50 loops=1)
        Presorted Key: created_at
        ->  Index Scan Backward using idx_orders_created_at on orders
              (actual time=0.018..0.063 rows=51 loops=1)
              Filter: (client_id = 3)
              Rows Removed by Filter: 231
Execution Time: 0.188 ms
```

**23.11 ms → 0.188 ms.**

### The composite index for this query is not used, and should be dropped

`idx_orders_client_created_at (client_id, created_at DESC, order_id DESC)` was
added for exactly this query. The planner does not use it. It walks
`idx_orders_created_at` backwards and filters instead, discarding 231 rows to
find 50.

This is not a statistics accident. It was tested at three densities:

| Client's share of the table | Rows | Plan chosen |
|---|---|---|
| 1 in 6 | 33,341 of 200,023 | `Index Scan Backward using idx_orders_created_at` + filter |
| 1 in 41 | 5,000 of 205,083 | `Index Scan Backward using idx_orders_created_at` + filter |
| 1 in 3,400 | 60 of 205,083 | `idx_orders_client_id` + sort (only 60 rows to sort) |

`pg_stat_user_indexes.idx_scan` for `idx_orders_client_created_at` is **0** after
all of them. Dropping it inside a transaction and re-running the middle case
produces a byte-identical plan at the same cost (`cost=2.43..104.84`, 0.35 ms).

It is the largest index on the table — **7944 kB at 200k rows**, against 4408 kB
for `idx_orders_created_at` and 808 kB for the partial index — and it is
maintained on every single order insert and update.

**Recommendation: drop it.** It is still in `010_query_indexes.sql` so that
nothing disappears without the team agreeing, but it currently costs write
throughput and disk for no measured read benefit. The case for keeping it would
be a query shape that changes the trade-off — an offset deep into one client's
history, or a client whose order count grows large enough that the backward scan
has to discard a lot before finding 50. Neither exists in `queries.sql` today.

---

## Query 4 — every order created since a given timestamp, across all accounts

**Before:** no index touched `created_at` at all.

```
Gather Merge  (actual time=55.600..62.285 rows=23 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Sort  (actual time=9.241..9.242 rows=8 loops=3)
        Sort Key: created_at, order_id
```

A parallel sequential scan over the whole table, two extra worker processes
started, to return 23 rows.

**New index:**

```sql
CREATE INDEX idx_orders_created_at ON orders (created_at);
```

Single column, no partition by client — this query is explicitly cross-account.

**After:**

```
Incremental Sort  (actual time=0.044..0.045 rows=23 loops=1)
  Presorted Key: created_at
  ->  Index Scan using idx_orders_created_at on orders
        (actual time=0.008..0.012 rows=23 loops=1)
        Index Cond: (created_at > '2026-01-03 12:00:00'::timestamp without time zone)
Execution Time: 0.083 ms
```

**62.29 ms → 0.083 ms**, and no parallel workers. This is the query that most
needed an index: the only one of the six with no `client_id` in its predicate,
so before this it was the only one guaranteed to scan the whole table.

It also turns out to be the index that queries 2 and 4 both rely on, which is
the reason the composite index above earns nothing.

**Cost on write:** one btree entry per order, same shape as the existing
single-column indexes.

---

## Queries that need no new index

**Query 3 — everything one account currently holds.**

```
Append  (actual time=0.070..0.096 rows=3 loops=1)
  ->  Bitmap Heap Scan on portfolio_holding h (actual time=0.036..0.037 rows=2)
        Filter: (quantity <> 0)
        ->  Bitmap Index Scan on idx_portfolio_holding_client_id
              Index Cond: (client_id = 3)
```

Already served by `idx_portfolio_holding_client_id` and
`idx_portfolio_positions_client_id` from `007_portfolio.sql`. The join to
`instruments` is a sequential scan over 8 rows, which is correct — an index on a
table that fits in one page is slower than reading the page.

A client's row count here is bounded by how many distinct instruments they have
ever traded, under a `UNIQUE (client_id, instrument_id)` constraint, not by their
order history. There is nothing for a composite index to improve.

**Query 5 — resolve an account from the customer-facing reference.**

```
Index Scan using idx_clients_account_number on clients
  Index Cond: ((account_number)::text = 'IN45HDFC0000001234567'::text)
Execution Time: 0.056 ms
```

Already served by `idx_clients_account_number` from `002_clients.sql`. An
equality lookup on an indexed column — nothing to add.

**Query 6 — running cash committed, ranked within instrument.**

```
Sort  (actual time=61.170..63.793 rows=26672 loops=1)
  Sort Key: created_at, order_id
  ->  Sort  (actual time=44.651..46.257 rows=26672 loops=1)
        Sort Key: instrument_id, ((executed_price * quantity)) DESC
        ->  Bitmap Heap Scan on orders o (actual time=1.094..17.946 rows=26672 loops=1)
```

Per the ticket, answered with window functions rather than an index. The
measurement supports that: of the ~64 ms, the bitmap scan that fetches the rows
takes 18 ms and the two sorts the window functions require take the rest. An
index can only help the first part. `RANK() OVER (PARTITION BY instrument_id
ORDER BY executed_price * quantity DESC)` sorts on an expression, so no ordinary
index can supply that order.

If this query ever matters at volume, the lever is an index on the expression:

```sql
CREATE INDEX idx_orders_client_value
    ON orders (client_id, instrument_id, ((executed_price * quantity) DESC));
```

That is speculative and not added here. Brought to the design review as the
ticket asks.

---

## Reproducing the volume dataset

```sql
INSERT INTO orders (client_id, account_id, instrument_id, order_type, side, quantity,
                    price, executed_price, status, idempotency_key, created_at, updated_at)
SELECT
  (g % 6) + 1,
  (g % 6) + 1,
  (ARRAY['RELIANCE','TCS','INFY','HDFCBANK','ICICIBANK','ITC','TATAMOTORS','LEGACYCORP'])[(g % 8) + 1],
  CASE WHEN g % 2 = 0 THEN 'HOLDING' ELSE 'POSITION' END,
  CASE WHEN g % 3 = 0 THEN 'SELL' ELSE 'BUY' END,
  ((g % 100) + 1)::decimal,
  ((g % 5000) + 100)::decimal,
  CASE WHEN g % 10 < 7 THEN ((g % 5000) + 100)::decimal ELSE NULL END,
  CASE WHEN g % 10 < 7 THEN 'FILLED' WHEN g % 10 = 7 THEN 'NEW'
       WHEN g % 10 = 8 THEN 'REJECTED' ELSE 'CANCELLED' END,
  'bulk-' || g,
  timestamp '2026-01-01' + (g || ' seconds')::interval,
  timestamp '2026-01-01' + (g || ' seconds')::interval
FROM generate_series(1, 200000) g;
ANALYZE orders;
```

The `executed_price` cases are aligned with the `status` cases on purpose:
`chk_orders_filled_has_executed_price` and
`chk_orders_executed_price_only_when_filled` reject any row where they disagree.
