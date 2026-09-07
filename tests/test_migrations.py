from __future__ import annotations

import csv
import re

import pytest

import apply_db
import make_seed
from db_config import MIGRATIONS_DIR, SEED_DIR, DbError, quote_ident, quote_literal

from dbenv import SCRATCH_DB, TEST_DB, drop_database

MIGRATIONS = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)

EXPECTED_TABLES = {
    "auth", "bank_account", "clients", "instruments", "order_history", "orders",
    "portfolio_holding", "portfolio_positions", "schema_migrations",
}


def test_there_are_migrations_to_run():
    assert MIGRATIONS, "migrations/ is empty"


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_every_migration_is_numbered(path):
    assert re.match(r"^\d{3}_[a-z0-9_]+\.sql$", path.name)


def test_migration_numbers_are_unique():
    numbers = [p.name[:3] for p in MIGRATIONS]
    assert len(set(numbers)) == len(numbers), "two migrations share a number"


def test_the_ledger_migration_comes_first():
    assert MIGRATIONS[0].name.startswith("000_")


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_every_migration_is_one_transaction(path):
    body = path.read_text(encoding="utf-8").strip()
    assert body.startswith("BEGIN;"), path.name + " does not open a transaction"
    assert body.endswith("COMMIT;"), path.name + " does not commit"


def test_migrations_apply_to_an_empty_database(scratch_db):
    assert apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"]) == 0
    found = {r[0] for r in scratch_db.rows(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE';"
    )}
    assert EXPECTED_TABLES <= found, "missing: " + str(sorted(EXPECTED_TABLES - found))


def test_migrations_create_no_unexpected_tables(scratch_db):
    apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"])
    found = {r[0] for r in scratch_db.rows(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE';"
    )}
    assert found == EXPECTED_TABLES, "unexpected: " + str(sorted(found - EXPECTED_TABLES))


def test_applying_twice_applies_nothing_the_second_time(scratch_db, capsys):
    apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"])
    capsys.readouterr()
    assert apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"]) == 0
    output = capsys.readouterr().out
    assert "0 applied" in output, output


def test_every_migration_is_recorded_in_the_ledger(scratch_db):
    apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"])
    recorded = {r[0] for r in scratch_db.rows("SELECT filename FROM schema_migrations;")}
    assert recorded == {p.name for p in MIGRATIONS}


def test_an_edited_migration_is_refused(scratch_db, capsys):
    apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"])
    scratch_db.run_or_die(
        "tampering with the ledger",
        sql="UPDATE schema_migrations SET checksum = repeat('0', 64) "
            "WHERE filename = " + quote_literal(MIGRATIONS[-1].name) + ";",
    )
    capsys.readouterr()
    assert apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"]) == 1
    output = capsys.readouterr().out
    assert "EDITED" in output
    assert MIGRATIONS[-1].name in output


def test_allow_modified_re_records_the_checksum(scratch_db):
    apply_db.main(["--dbname", SCRATCH_DB, "--migrations-only"])
    scratch_db.run_or_die(
        "tampering with the ledger",
        sql="UPDATE schema_migrations SET checksum = repeat('0', 64) "
            "WHERE filename = " + quote_literal(MIGRATIONS[-1].name) + ";",
    )
    assert apply_db.main(
        ["--dbname", SCRATCH_DB, "--migrations-only", "--allow-modified"]) == 0
    stored = scratch_db.scalar(
        "SELECT checksum FROM schema_migrations WHERE filename = "
        + quote_literal(MIGRATIONS[-1].name) + ";")
    assert stored == apply_db.sha256_of(MIGRATIONS[-1])


def test_a_failing_migration_leaves_nothing_behind(scratch_db, tmp_path):
    broken = tmp_path / "999_broken.sql"
    broken.write_text(
        "BEGIN;\n"
        "CREATE TABLE should_not_survive (id INT);\n"
        "CREATE TABLE this_one_is_not_valid (id NOT A TYPE);\n"
        "COMMIT;\n",
        encoding="utf-8",
    )
    proc = scratch_db.run(file=broken)
    assert proc.returncode != 0, "the broken migration was accepted"
    assert scratch_db.scalar(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='should_not_survive';") == "0"


def test_dry_run_creates_nothing(server, capsys):
    drop_database(server, SCRATCH_DB)
    assert apply_db.main(["--dbname", SCRATCH_DB, "--dry-run"]) == 0
    assert server.scalar(
        "SELECT count(*) FROM pg_database WHERE datname = "
        + quote_literal(SCRATCH_DB) + ";") == "0"


def test_seed_files_are_what_make_seed_generates():
    assert make_seed.main(["--check"]) == 0


def test_seed_directory_holds_no_stray_files():
    expected = {name for name, _ in make_seed.BUILDERS}
    assert make_seed.strays(expected) == []


@pytest.mark.parametrize(
    "name", [name for name, _ in make_seed.BUILDERS])
def test_every_seed_file_targets_a_real_table(built_db, name):
    table = apply_db.table_for_seed_file(SEED_DIR / name)
    assert apply_db.table_columns(built_db, table), table + " does not exist"


def test_seed_row_counts_match_the_csv_files(built_db):
    for name, _ in make_seed.BUILDERS:
        path = SEED_DIR / name
        table = apply_db.table_for_seed_file(path)
        with path.open(encoding="utf-8-sig", newline="") as fh:
            expected = sum(1 for _ in csv.reader(fh)) - 1
        actual = int(built_db.scalar("SELECT count(*) FROM " + quote_ident(table) + ";"))
        assert actual == expected, table + " has " + str(actual) + " rows, " \
            + name + " supplies " + str(expected)


def test_a_seed_file_with_an_unknown_column_is_rejected(built_db, tmp_path):
    bad = tmp_path / "050_orders.csv"
    bad.write_text("order_id,not_a_real_column\n1,x\n", encoding="utf-8")
    with pytest.raises(DbError) as caught:
        apply_db.validate_seed_file(built_db, bad)
    assert "not_a_real_column" in str(caught.value)


def test_a_seed_file_with_a_short_row_is_rejected(built_db, tmp_path):
    bad = tmp_path / "040_instruments.csv"
    bad.write_text("instrument_id,instrument_name\nRELIANCE\n", encoding="utf-8")
    with pytest.raises(DbError) as caught:
        apply_db.validate_seed_file(built_db, bad)
    assert "line 2" in str(caught.value)


def test_reseeding_is_stable(built_db, table_counts):
    before = table_counts(built_db)
    assert apply_db.main(["--dbname", TEST_DB, "--reseed"]) == 0
    assert table_counts(built_db) == before


def test_the_bank_account_foreign_key_is_deferrable(built_db):
    definition = built_db.scalar(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'fk_bank_account_client';")
    assert definition, "fk_bank_account_client is missing"
    assert "DEFERRABLE" in definition.upper()


def test_the_seed_cannot_load_outside_one_transaction(built_db):
    first = SEED_DIR / make_seed.BUILDERS[0][0]
    table = apply_db.table_for_seed_file(first)
    header = first.read_text(encoding="utf-8").splitlines()[0]
    try:
        proc = built_db.run(
            script="BEGIN;\nTRUNCATE TABLE " + quote_ident(table) + " CASCADE;\n"
                   "COMMIT;\n"
                   "\\copy " + quote_ident(table) + " (" + header + ") FROM '"
                   + first.resolve().as_posix() + "' WITH (FORMAT csv, HEADER true)\n"
        )
        assert proc.returncode != 0, (
            "loading " + table + " in its own transaction succeeded; the deferrable "
            "foreign key that makes the seed order work is gone, and the docker init "
            "script no longer needs its single transaction"
        )
        assert "fk_bank_account_client" in (proc.stderr or ""), (
            "the load failed, but not on the deferred foreign key: "
            + (proc.stderr or "").strip()[:200]
        )
    finally:
        assert apply_db.main(["--dbname", TEST_DB, "--reseed"]) == 0
