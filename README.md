# Team 1 — Trade Database (PostgreSQL)

SEC3-91 / SEC3-94 / SEC3-95

PostgreSQL schema for the trading platform, built from numbered migration files,
with a script to apply them and load seed data, and a test script that checks the
result.

## Setup

Needs PostgreSQL (server + `psql`) and Python 3.8+. No third-party packages.

```
python scripts/apply_db.py      # create the database, migrate, seed
python scripts/verify_db.py     # run the checks
```

Defaults are `localhost:5432`, user `postgres`, database `trading_platform`.
Override with a CLI flag, a `PG*` environment variable, or a `.env` file —
flags win over env vars, env vars win over `.env`. Copy `.env.example` to `.env`
to set them permanently.

If `psql` is not on `PATH` the scripts look in
`C:\Program Files\PostgreSQL\<version>\bin`, or set `PSQL_BIN`.

## Layout

```
migrations/      numbered .sql files, the only definition of the schema
seed/            CSV data, loaded in filename order
scripts/         apply_db.py, verify_db.py, make_seed.py, db_config.py
docs/            ERD and order lifecycle diagrams
infra/postgres/  docker compose setup
legacy/          the original single-file schema
```

## migrations/

The number is the order.

| File | Contents |
|---|---|
| `000_migration_ledger.sql` | `schema_migrations` tracking table |
| `001_bank_account.sql` | funding account, `version` column |
| `002_clients.sql` | clients, account state rules |
| `003_auth.sql` | credentials |
| `004_instruments.sql` | instruments, delisting |
| `005_orders.sql` | orders, `product_type`, idempotency key |
| `006_in_progress.sql` | execution queue |
| `007_transaction_terminal_states.sql` | success/failure tables and trigger |
| `008_portfolio.sql` | `portfolio_holding` and `portfolio_positions` |
| `009_maintenance.sql` | `fn_resync_sequences()` |

Running `psql -f` over these in order rebuilds the database without the Python
scripts.

Do not edit a migration once it has been applied — add `010_`, `011_` instead,
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
- Loads `seed/*.csv` in filename order inside one transaction.
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

54 checks in four sections: structure, constraints, behaviour, data consistency.
Anything that writes runs inside `BEGIN`/`ROLLBACK`, so the database is unchanged
afterwards.

Behavioural checks assert on SQLSTATEs — a duplicate idempotency key must raise
`23505`, an order that already succeeded must be refused a failure row, a stale
balance writer must get rowcount 0.

Section D rebuilds both portfolio books by replaying the successful orders read
back from the database and compares them against the stored rows.

## scripts/make_seed.py

```
python scripts/make_seed.py           # rewrite seed/
python scripts/make_seed.py --check   # fail if seed/ is out of date
```

The dataset is fixed in the script, so output is deterministic. Portfolio rows
are computed by replaying the successful orders through `apply_fill()` rather
than typed in, so they always match the orders.

Covers all three client states, a delisted instrument with orders against it,
all four order statuses, both product types, an intraday short, and a position
squared off to zero.

## infra/postgres/

```
cd infra/postgres && docker compose up -d
```

Brings up Postgres with the migrations applied and seed data loaded.
`migrations/` and `seed/` are mounted from the repo rather than copied into an
image. The healthcheck waits for the schema, so `depends_on: service_healthy`
means the database is ready.

Not run against Docker — there is no Docker on the machine this was written on.
The init script itself was run against a local PostgreSQL and produced a
database that passes all 54 checks.

## Notes

Money uses `DECIMAL(18,2)` for cash and `DECIMAL(18,4)` for prices. A check
asserts there is no `real`, `double precision` or `money` column.

Idempotency is a `UNIQUE` constraint, not a read-then-write.

Optimistic concurrency on `bank_account.version`: read the version, then
`UPDATE ... WHERE version = <value read>`. Rowcount 0 means you lost.

Nothing is deleted. Clients go to `CLOSED`, instruments to `is_active = FALSE`,
both enforced by triggers, and `CLOSED` is one-way.

Settlement is application-layer work. The database decides which book a fill
belongs in (`orders.product_type`) and keeps the two books separate, but does not
move fills into them.

See [docs/erd.md](docs/erd.md) for the ERD and the details.
