# Team 1 — Trade Database (PostgreSQL)

SEC3-91 / SEC3-94 / SEC3-95

PostgreSQL schema for the trading platform, built from numbered migration files,
with a script to apply them and load seed data, and a test suite that checks the
result.

The schema mirrors the domain entities in `sprint-05-domain-engine` — one table
per entity class, one column per field. `verify_db.py` reads those Java classes
and fails if the two ever drift apart. See [docs/erd.md](docs/erd.md).

## Setup

Needs PostgreSQL (server + `psql`) and Python 3.8+. No third-party packages,
except `pytest` if you want to run the test suite.

```
python scripts/apply_db.py      # create the database, migrate, seed
python scripts/verify_db.py     # run the checks
python -m pytest tests/         # run the migration test suite
```

Defaults are `localhost:5432`, user `postgres`, database `trading_platform`.
Override with a CLI flag, a `PG*` environment variable, or a `.env` file —
flags win over env vars, env vars win over `.env`. Copy `.env.example` to `.env`
to set them permanently; `.env` is git-ignored.

If `psql` is not on `PATH` the scripts look in
`C:\Program Files\PostgreSQL\<version>\bin`, or set `PSQL_BIN`.

`.env.example` also carries `FAUXNANCE_API_KEY` and `FAUXNANCE_BASE_URL`, which
the analytics pipeline in `ETL_Analysis/` reads. The key ships empty on purpose:
put your own in `.env`, never in a source file, a test or a fixture.

## Layout

```
migrations/      numbered .sql files, the only definition of the schema
seed/            CSV data, loaded in filename order
scripts/         apply_db.py, verify_db.py, make_seed.py, db_config.py
tests/           pytest suite over the migrations, seed and schema parity
docs/            ERD and order lifecycle diagrams
infra/postgres/  docker compose setup
legacy/          the original single-file schema
```

## migrations/

The number is the order.

| File | Contents |
|---|---|
| `000_migration_ledger.sql` | `schema_migrations` tracking table |
| `001_bank_account.sql` | funding account |
| `002_clients.sql` | clients, wallet balance, account state rules |
| `003_auth.sql` | credentials, `version` for optimistic concurrency |
| `004_instruments.sql` | instruments keyed by symbol, delisting |
| `005_orders.sql` | orders, `order_type`, `side`, idempotency key |
| `006_order_history.sql` | audit trail of order status changes |
| `007_portfolio.sql` | `portfolio_holding` and `portfolio_positions` |
| `008_maintenance.sql` | `fn_resync_sequences()` |

Running `psql -f` over these in order rebuilds the database without the Python
scripts.

Do not edit a migration once it has been applied — add `009_`, `010_` instead,
since other people already have databases with data in them. `apply_db.py`
stores a sha256 of each file it applies and stops if one changed.

## scripts/apply_db.py

```
python scripts/apply_db.py                  # create db if needed, migrate, seed
python scripts/apply_db.py --reset          # drop the database and rebuild
python scripts/apply_db.py --reseed         # reload seed data
python scripts/apply_db.py --migrations-only
python scripts/apply_db.py --seed-only
python scripts/apply_db.py --dry-run
```

- Creates the database if it does not exist.
- Applies `migrations/*.sql` in filename order via `psql -v ON_ERROR_STOP=1`, so
  a failing migration stops the run instead of exiting zero.
- Records applied files in `schema_migrations` and skips them next time, so
  re-running is a no-op.
- Aborts if a migration changed after it was applied (`--allow-modified` to
  re-record, `--reset` to rebuild).
- Loads `seed/*.csv` in filename order inside one transaction. This is required,
  not stylistic: `clients` and `bank_account` reference each other, so one of the
  two foreign keys is deferred to `COMMIT`.
- Validates every seed file before loading any of it — unknown column, duplicate
  column, blank line, wrong field count, each reported with file and line. Type
  and constraint errors roll the whole load back. Bad rows are never skipped.
- Resyncs sequences past the seeded ids.

Seed files are named `NNN_<table>.csv`. The header row is the column list, so a
file only supplies the columns it has and the rest take their defaults. An
unquoted empty field is `NULL`.

## scripts/verify_db.py

```
python scripts/verify_db.py
python scripts/verify_db.py -v
python scripts/verify_db.py --only C
```

62 checks in four sections: structure, constraints, behaviour, data consistency.
Anything that writes runs inside `BEGIN`/`ROLLBACK`, so the database is unchanged
afterwards.

Two of them read the Java source rather than a hard-coded list. `A05` parses
every entity class and fails if a table has a column no field maps to, or a
field with no column. `B02` parses `OrderStatus`, `OrderType`, `OrderSide` and
`AccountStatus` and fails if a `CHECK` constraint's vocabulary differs from the
enum it stands for. Between them, the schema cannot drift from the entities
without a test going red.

Behavioural checks assert on SQLSTATEs — a duplicate idempotency key must raise
`23505`, a `FILLED` order with no executed price must be refused, a stale
credential writer must get rowcount 0.

Section D rebuilds both portfolio books by replaying the filled orders read back
from the database and compares them against the stored rows.

## tests/

```
python -m pytest tests/          # migrations, seed and schema parity
python -m pytest                 # the above plus the ETL_Analysis suite
```

Creates and drops its own `trading_platform_test` database, so your working
database is never touched. Set `TEST_DBNAME` to use a different name. The whole
suite skips cleanly if no PostgreSQL server is reachable.

What it covers beyond `verify_db.py`:

- every migration is numbered, unique and wrapped in a single transaction
- migrations apply to an empty database and create exactly the expected tables
- applying twice applies nothing the second time
- a migration edited after it was applied is refused, and `--allow-modified`
  re-records it
- a failing migration leaves nothing behind
- `--dry-run` creates no database
- `seed/` matches what `make_seed.py` generates, with no stray files
- seed row counts in the database match the CSV files
- a seed file with an unknown column or a short row is rejected, with the line
- reseeding is stable
- the seed genuinely cannot be loaded outside one transaction

## scripts/make_seed.py

```
python scripts/make_seed.py           # rewrite seed/
python scripts/make_seed.py --check   # fail if seed/ is out of date
python scripts/make_seed.py --prune   # also delete .csv files it does not generate
```

The dataset is fixed in the script, so output is deterministic. Portfolio rows
are computed by replaying the filled orders through `apply_fill()` rather than
typed in, so they always match the orders.

Covers all three client states, a delisted instrument with orders against it,
all four order statuses, both order types, an intraday short, and a position
squared off to zero.

`--check` also fails on a `.csv` in `seed/` that the script does not generate,
because `apply_db.py` would still load it.

## infra/postgres/

```
cd infra/postgres && docker compose up -d
```

Brings up Postgres with the migrations applied and seed data loaded.
`migrations/` and `seed/` are mounted from the repo rather than copied into an
image. The healthcheck waits for the schema, so `depends_on: service_healthy`
means the database is ready.

Not run against Docker — there is no Docker on the machine this was written on.
The init script itself was run against a local PostgreSQL 17 and produced a
database that passes all 62 checks.

## Notes

Money uses `DECIMAL(18,2)` for cash and `DECIMAL(18,4)` for prices and
quantities. A check asserts there is no `real`, `double precision` or `money`
column.

Idempotency is a `UNIQUE` constraint, not a read-then-write.

Optimistic concurrency on `auth.version`: read the version, then
`UPDATE ... WHERE version = <value read>`. Rowcount 0 means you lost. This sits
on `auth` rather than `bank_account` because `Auth` is the entity that carries a
`version` field and `changePassword()` increments it.

Instruments are keyed by their symbol (`RELIANCE`, `TCS`), because
`Instrument.instrumentId` is a `String`.

Nothing is deleted. Clients go to `CLOSED`, instruments to `active = FALSE`,
both enforced by triggers, and `CLOSED` is one-way.

An order's history lives in `order_history`, one row per status change. There is
no settlement queue and no terminal-state table: `orders.status` carries the
current state and `order_history` carries how it got there.

Settlement is application-layer work. The database decides which book a fill
belongs in (`orders.order_type`) and keeps the two books separate, but does not
move fills into them.

See [docs/erd.md](docs/erd.md) for the ERD and the details.
