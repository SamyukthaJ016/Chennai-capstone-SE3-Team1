# Execution Retention — Design

## What is retained beyond the order

`orders` records what a client asked for and where it ended up: instrument,
side, quantity, requested price, order type, idempotency key, and the current
`status`. It does not record how it got there.

`order_history` records that. One row per status change, and beyond what
`orders` already carries each row adds:

- `previous_status` → `new_status` — the transition itself. `orders.status` is
  only ever the latest value; this is the path.
- `event_type` — what the writer was doing (`CREATED`, `FILLED`, `REJECTED`,
  `CANCELLED`). Distinct from `new_status` because two different events can
  land on the same status.
- `event_timestamp` — when the transition happened, distinct from
  `orders.created_at` (when the order was received). The gap between the
  `CREATED` row and the terminal row is the order's time-in-flight.
- `failure_code` and `failure_reason` — only on a rejection; there is nothing
  on the order to explain one.
- `external_status`, `external_order_id`, `request_id`, `api_response` — what
  the venue said, kept verbatim. When our status and theirs disagree, this is
  the only record of the disagreement.
- `history_id` — an event identity distinct from `order_id`, needed because
  extraction (below) walks events, not orders.

`orders.executed_price` holds the price a fill actually happened at, which is
not necessarily the `price` that was asked for. That difference is the whole
reason both columns exist.

## Grain

One row per status transition, per order. An order that is created and then
filled has two rows; one that is created and never worked has one.

This is finer than the grain it replaces. The previous schema had one row per
order per terminal table, so an order carried at most one outcome record and
nothing about the path to it. The current grain keeps the path, at the cost of
more rows per order.

It is still not fill-level. An order worked in several partial fills is one
`FILLED` transition, not one row per fill. If partial-fill detail is ever
needed — slippage analysis fill-by-fill rather than order-by-order — that is a
new table keyed on `(order_id, fill_sequence)`, not a change to this grain.

A `CHECK` rejects a row whose `previous_status` equals its `new_status`, so an
event that records no change cannot be written. Both status columns are
constrained to the `OrderStatus` vocabulary, and `verify_db.py` asserts that
vocabulary against the Java enum rather than a hard-coded list.

## Population

Written by whatever component changes `orders.status`, in the same transaction
as the `UPDATE`. The pair is:

```sql
UPDATE orders SET status = 'FILLED', executed_price = :price, updated_at = now()
 WHERE order_id = :id AND status = 'NEW';

INSERT INTO order_history (order_id, event_type, previous_status, new_status,
                           external_order_id, request_id)
VALUES (:id, 'FILLED', 'NEW', 'FILLED', :external_id, :request_id);
```

Moving a fill into the correct book by `orders.order_type` is application-layer
work done after this, not part of this table's write path — the same division
as before.

### One thing this design gives up

The previous schema enforced the link with a trigger: inserting into
`transaction_success` set `orders.status` itself, so the status and the record
of it could not disagree. Here `orders.status` is authoritative and the audit
row is written alongside it, so a caller that updates the status and forgets
the `INSERT` leaves no trace.

`verify_db.py` catches that after the fact — D03 requires every order to have a
`CREATED` event, and D04 requires the latest event's `new_status` to equal
`orders.status` — but that is a consistency check on data at rest, not a
guarantee at write time.

Closing the gap properly means a trigger on `orders`:

```sql
CREATE TRIGGER trg_orders_audit AFTER UPDATE OF status ON orders
    FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION fn_write_order_history();
```

That is not in the schema, because the entities model `OrderHistory` as an
object the application constructs and populates — `event_type`, `request_id`
and `api_response` are known to the caller and not to the database, so a
trigger could only ever write a partial row. Bring it to the design review: the
choice is a partial row that is always written against a complete row that is
written by convention.

## Incremental extraction (Sprint 7)

A downstream extract needs to read new events without rescanning the table from
the start every run.

Position on the cursor: use `history_id`, not `event_timestamp`. Both increase
per row, but `history_id` is a `BIGSERIAL` primary key with no ties and no clock
skew to worry about if the writer ever runs on more than one connection
concurrently; a timestamp cursor risks missing a row whose commit lands after
the extract already read past that wall-clock second. The extract keeps one
high-water mark and each run does:

```sql
SELECT * FROM order_history WHERE history_id > :last_history_id ORDER BY history_id;
```

One table and one cursor, where the previous design needed two of each and had
to reason about whether success and failure events needed interleaving. They
did not, but the question no longer arises.

No new index is needed: `WHERE history_id > :last_id ORDER BY history_id` is a
forward scan off the primary key's own btree.

## Behaviour at 100x volume

The write path is a plain `INSERT` with one foreign-key lookup on `order_id`,
served by the primary key of `orders` — O(1) relative to table size, so 100x the
row count does not change per-insert cost materially. This is cheaper than the
design it replaces, which did two `EXISTS` lookups per insert inside a trigger.

The extract's `WHERE history_id > :last_id` stays a cheap index range scan at
any table size, for the same reason.

Reading one order's history — `WHERE order_id = :id ORDER BY event_timestamp` —
is served by `idx_order_history_order_id`, which carries both columns in that
order, so it stays an index scan with no sort at any size.

What grows linearly is table and index size on disk, and the duration of a full
scan if anything ever needs one. The row count now grows faster than before:
roughly two rows per order rather than one, and more if orders acquire more
intermediate states.

Operational complexity: the main new concern at 100x is table bloat and
autovacuum pressure on a table that only ever grows. Rows are never updated
after insert, so this is append-heavy and vacuum-friendly, but autovacuum
thresholds tuned for the current size may need revisiting. Backup and restore
time also grows linearly with table size, independent of query performance.

## Position on partitioning, archival, retention

No partitioning yet. Every current access pattern — the extract's
`history_id > :last_id` scan, per-order history reads, `verify_db.py`'s
D-section checks — is already served by an index that does not degrade with
table size.

Partitioning earns its complexity when most reads only touch a recent time
window and partition pruning would let the planner skip old partitions. Nothing
here does that yet: the extract reads forward from a cursor near the end of the
table regardless of how old the table gets, and there is no "only show me last
month" query in this schema today.

If a genuine time-windowed access pattern shows up later, range-partitioning
`order_history` by `event_timestamp` is the natural fit, since that is already
close to append order. The extract's `history_id` cursor would then span
partitions, which is the one thing to check before doing it.

Archival: also not yet. `verify_db.py`'s D-section replays orders to
reconstruct the portfolio books, and D04 needs the latest event per order, so
archiving history rows would need to preserve at least the terminal event per
order — an archive table with the same shape, not a delete.

This is a decision to revisit, not a closed question — bring it to the design
review named in the ticket, specifically to confirm no time-windowed read
pattern is already planned for Sprint 7 that would change the answer above.
