# Team 1 — Trade Database (PostgreSQL)

SEC3-91 · SEC3-94 (schema) · SEC3-95 (apply command)

A PostgreSQL trading schema built from numbered migration files, with a
one-command apply/seed tool and a verification suite that checks the database
against the acceptance criteria rather than assuming it meets them.

---

## Quick start

You need PostgreSQL (server + `psql`) and Python 3.8+. Nothing else — the
scripts are standard library only, so there is no `pip install` step and no
virtualenv to activate.

```bash
python scripts/apply_db.py      # create the database, migrate, seed
python scripts/verify_db.py     # prove it is correct  -> 54 checks
```

That is the whole setup. There are no variables to export first: every setting
has a working default (`localhost:5432`, user `postgres`, database
`trading_platform`). Override any of them with a CLI flag, a `PG*` environment
variable, or a `.env` file — in that order of precedence. See `.env.example`.

If `psql` is not on your `PATH`, the scripts look in
`C:\Program Files\PostgreSQL\<version>\bin` automatically; otherwise set
`PSQL_BIN`.

---

## Layout

```
migrations/    numbered .sql files - the ONLY definition of the schema
seed/          CSV data files, loaded in filename order
scripts/       apply_db.py, verify_db.py, make_seed.py, db_config.py
docs/          ERD + order lifecycle diagrams (mermaid source and PNG)
infra/postgres/ docker compose that builds the same database unattended
legacy/        the original single-blob schema this replaced, kept for reference
```

### `migrations/`

The number is the order. Each file is self-contained, wrapped in
`BEGIN`/`COMMIT`, and split by concern so a change is reviewable:

| File | Contents |
|---|---|
| `000_migration_ledger.sql` | `schema_migrations` bookkeeping table |
| `001_bank_account.sql` | funding account, `version` optimistic lock |
| `002_clients.sql` | clients + `ACTIVE`/`SUSPENDED`/`CLOSED` state rules |
| `003_auth.sql` | credentials |
| `004_instruments.sql` | instruments + delisting rules |
| `005_orders.sql` | orders, `product_type`, idempotency `UNIQUE` |
| `006_in_progress.sql` | the execution queue |
| `007_transaction_terminal_states.sql` | the two terminal tables + trigger |
| `008_portfolio.sql` | `portfolio_holding` **and** `portfolio_positions` |
| `009_maintenance.sql` | `fn_resync_sequences()` |

The database can be rebuilt from these files alone — `psql -f` each one in
filename order and you get the same schema, with or without the Python tool.

**Once a migration has been applied, do not edit it.** Add `010_`, `011_` and so
on instead; teammates already have databases with data in them. The apply
command enforces this: it stores a sha256 of every file it applies and refuses
to continue if one changed underneath it.

---

## `scripts/apply_db.py` — the apply command (SEC3-95)

```bash
python scripts/apply_db.py                  # create db if needed, migrate, seed
python scripts/apply_db.py --reset          # drop the database and rebuild
python scripts/apply_db.py --reseed         # reload seed data over the schema
python scripts/apply_db.py --migrations-only
python scripts/apply_db.py --seed-only
python scripts/apply_db.py --dry-run        # report, change nothing
```

What it guarantees:

- **Creates the database** if it does not exist. A fresh machine needs no manual
  step before this command.
- **Applies every `migrations/*.sql` in filename order** through
  `psql -v ON_ERROR_STOP=1`, so a migration that errors *stops the run* instead
  of reporting an error, carrying on, and exiting zero.
- **Safe to run often.** Applied files are recorded in `schema_migrations` with
  a checksum and skipped next time; re-running is a no-op that exits 0.
- **Catches edited migrations.** A file whose contents changed after it was
  applied aborts the run with both checksums and instructions
  (`--allow-modified` to re-record, `--reset` to rebuild).
- **Loads every `seed/*.csv` in filename order, inside one transaction.**
- **Fails the load rather than skipping a row that cannot be mapped.** Every
  file is validated before *anything* is loaded — unknown column, duplicate
  column, blank line, wrong field count — each reported with the file and line
  number. Type and constraint failures are caught by Postgres and roll the whole
  load back. No row is ever silently dropped.
- **Resyncs the sequences** past the seeded ids, so the application's first
  insert does not collide with seed data.

`seed/NNN_<table>.csv` — the number is load order, the rest is the table name.
The header row is the column list, so a file only supplies the columns it has
and everything else takes its `DEFAULT`. An unquoted empty field is `NULL`.

---

## `scripts/verify_db.py` — does it actually meet the criteria?

```bash
python scripts/verify_db.py           # 54 checks
python scripts/verify_db.py -v        # list passing checks too
python scripts/verify_db.py --only C  # one section
```

Four sections: **A** structure, **B** constraints, **C** behaviour, **D** data
consistency. Everything that writes runs inside `BEGIN`/`ROLLBACK`, so the
database is unchanged afterwards even when a check fails.

The behavioural checks assert on real SQLSTATEs, not on prose. For example a
duplicate `idempotency_key` must raise `23505` — Sprint 6 depends on that unique
violation being detectable — and an order that already succeeded must be refused
a failure row.

Section D re-derives both portfolio books by replaying the successful orders
*read back out of the database* and compares them against the stored rows, so a
settlement bug shows up as a diff instead of as plausible-looking numbers.

The suite has been mutation-tested: dropping the idempotency constraint, the
terminal-state triggers, or the composite FK, forbidding shorts in
`portfolio_positions`, giving `product_type` a default, turning `avg_price` into
a float, corrupting a holding, and rewinding a sequence each fail exactly the
checks they should.

---

## `scripts/make_seed.py` — the seed generator

```bash
python scripts/make_seed.py           # (re)write seed/
python scripts/make_seed.py --check   # fail if seed/ is out of date
```

The dataset is written out by hand in the script and is deterministic, so a diff
in `seed/` always means someone changed something on purpose.

The portfolio rows are **not** typed in — they are computed by replaying every
successful order through `apply_fill()`, the same settlement arithmetic the
application layer should use. The seeded portfolio therefore cannot disagree
with the seeded orders.

The data deliberately covers all three client states, a delisted instrument that
still has orders pointing at it, all four order statuses, both product types, an
intraday **short** (negative quantity), and an intraday position squared off to
exactly zero.

---

## `infra/postgres/` — unattended build (SEC3-95, for Sprint 6)

```bash
cd infra/postgres && docker compose up -d
```

Brings up a Postgres that has already applied every migration and loaded every
seed file, with nothing to run afterwards. `migrations/` and `seed/` are
*mounted* from the repository rather than copied into an image, so there is one
copy of the schema in this project and the container can never be built from a
stale one. The healthcheck only reports healthy once the schema exists, so
`depends_on: service_healthy` means "the database is ready", not "the port is
open".

> **Not executed.** The machine this was written on has no Docker. The compose
> file and init script are unverified *as Docker*. What has been verified is
> everything inside them: the init script was run verbatim against a local
> PostgreSQL, built a database that passes all 54 checks, and wrote a
> `schema_migrations` ledger that `apply_db.py` then recognised as up to date.

---

## Design notes

**Money is exact.** `DECIMAL(18,2)` for cash, `DECIMAL(18,4)` for prices. A
check asserts there is no `real`, `double precision` or `money` column anywhere.

**Idempotency is a database constraint,** not a read followed by a write, so two
concurrent identical requests cannot both pass.

**Optimistic concurrency** on `bank_account.version`: read the version, then
`UPDATE ... WHERE version = <the value you read>`. A rowcount of 0 means you
lost the race.

**Nothing is deleted.** A client is `CLOSED`, an instrument is
`is_active = FALSE`. Both are enforced by triggers, and `CLOSED` is one-way.

**Settlement lives in the application layer,** by design — the database makes
the routing decision unambiguous (`orders.product_type`) and keeps the two books
structurally distinct, but does not itself move fills into them.

Full detail, including the two portfolio tables and what changed from the
original ERD: **[docs/erd.md](docs/erd.md)**.
