#!/usr/bin/env python3
"""
apply_db.py - the apply command for the Team 1 trade database (SEC3-95).

    python scripts/apply_db.py                # create db if needed, migrate, seed
    python scripts/apply_db.py --reset        # drop the database and rebuild from scratch
    python scripts/apply_db.py --reseed       # reload seed data over the existing schema
    python scripts/apply_db.py --migrations-only
    python scripts/apply_db.py --seed-only
    python scripts/apply_db.py --dry-run      # say what would happen, touch nothing

What it does, in order:

  1. Creates the database if it does not exist, so a fresh machine needs no
     manual setup step.
  2. Applies every file in migrations/ in FILENAME ORDER through
     `psql -v ON_ERROR_STOP=1`, so a migration that errors stops the run
     instead of reporting an error, carrying on and exiting zero.
  3. Records each applied file in schema_migrations with a sha256, so the
     command is safe to run often and so a migration edited after it was
     applied is caught rather than silently ignored.
  4. Loads every data file in seed/ in filename order, inside ONE
     transaction. A row that cannot be mapped to its table FAILS THE LOAD;
     it is never skipped.
  5. Resyncs every SERIAL sequence past the seeded ids, so the first insert
     from the application does not collide with seed data.

Standard library only. Every setting has a default; nothing has to be
exported by hand first.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_config import (  # noqa: E402
    MIGRATIONS_DIR,
    SEED_DIR,
    DbConfig,
    DbError,
    add_connection_args,
    quote_ident,
    quote_literal,
)

PROTECTED_DBS = {"postgres", "template0", "template1"}
# Extensions we refuse to silently ignore if they turn up in seed/.
UNSUPPORTED_SEED_EXTS = {".sql", ".tsv", ".json", ".jsonl", ".xlsx", ".parquet"}

# Defined once, in migrations/009_maintenance.sql, so that this script and
# infra/postgres/initdb/ cannot drift apart.
RESYNC_SEQUENCES_SQL = "SELECT count(*) AS sequences_resynced FROM fn_resync_sequences();"


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------

def say(msg=""):
    print(msg, flush=True)


def step(msg):
    say("  -> " + msg)


def head(msg):
    say("")
    say("== " + msg + " " + "=" * max(0, 66 - len(msg)))


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations():
    """Every migrations/*.sql, in filename order. The number IS the order."""
    if not MIGRATIONS_DIR.is_dir():
        raise DbError("migrations/ directory not found at " + str(MIGRATIONS_DIR))
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    if not files:
        raise DbError("migrations/ contains no .sql files")

    bad = [f.name for f in files if not re.match(r"^\d{3}_", f.name)]
    if bad:
        raise DbError(
            "migration files must start with a three-digit number (001_, 002_, ...); "
            "these do not: " + ", ".join(bad)
        )
    return files


def table_for_seed_file(path: Path) -> str:
    """seed/050_orders.csv -> orders. The numeric prefix is load order only."""
    stem = path.stem
    match = re.match(r"^\d+[_-](?P<table>.+)$", stem)
    if not match:
        raise DbError(
            "seed file " + path.name + " must be named <number>_<table>.csv, "
            "e.g. 050_orders.csv - the number is the load order"
        )
    return match.group("table")


def discover_seeds():
    """Every seed/*.csv, in filename order. Refuses to silently ignore data files."""
    if not SEED_DIR.is_dir():
        return []

    stray = sorted(
        p.name for p in SEED_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in UNSUPPORTED_SEED_EXTS
    )
    if stray:
        raise DbError(
            "seed/ contains data files this loader does not handle: "
            + ", ".join(stray)
            + "\nThe seed format is CSV. Refusing to run rather than skip them silently."
        )
    return sorted(SEED_DIR.glob("*.csv"), key=lambda p: p.name)


# ---------------------------------------------------------------------------
# database lifecycle
# ---------------------------------------------------------------------------

def drop_database(cfg: DbConfig):
    if cfg.dbname in PROTECTED_DBS:
        raise DbError("refusing to drop the protected database " + repr(cfg.dbname))
    step("terminating open connections to " + cfg.dbname)
    cfg.run_or_die(
        "terminating connections",
        dbname="postgres",
        sql=(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = " + quote_literal(cfg.dbname) + " AND pid <> pg_backend_pid();"
        ),
    )
    step("dropping database " + cfg.dbname)
    cfg.run_or_die(
        "dropping the database",
        dbname="postgres",
        sql="DROP DATABASE IF EXISTS " + quote_ident(cfg.dbname) + ";",
    )


def create_database_if_missing(cfg: DbConfig):
    if cfg.database_exists():
        step("database " + cfg.dbname + " already exists")
        return False
    step("creating database " + cfg.dbname)
    cfg.run_or_die(
        "creating the database",
        dbname="postgres",
        sql="CREATE DATABASE " + quote_ident(cfg.dbname) + ";",
    )
    return True


# ---------------------------------------------------------------------------
# migrations
# ---------------------------------------------------------------------------

def bootstrap_ledger(cfg: DbConfig, files):
    ledger = next((f for f in files if f.name.startswith("000_")), None)
    if ledger is None:
        raise DbError(
            "migrations/000_*.sql is missing. It creates the schema_migrations "
            "ledger this command needs before it can track anything."
        )
    cfg.run_or_die("bootstrapping schema_migrations", file=ledger)


def read_ledger(cfg: DbConfig):
    rows = cfg.rows("SELECT filename, checksum FROM schema_migrations ORDER BY filename;")
    return {r[0]: r[1] for r in rows if len(r) >= 2}


def apply_migrations(cfg: DbConfig, allow_modified=False, dry_run=False):
    files = discover_migrations()
    say("  " + str(len(files)) + " migration file(s) in " + str(MIGRATIONS_DIR))

    if dry_run:
        for f in files:
            step("would apply " + f.name)
        return {"applied": 0, "skipped": 0, "total": len(files)}

    bootstrap_ledger(cfg, files)
    ledger = read_ledger(cfg)

    applied = skipped = 0
    for path in files:
        digest = sha256_of(path)
        recorded = ledger.get(path.name)

        if recorded == digest:
            step("skip    " + path.name + "  (already applied)")
            skipped += 1
            continue

        if recorded is not None and recorded != digest:
            msg = (
                path.name + " was EDITED after it was applied to this database.\n"
                "    recorded sha256: " + recorded + "\n"
                "    on-disk  sha256: " + digest + "\n"
                "  Once a migration has been applied, change the schema by adding a new\n"
                "  numbered file (009_, 010_, ...) instead of editing this one - your\n"
                "  teammates already have databases with data in them.\n"
                "  To rebuild this database from scratch instead:  --reset\n"
                "  To record the new contents without re-running:  --allow-modified"
            )
            if not allow_modified:
                raise DbError(msg)
            step("WARNING " + path.name + " was edited after apply; re-recording checksum")
            cfg.run_or_die(
                "updating the ledger for " + path.name,
                sql=(
                    "UPDATE schema_migrations SET checksum = " + quote_literal(digest)
                    + ", applied_at = now() WHERE filename = " + quote_literal(path.name) + ";"
                ),
            )
            skipped += 1
            continue

        step("apply   " + path.name)
        cfg.run_or_die("migration " + path.name, file=path, verbose_errors=True)
        cfg.run_or_die(
            "recording " + path.name + " in schema_migrations",
            sql=(
                "INSERT INTO schema_migrations (filename, checksum) VALUES ("
                + quote_literal(path.name) + ", " + quote_literal(digest) + ") "
                "ON CONFLICT (filename) DO UPDATE SET checksum = EXCLUDED.checksum, "
                "applied_at = now();"
            ),
        )
        applied += 1

    return {"applied": applied, "skipped": skipped, "total": len(files)}


# ---------------------------------------------------------------------------
# seed loading
# ---------------------------------------------------------------------------

def table_columns(cfg: DbConfig, table: str):
    rows = cfg.rows(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = " + quote_literal(table)
        + " ORDER BY ordinal_position;"
    )
    return [r[0] for r in rows]


def validate_seed_file(cfg: DbConfig, path: Path):
    """
    Check the file maps cleanly onto its table BEFORE any of it is loaded.

    SEC3-95: "Fail the load rather than skipping a row that cannot be mapped,
    or a mapping bug becomes missing data nobody notices."
    """
    table = table_for_seed_file(path)

    columns = table_columns(cfg, table)
    if not columns:
        raise DbError(
            "seed file " + path.name + " targets table " + repr(table)
            + ", which does not exist in this database."
        )

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise DbError("seed file " + path.name + " is empty (no header row).")

        header = [h.strip() for h in header]
        if not header or any(h == "" for h in header):
            raise DbError("seed file " + path.name + " has a blank column name in its header.")

        unknown = [h for h in header if h not in columns]
        if unknown:
            raise DbError(
                "seed file " + path.name + " has column(s) not present on table "
                + table + ": " + ", ".join(unknown)
                + "\n  table " + table + " has: " + ", ".join(columns)
            )

        duplicates = sorted({h for h in header if header.count(h) > 1})
        if duplicates:
            raise DbError(
                "seed file " + path.name + " repeats column(s): " + ", ".join(duplicates)
            )

        width = len(header)
        rowcount = 0
        for lineno, row in enumerate(reader, start=2):
            if not row or (len(row) == 1 and row[0].strip() == ""):
                raise DbError(
                    "seed file " + path.name + " line " + str(lineno)
                    + ": blank line. Remove it - a blank row cannot be mapped to "
                    + table + " and will not be skipped."
                )
            if len(row) != width:
                raise DbError(
                    "seed file " + path.name + " line " + str(lineno)
                    + ": expected " + str(width) + " field(s) to match the header, found "
                    + str(len(row)) + ".\n  header: " + ",".join(header)
                    + "\n  row:    " + ",".join(row)
                )
            rowcount += 1

    if rowcount == 0:
        raise DbError("seed file " + path.name + " has a header but no data rows.")

    return {"table": table, "header": header, "rows": rowcount}


def load_seeds(cfg: DbConfig, reseed=False, dry_run=False):
    files = discover_seeds()
    if not files:
        say("  seed/ has no .csv files; nothing to load")
        return {"loaded": 0, "skipped": 0, "rows": 0}

    say("  " + str(len(files)) + " seed file(s) in " + str(SEED_DIR))

    # Validate every file up front so we never load half a dataset.
    plans = []
    for path in files:
        plan = validate_seed_file(cfg, path)
        plan["path"] = path
        plans.append(plan)
        step("check   " + path.name + "  -> " + plan["table"]
             + " (" + str(plan["rows"]) + " rows, " + str(len(plan["header"])) + " cols)")

    if not reseed:
        keep = []
        for plan in plans:
            count = cfg.scalar("SELECT count(*) FROM " + quote_ident(plan["table"]) + ";")
            if count != "0":
                step("skip    " + plan["path"].name + "  (" + plan["table"]
                     + " already has " + count + " row(s); use --reseed to reload)")
            else:
                keep.append(plan)
        skipped = len(plans) - len(keep)
        plans = keep
    else:
        skipped = 0

    if not plans:
        say("  nothing to load")
        # Sequences may still be out of step if the schema was rebuilt around
        # existing data, so resync anyway - it is cheap and idempotent.
        if not dry_run:
            cfg.run_or_die("resyncing sequences", sql=RESYNC_SEQUENCES_SQL)
        return {"loaded": 0, "skipped": skipped, "rows": 0}

    script = build_seed_script(plans, reseed=reseed)

    if dry_run:
        say("")
        say("  --- seed script that would run ---")
        for line in script.splitlines():
            say("  " + line)
        return {"loaded": 0, "skipped": skipped, "rows": sum(p["rows"] for p in plans)}

    # One transaction for the whole seed load: with ON_ERROR_STOP=1 a bad row
    # aborts the script, which rolls the whole load back. No partial datasets.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sql", delete=False, encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(script)
        script_path = Path(fh.name)

    try:
        for plan in plans:
            step("load    " + plan["path"].name + "  -> " + plan["table"]
                 + " (" + str(plan["rows"]) + " rows)")
        cfg.run_or_die("seed load", file=script_path, verbose_errors=True)
    finally:
        script_path.unlink(missing_ok=True)

    return {
        "loaded": len(plans),
        "skipped": skipped,
        "rows": sum(p["rows"] for p in plans),
    }


def build_seed_script(plans, reseed):
    """One psql script: truncate (if reseeding), \\copy each file, resync sequences."""
    lines = [
        "-- generated by scripts/apply_db.py; not checked in",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
    ]

    if reseed:
        # One TRUNCATE for all targets so FK order does not matter. CASCADE is
        # scoped to these tables' dependents, which are all seed targets too.
        targets = ", ".join(quote_ident(p["table"]) for p in plans)
        lines.append("TRUNCATE TABLE " + targets + " RESTART IDENTITY CASCADE;")

    for plan in plans:
        cols = ", ".join(quote_ident(c) for c in plan["header"])
        # Forward slashes work in psql on Windows too.
        location = plan["path"].resolve().as_posix()
        lines.append(
            "\\copy " + quote_ident(plan["table"]) + " (" + cols + ") FROM '"
            + location + "' WITH (FORMAT csv, HEADER true)"
        )

    lines.append(RESYNC_SEQUENCES_SQL.strip())
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="apply_db.py",
        description="Build the Team 1 trade database: apply migrations/ then load seed/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Runs with no arguments on a machine that has psql and a local Postgres.\n"
            "Override any setting with a flag, a PG* environment variable, or a .env file."
        ),
    )
    add_connection_args(p)
    g = p.add_argument_group("what to do")
    g.add_argument("--reset", action="store_true",
                   help="drop the database and rebuild it from migrations/ and seed/")
    g.add_argument("--reseed", action="store_true",
                   help="truncate the seeded tables and load seed/ again")
    g.add_argument("--migrations-only", action="store_true", help="apply migrations, skip seed/")
    g.add_argument("--seed-only", action="store_true", help="load seed/, skip migrations")
    g.add_argument("--allow-modified", action="store_true",
                   help="accept a migration whose contents changed after it was applied")
    g.add_argument("--dry-run", action="store_true",
                   help="report what would happen and change nothing")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.migrations_only and args.seed_only:
        say("error: --migrations-only and --seed-only contradict each other")
        return 2

    started = time.time()

    try:
        cfg = DbConfig.resolve(args)
    except DbError as exc:
        say("error: " + str(exc))
        return 1

    head("Target")
    say("  " + cfg.describe())
    say("  psql: " + cfg.psql)
    if args.dry_run:
        say("  DRY RUN - nothing will be changed")

    try:
        reachable, detail = cfg.server_reachable()
        if not reachable:
            raise DbError(
                "cannot reach the PostgreSQL server at " + cfg.host + ":" + str(cfg.port)
                + " as user " + cfg.user + ".\n" + detail
                + "\nIs the server running? Check the host/port/user/password "
                "(flags, PG* env vars, or .env)."
            )

        if args.reset and not args.dry_run:
            head("Reset")
            drop_database(cfg)

        if not args.seed_only or args.reset:
            head("Database")
            if args.dry_run:
                exists = cfg.database_exists()
                step(("database " + cfg.dbname + " already exists") if exists
                     else ("would create database " + cfg.dbname))
                if not exists:
                    say("  (dry run cannot inspect a database that does not exist yet)")
                    say("")
                    say("Dry run finished.")
                    return 0
            else:
                create_database_if_missing(cfg)

        mig = {"applied": 0, "skipped": 0, "total": 0}
        if not args.seed_only:
            head("Migrations")
            mig = apply_migrations(
                cfg, allow_modified=args.allow_modified, dry_run=args.dry_run
            )

        seed = {"loaded": 0, "skipped": 0, "rows": 0}
        if not args.migrations_only:
            head("Seed data")
            seed = load_seeds(cfg, reseed=args.reseed or args.reset, dry_run=args.dry_run)

    except DbError as exc:
        say("")
        say("FAILED: " + str(exc))
        say("")
        say("Nothing further was applied. Fix the problem and run the command again.")
        return 1
    except KeyboardInterrupt:
        say("")
        say("Interrupted.")
        return 130

    head("Summary")
    say("  migrations : " + str(mig["applied"]) + " applied, "
        + str(mig["skipped"]) + " already up to date, " + str(mig["total"]) + " total")
    say("  seed       : " + str(seed["loaded"]) + " file(s) loaded, "
        + str(seed["rows"]) + " row(s), " + str(seed["skipped"]) + " file(s) skipped")
    say("  elapsed    : " + format(time.time() - started, ".1f") + "s")
    say("")
    say("Database ready: " + cfg.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
