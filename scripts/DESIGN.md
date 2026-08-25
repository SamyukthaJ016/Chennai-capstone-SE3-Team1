# Execution Retention — Design

## What is retained beyond the order

`orders` records what a client asked for: instrument, side, quantity, requested
price, product type, exchange, idempotency key. It does not record what
actually happened when the order was worked.

`transaction_success` and `transaction_failures` record the outcome. Beyond
what `orders` already carries, each terminal row adds:

- `value` — the executed value of the fill (success) or the value at the point
  of rejection (failure). Not necessarily `quantity * price_per_unit` from the
  order: a fill can differ from the requested price, which is the whole reason
  this is a separate fact rather than a column derived from `orders`.
- `transaction_timestamp` — when execution concluded, distinct from
  `orders.order_timestamp` (when the order was received). The gap between the
  two is the order's time-in-queue.
- `reason_for_failure` — only on the failure side; there is nothing on the
  order to explain a rejection.
- `transaction_id` — a terminal-event identity distinct from `order_id`,
  needed because extraction (below) walks terminal events, not orders.

## Grain

One row per order per terminal table, at the point the order reaches a
terminal state. This is enforced, not just intended: `order_id` is `UNIQUE` in
each of `transaction_success` and `transaction_failures`, and
`fn_enforce_single_terminal_state()` (`007_transaction_terminal_states.sql`)
rejects an insert into either table if a row for that `order_id` already
exists in the other. An order has at most one execution outcome, ever.

This is coarser than a fill-level grain. A single order that is worked in
multiple partial fills is not modelled as multiple rows — the schema captures
the order's final outcome, not a fill-by-fill execution log. If partial-fill
detail is ever needed (e.g. for slippage analysis fill-by-fill rather than
order-by-order), that is a new table keyed on `(order_id, fill_sequence)`, not
a change to the grain described here.

## Population

Written by whatever component decides the execution outcome — the same
component that moves an order out of `in_progress` (see
`docs/order_lifecycle.md` / `erd.md`). That component does exactly one of:

- `INSERT INTO transaction_success (order_id, quantity, value, ...)`
- `INSERT INTO transaction_failures (order_id, quantity, value, reason_for_failure, ...)`

The trigger then sets `orders.status` to `SUCCESS` or `FAILED` as a side
effect of that insert — the caller does not set `orders.status` directly, and
does not touch `portfolio_holding` / `portfolio_positions` directly either;
per `erd.md`, moving a successful fill into the correct book by
`orders.product_type` is application-layer work done after this insert, not
part of this table's write path.

## Incremental extraction (Sprint 7)

A downstream extract (analytics, a data warehouse, whatever Sprint 7 turns
out to be) needs to read new terminal events without rescanning both tables
from the start every run.

Position on the cursor: use `transaction_id`, not `transaction_timestamp`.
Both are monotonically increasing per table, but `transaction_id` is a
`SERIAL` primary key with no ties and no clock skew to worry about if the
writer ever runs on more than one connection concurrently; a timestamp cursor
risks missing a row whose commit lands after the extract already read past
that wall-clock second. The extract keeps a high-water mark per table
(`last_transaction_success_id`, `last_transaction_failures_id`) and each run
does:

```sql
SELECT * FROM transaction_success  WHERE transaction_id > :last_success_id  ORDER BY transaction_id;
SELECT * FROM transaction_failures WHERE transaction_id > :last_failure_id ORDER BY transaction_id;
```

Both tables are read separately and the high-water marks advance
independently — there is no need to merge them into one ordered stream, since
nothing downstream requires success and failure events to be interleaved in
strict global order across the two tables.

This needs an index to stay fast as the tables grow: today, the only index on
either table is the primary key (`transaction_id`) and the `UNIQUE` on
`order_id` — the primary key already serves this access pattern directly
(`WHERE transaction_id > :last_id ORDER BY transaction_id` is a forward scan
off the PK's own btree), so no new index is needed for the extract itself.

## Behaviour at 100x volume

The write path (the trigger) does two `EXISTS` lookups per insert, each
served by the `UNIQUE` index on `order_id` — O(1) relative to table size, so
100x the row count does not change per-insert cost materially.

The extract's `WHERE transaction_id > :last_id` stays a cheap index range
scan at any table size, for the same reason. What does grow linearly is
table and index size on disk, and the duration of a full table scan if
anything ever needs one (ad hoc reporting, a rebuild).

Cost on write: unchanged in kind, same two `EXISTS` checks regardless of
table size — the cost is per-row, not per-table-size, so 100x volume is 100x
the total write cost, not 100x the cost of any individual write.

Operational complexity: the main new concern at 100x is table bloat and
vacuum/autovacuum pressure on two tables that only ever grow (rows are never
updated after insert, so this is append-heavy and vacuum-friendly, but
autovacuum thresholds tuned for the current size may need revisiting).
Backup and restore time also grows linearly with table size, independent of
query performance.

## Position on partitioning, archival, retention

No partitioning yet. The argument: every current access pattern —
the terminal-state trigger's `EXISTS` checks, the extract's
`transaction_id > :last_id` scan, `verify_db.py`'s D-section consistency
checks — is already served by an index that does not degrade with table size
(btree lookups and range scans are `O(log n)` / sequential, not `O(n)`).
Partitioning earns its complexity when a specific query pattern needs it —
typically because most reads only touch a recent time window and partition
pruning would let the planner skip old partitions entirely. Nothing here
does that yet: the extract reads *forward* from a cursor near the current
end of the table regardless of how old the table gets, and there is no
"only show me last month" query in this schema today.

If a genuine time-windowed access pattern shows up later (e.g. "reporting
only ever looks at the trailing 90 days"), range-partitioning
`transaction_success` / `transaction_failures` by `transaction_timestamp`
is the natural fit, since that's already the append-order and the terminal
trigger and extract queries would be unaffected — the trigger's `EXISTS`
check on `order_id` and the extract's `transaction_id` cursor scan don't
care whether the table is partitioned underneath.

Archival: also not yet, for the same reason — nothing currently needs old
rows moved or dropped, and `verify_db.py`'s D-section checks replay the full
order history to reconstruct the portfolio books, so archiving terminal rows
would need to preserve that replay capability (an archive table with the
same shape, not a delete) rather than a straightforward drop.

This is a decision to revisit, not a closed question — it should be brought
to the design review named in the ticket, specifically to confirm no
time-windowed read pattern is already planned for Sprint 7 that would change
the answer above.
