#!/usr/bin/env python3
"""
verify_db.py - assert the built database actually meets the SEC3-94 / SEC3-95
acceptance criteria, rather than assuming it does.

    python scripts/verify_db.py           # run every check
    python scripts/verify_db.py -v        # also print each check that passed
    python scripts/verify_db.py --only C  # run one section (A, B, C or D)

Exit code is 0 only if every check passes.

Every check that writes anything does so inside BEGIN ... ROLLBACK, or is a
statement that is EXPECTED to fail, so running this leaves the database exactly
as it found it.

Sections:
    A  structure      - tables, columns, exact money types, migration ledger
    B  constraints    - FKs, CHECKs, the idempotency UNIQUE, the holding/
                        positions difference
    C  behaviour      - what the database actually rejects and accepts:
                        idempotency, terminal states, account lifecycle,
                        optimistic concurrency, sequence resync
    D  data           - the seeded data is internally consistent, and the two
                        portfolio books agree with a replay of the orders
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_config import DbConfig, DbError, add_connection_args, quote_literal  # noqa: E402
from make_seed import apply_fill, price  # noqa: E402

SQLSTATE_RE = re.compile(r"ERROR:\s+([0-9A-Z]{5}):")

EXPECTED_TABLES = [
    "auth", "bank_account", "clients", "in_progress", "instruments", "orders",
    "portfolio_holding", "portfolio_positions", "schema_migrations",
    "transaction_failures", "transaction_success",
]

# Columns that hold money and must therefore be exact (numeric), never float.
MONEY_COLUMNS = [
    ("bank_account", "balance"),
    ("orders", "price_per_unit"),
    ("transaction_success", "value"),
    ("transaction_failures", "value"),
    ("portfolio_holding", "avg_price"),
    ("portfolio_positions", "avg_price"),
]

INEXACT_TYPES = {"real", "double precision", "float", "float4", "float8", "money"}


class CheckFailed(AssertionError):
    """A single verification check did not hold."""


# ---------------------------------------------------------------------------
# assertion helpers
# ---------------------------------------------------------------------------

def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def equal(actual, expected, what):
    if str(actual) != str(expected):
        raise CheckFailed(what + ": expected " + repr(expected) + ", got " + repr(actual))


def sqlstate_of(proc):
    match = SQLSTATE_RE.search(proc.stderr or "")
    return match.group(1) if match else None


class Verifier:
    def __init__(self, cfg):
        self.cfg = cfg

    # -- raw access ----------------------------------------------------

    def scalar(self, sql):
        return self.cfg.scalar(sql)

    def rows(self, sql):
        return self.cfg.rows(sql)

    def count(self, sql):
        return int(self.scalar(sql) or "0")

    # -- expectation helpers -------------------------------------------

    def expect_rejected(self, sql, sqlstate, what):
        """
        The statement must FAIL, with the given SQLSTATE.

        Wrapped in BEGIN/ROLLBACK so that a check which FAILS still leaves the
        database untouched. Without this, a statement that was supposed to be
        rejected but was not would commit, and every later check would then be
        reasoning about polluted data.
        """
        proc = self.cfg.run(script=rollback_script(sql), verbose_errors=True)
        if proc.returncode == 0:
            raise CheckFailed(what + ": the database ACCEPTED it, but it should be rejected")
        actual = sqlstate_of(proc)
        if actual != sqlstate:
            raise CheckFailed(
                what + ": expected SQLSTATE " + sqlstate + ", got "
                + (actual or "none") + "\n      " + first_error_line(proc)
            )

    def expect_accepted(self, script, what):
        """The script must SUCCEED. It is responsible for its own ROLLBACK."""
        proc = self.cfg.run(script=script, verbose_errors=True)
        if proc.returncode != 0:
            raise CheckFailed(
                what + ": the database REJECTED it, but it should be accepted"
                + "\n      " + first_error_line(proc)
            )
        return proc.stdout


def first_error_line(proc):
    """The most useful single line of psql output for a failure message."""
    output = (proc.stderr or "") + (proc.stdout or "")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines:
        if "ERROR" in line:
            return line
    return lines[0] if lines else "(no output)"


def rollback_script(body):
    """Wrap statements so nothing they do survives the check."""
    return "BEGIN;\n" + body.strip() + "\nROLLBACK;\n"


# ===========================================================================
# A. STRUCTURE
# ===========================================================================

def a01_tables_exist(v):
    found = [r[0] for r in v.rows(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;"
    )]
    missing = [t for t in EXPECTED_TABLES if t not in found]
    require(not missing, "missing table(s): " + ", ".join(missing))


def a02_portfolio_positions_exists(v):
    require(
        v.count("SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='portfolio_positions';") == 1,
        "portfolio_positions table does not exist",
    )


def a03_positions_mirrors_holding(v):
    """
    portfolio_positions must be a structural copy of portfolio_holding: same
    columns, same types, same nullability - only the surrogate key differs.
    """
    def shape(table, pk):
        return {
            r[0]: (r[1], r[2])
            for r in v.rows(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=" + quote_literal(table)
                + " AND column_name <> " + quote_literal(pk) + " ORDER BY column_name;"
            )
        }

    holding = shape("portfolio_holding", "holding_id")
    positions = shape("portfolio_positions", "position_id")

    require(holding, "portfolio_holding has no columns")
    only_h = sorted(set(holding) - set(positions))
    only_p = sorted(set(positions) - set(holding))
    require(not only_h, "portfolio_positions is missing column(s): " + ", ".join(only_h))
    require(not only_p, "portfolio_positions has extra column(s): " + ", ".join(only_p))

    for col in sorted(holding):
        equal(positions[col], holding[col], "portfolio_positions." + col + " type/nullability")


def a04_version_column(v):
    dtype = v.scalar(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='bank_account' AND column_name='version';"
    )
    require(dtype == "integer", "bank_account.version must be an integer, got " + repr(dtype))


def a05_product_type_column(v):
    dtype = v.scalar(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='product_type';"
    )
    require(dtype == "character varying",
            "orders.product_type missing or wrong type: " + repr(dtype))

    nullable = v.scalar(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='product_type';"
    )
    equal(nullable, "NO", "orders.product_type nullability")

    default = v.scalar(
        "SELECT coalesce(column_default, '') FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='product_type';"
    )
    require(
        default == "",
        "orders.product_type must have NO default (" + repr(default) + "): a default would "
        "let a caller that forgot to set it silently book an intraday fill into holdings",
    )


def a06_money_is_exact(v):
    for table, column in MONEY_COLUMNS:
        dtype = v.scalar(
            "SELECT data_type FROM information_schema.columns WHERE table_name="
            + quote_literal(table) + " AND column_name=" + quote_literal(column) + ";"
        )
        require(dtype, table + "." + column + " does not exist")
        require(
            dtype == "numeric",
            table + "." + column + " must be numeric/DECIMAL for exact money, got " + repr(dtype),
        )


def a07_no_inexact_numeric_anywhere(v):
    bad = v.rows(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND data_type IN "
        "('real','double precision','money') ORDER BY table_name, column_name;"
    )
    require(
        not bad,
        "float/money columns found (money must be exact): "
        + ", ".join(r[0] + "." + r[1] + " " + r[2] for r in bad),
    )


def a08_every_migration_recorded(v):
    from db_config import MIGRATIONS_DIR

    on_disk = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    recorded = sorted(r[0] for r in v.rows("SELECT filename FROM schema_migrations;"))
    missing = [f for f in on_disk if f not in recorded]
    require(
        not missing,
        "migration file(s) on disk but not recorded as applied: " + ", ".join(missing)
        + "\n  If you built this database by running psql over migrations/ by hand, the"
        "\n  ledger is empty and `apply_db.py` would try to re-apply everything."
        "\n  Rebuild through the apply command instead:  python scripts/apply_db.py --reset",
    )


def a09_numbered_in_order(v):
    from db_config import MIGRATIONS_DIR

    names = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    require(names, "migrations/ is empty")
    for name in names:
        require(
            re.match(r"^\d{3}_[a-z0-9_]+\.sql$", name),
            "migration " + name + " does not match NNN_snake_case.sql",
        )
    numbers = [int(n[:3]) for n in names]
    require(len(set(numbers)) == len(numbers),
            "two migrations share a number: " + ", ".join(names))


# ===========================================================================
# B. CONSTRAINTS
# ===========================================================================

def b01_at_least_three_checks(v):
    """SEC3-94: 'At least three check constraints exist.'"""
    n = v.count(
        "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE c.contype='c' AND n.nspname='public' AND c.conname LIKE 'chk_%';"
    )
    require(n >= 3, "expected at least 3 named CHECK constraints, found " + str(n))


def b02_account_state_check(v):
    """SEC3-94: 'one of them covering account state.'"""
    definition = v.scalar(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "WHERE c.conname = 'chk_clients_status';"
    )
    require(definition, "chk_clients_status (the account-state CHECK) does not exist")
    for state in ("ACTIVE", "SUSPENDED", "CLOSED"):
        require(state in definition,
                "chk_clients_status does not mention " + state + ": " + definition)


def b03_idempotency_unique(v):
    definition = v.scalar(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "WHERE c.conname = 'uq_orders_idempotency_key' AND c.contype = 'u';"
    )
    require(
        definition and "idempotency_key" in definition,
        "UNIQUE constraint on orders.idempotency_key is missing - idempotency must be "
        "enforced by the database, not a read-then-write",
    )


def b04_foreign_keys_present(v):
    expected = {
        ("clients", "bank_account"),
        ("auth", "clients"),
        ("orders", "clients"),
        ("orders", "instruments"),
        # in_progress reaches instruments through the composite FK to orders,
        # not with a plain FK of its own - see migrations/006.
        ("in_progress", "orders"),
        ("transaction_success", "orders"),
        ("transaction_failures", "orders"),
        ("portfolio_holding", "clients"),
        ("portfolio_holding", "instruments"),
        ("portfolio_positions", "clients"),
        ("portfolio_positions", "instruments"),
    }
    found = {
        (r[0], r[1])
        for r in v.rows(
            "SELECT src.relname, tgt.relname FROM pg_constraint c "
            "JOIN pg_class src ON src.oid = c.conrelid "
            "JOIN pg_class tgt ON tgt.oid = c.confrelid "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE c.contype = 'f' AND n.nspname = 'public';"
        )
    }
    missing = sorted(expected - found)
    require(
        not missing,
        "missing foreign key(s): " + ", ".join(a + " -> " + b for a, b in missing),
    )


def b05_holding_forbids_negative(v):
    definition = v.scalar(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'chk_portfolio_holding_quantity_non_negative';"
    )
    require(definition, "portfolio_holding is missing its non-negative quantity CHECK")
    require("quantity" in definition, "unexpected definition: " + definition)


def b06_positions_allows_negative(v):
    """The one deliberate difference between the two portfolio tables."""
    found = v.rows(
        "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relname = 'portfolio_positions' AND c.contype = 'c';"
    )
    offending = [r[0] for r in found if "quantity" in (r[1] if len(r) > 1 else "")]
    require(
        not offending,
        "portfolio_positions must NOT constrain quantity (intraday shorts are negative), "
        "but found: " + ", ".join(offending),
    )


def b07_unique_portfolio_keys(v):
    for table, conname in (
        ("portfolio_holding", "uq_portfolio_holding_client_instrument"),
        ("portfolio_positions", "uq_portfolio_positions_client_instrument"),
    ):
        definition = v.scalar(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname="
            + quote_literal(conname) + ";"
        )
        require(definition, table + " is missing UNIQUE (client_id, instrument_id)")


def b08_terminal_tables_unique_per_order(v):
    for table in ("transaction_success", "transaction_failures"):
        n = v.count(
            "SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
            "WHERE t.relname=" + quote_literal(table) + " AND c.contype='u' "
            "AND pg_get_constraintdef(c.oid) LIKE '%order_id%';"
        )
        require(n >= 1, table + " must have a UNIQUE constraint on order_id")


# ===========================================================================
# C. BEHAVIOUR
# ===========================================================================

_NEW_ORDER = (
    "INSERT INTO orders (instrument_id, client_id, price_per_unit, type, "
    "product_type, quantity, exchange, idempotency_key) VALUES "
)


def c01_duplicate_idempotency_key_rejected(v):
    """Sprint 6 depends on this unique violation being DETECTABLE (SQLSTATE 23505)."""
    existing = v.scalar("SELECT idempotency_key FROM orders ORDER BY order_id LIMIT 1;")
    require(existing, "no seeded orders to test against")
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 100.0000, 'BUY', 'DELIVERY', 1, 'NSE', "
        + quote_literal(existing) + ");",
        "23505",
        "a second order reusing an existing idempotency_key",
    )


def c02_bad_product_type_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 100.0000, 'BUY', 'SWING', 1, 'NSE', 'verify-bad-product');",
        "23514",
        "an order with product_type = 'SWING'",
    )


def c03_bad_side_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 100.0000, 'HOLD', 'DELIVERY', 1, 'NSE', 'verify-bad-side');",
        "23514",
        "an order with type = 'HOLD'",
    )


def c04_zero_quantity_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 100.0000, 'BUY', 'DELIVERY', 0, 'NSE', 'verify-zero-qty');",
        "23514",
        "an order with quantity = 0",
    )


def c05_missing_client_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 99999, 100.0000, 'BUY', 'DELIVERY', 1, 'NSE', 'verify-no-client');",
        "23503",
        "an order for a client_id that does not exist",
    )


def c06_bad_client_status_rejected(v):
    v.expect_rejected(
        "UPDATE clients SET status = 'DORMANT' WHERE client_id = 1;",
        "23514",
        "setting a client to an undefined status",
    )


def c07_suspension_is_reversible(v):
    v.expect_accepted(
        rollback_script(
            "UPDATE clients SET status = 'SUSPENDED' WHERE client_id = 1;\n"
            "UPDATE clients SET status = 'ACTIVE'    WHERE client_id = 1;\n"
            "UPDATE clients SET status = 'SUSPENDED' WHERE client_id = 1;"
        ),
        "ACTIVE <-> SUSPENDED round trip",
    )


def c08_closed_is_terminal(v):
    closed = v.scalar("SELECT client_id FROM clients WHERE status = 'CLOSED' LIMIT 1;")
    require(closed, "seed data has no CLOSED client to test with")
    v.expect_rejected(
        "UPDATE clients SET status = 'ACTIVE' WHERE client_id = " + closed + ";",
        "23514",
        "reopening a CLOSED client",
    )


def c09_client_never_deleted(v):
    v.expect_rejected(
        "DELETE FROM clients WHERE client_id = 1;",
        "23001",
        "deleting a client row",
    )


def c10_instrument_never_deleted(v):
    v.expect_rejected(
        "DELETE FROM instruments WHERE instrument_id = 1;",
        "23001",
        "deleting an instrument row",
    )


def c11_delisting_keeps_orders_resolvable(v):
    """An instrument that stops trading keeps its row, so old orders still join."""
    out = v.expect_accepted(
        "BEGIN;\n"
        "UPDATE instruments SET is_active = FALSE, delisted_on = now() WHERE instrument_id = 1;\n"
        "SELECT count(*) FROM orders o JOIN instruments i USING (instrument_id) "
        "WHERE i.instrument_id = 1;\n"
        "ROLLBACK;\n",
        "delisting instrument 1",
    )
    numbers = [int(t) for t in re.findall(r"^\s*(\d+)\s*$", out, re.M)]
    require(
        numbers and max(numbers) > 0,
        "after delisting, orders no longer resolve their instrument (got " + repr(out) + ")",
    )


def c12_delisted_must_have_date(v):
    v.expect_rejected(
        "UPDATE instruments SET is_active = FALSE WHERE instrument_id = 1;",
        "23514",
        "delisting an instrument without recording delisted_on",
    )


def c13_single_terminal_state(v):
    """An order that already succeeded cannot also fail."""
    order_id = v.scalar("SELECT order_id FROM transaction_success ORDER BY order_id LIMIT 1;")
    require(order_id, "seed data has no successful order to test with")
    v.expect_rejected(
        "INSERT INTO transaction_failures (order_id, quantity, value, reason_for_failure) "
        "VALUES (" + order_id + ", 1, 1.00, 'verify: should be impossible');",
        "23514",
        "failing an order that already succeeded",
    )


def c14_terminal_insert_updates_order_status(v):
    """The trigger keeps orders.status and the terminal tables in agreement."""
    order_id = v.scalar("SELECT order_id FROM orders WHERE status = 'RECEIVED' LIMIT 1;")
    require(order_id, "seed data has no RECEIVED order to test with")
    out = v.expect_accepted(
        "BEGIN;\n"
        "INSERT INTO transaction_success (order_id, quantity, value) VALUES ("
        + order_id + ", 1, 1.00);\n"
        "SELECT status FROM orders WHERE order_id = " + order_id + ";\n"
        "ROLLBACK;\n",
        "settling a RECEIVED order",
    )
    require(
        "SUCCESS" in out,
        "inserting into transaction_success did not move orders.status to SUCCESS: " + repr(out),
    )


def c15_holding_rejects_negative_quantity(v):
    v.expect_rejected(
        "INSERT INTO portfolio_holding (client_id, instrument_id, quantity, avg_price) "
        "VALUES (3, 5, -10, 100.0000);",
        "23514",
        "a negative quantity in portfolio_holding",
    )


def c16_positions_accepts_negative_quantity(v):
    """The deliberate difference: an intraday SHORT is a negative quantity."""
    v.expect_accepted(
        rollback_script(
            "INSERT INTO portfolio_positions (client_id, instrument_id, quantity, avg_price) "
            "VALUES (3, 5, -10, 100.0000);"
        ),
        "a negative (short) quantity in portfolio_positions",
    )


def c17_one_portfolio_row_per_client_instrument(v):
    existing = v.rows(
        "SELECT client_id, instrument_id FROM portfolio_holding ORDER BY holding_id LIMIT 1;"
    )
    require(existing, "no seeded holdings to test against")
    client_id, instrument_id = existing[0][0], existing[0][1]
    v.expect_rejected(
        "INSERT INTO portfolio_holding (client_id, instrument_id, quantity, avg_price) "
        "VALUES (" + client_id + ", " + instrument_id + ", 1, 1.0000);",
        "23505",
        "a second holding row for the same (client, instrument)",
    )


def c18_optimistic_concurrency_detects_the_loser(v):
    """
    SEC3-94: 'the second writer of a concurrent balance update discovers that
    it lost.' Both writers read version N; the first bumps it, the second's
    UPDATE then matches zero rows and it knows it lost.
    """
    account = v.scalar("SELECT account_number FROM bank_account ORDER BY account_number LIMIT 1;")
    require(account, "no seeded bank accounts to test with")
    v.expect_accepted(
        "BEGIN;\n"
        "DO $verify$\n"
        "DECLARE stale INT; n INT;\n"
        "BEGIN\n"
        "  SELECT version INTO stale FROM bank_account WHERE account_number = "
        + quote_literal(account) + ";\n"
        "  UPDATE bank_account SET balance = balance + 1, version = version + 1\n"
        "   WHERE account_number = " + quote_literal(account) + " AND version = stale;\n"
        "  GET DIAGNOSTICS n = ROW_COUNT;\n"
        "  IF n <> 1 THEN RAISE EXCEPTION 'first writer should have won, updated % row(s)', n; END IF;\n"
        "  UPDATE bank_account SET balance = balance + 1, version = version + 1\n"
        "   WHERE account_number = " + quote_literal(account) + " AND version = stale;\n"
        "  GET DIAGNOSTICS n = ROW_COUNT;\n"
        "  IF n <> 0 THEN RAISE EXCEPTION 'stale writer should have lost, updated % row(s)', n; END IF;\n"
        "END\n"
        "$verify$;\n"
        "ROLLBACK;\n",
        "optimistic concurrency on bank_account.version",
    )


def c19_negative_balance_rejected(v):
    account = v.scalar("SELECT account_number FROM bank_account ORDER BY account_number LIMIT 1;")
    v.expect_rejected(
        "UPDATE bank_account SET balance = -1 WHERE account_number = "
        + quote_literal(account) + ";",
        "23514",
        "driving a bank_account balance negative",
    )


def c20_sequences_resynced_past_seed(v):
    """
    Seed CSVs carry explicit ids, so the SERIAL sequences must have been moved
    past them - otherwise the app's first insert collides with seed data.
    """
    max_id = v.count("SELECT coalesce(max(order_id), 0) FROM orders;")
    out = v.expect_accepted(
        "BEGIN;\n"
        + _NEW_ORDER
        + "(1, 1, 100.0000, 'BUY', 'DELIVERY', 1, 'NSE', 'verify-sequence-probe') "
          "RETURNING order_id;\n"
        "ROLLBACK;\n",
        "inserting an order without an explicit id",
    )
    numbers = [int(t) for t in re.findall(r"^\s*(\d+)\s*$", out, re.M)]
    require(numbers, "did not get an order_id back: " + repr(out))
    require(
        max(numbers) > max_id,
        "orders_order_id_seq is behind the seeded data: next id would be "
        + str(max(numbers)) + " but max(order_id) is " + str(max_id),
    )


def c22_in_progress_cannot_contradict_its_order(v):
    """
    in_progress.instrument_id duplicates orders.instrument_id. The composite FK
    must make the two disagreeing impossible, not merely unlikely.
    """
    row = v.rows(
        "SELECT order_id, instrument_id FROM orders o WHERE EXISTS "
        "(SELECT 1 FROM instruments i WHERE i.instrument_id <> o.instrument_id) LIMIT 1;"
    )
    require(row, "no orders to test against")
    order_id, instrument_id = row[0][0], row[0][1]
    other = v.scalar(
        "SELECT instrument_id FROM instruments WHERE instrument_id <> "
        + instrument_id + " ORDER BY instrument_id LIMIT 1;"
    )
    require(other, "need a second instrument to test against")
    v.expect_rejected(
        "INSERT INTO in_progress (order_id, instrument_id, quantity) VALUES ("
        + order_id + ", " + other + ", 1);",
        "23503",
        "queueing an order against a different instrument than the order names",
    )


def c23_in_progress_accepts_the_matching_instrument(v):
    row = v.rows("SELECT order_id, instrument_id FROM orders LIMIT 1;")
    require(row, "no orders to test against")
    v.expect_accepted(
        rollback_script(
            "INSERT INTO in_progress (order_id, instrument_id, quantity) VALUES ("
            + row[0][0] + ", " + row[0][1] + ", 1);"
        ),
        "queueing an order against its own instrument",
    )


def c21_blank_password_rejected(v):
    email = v.scalar("SELECT email FROM clients ORDER BY client_id LIMIT 1;")
    v.expect_rejected(
        "UPDATE auth SET password = '   ' WHERE email = " + quote_literal(email) + ";",
        "23514",
        "a blank auth password",
    )


# ===========================================================================
# D. DATA CONSISTENCY
# ===========================================================================

def d01_success_orders_have_one_success_row(v):
    n = v.count(
        "SELECT count(*) FROM orders o WHERE o.status = 'SUCCESS' AND NOT EXISTS "
        "(SELECT 1 FROM transaction_success t WHERE t.order_id = o.order_id);"
    )
    equal(n, 0, "SUCCESS orders with no transaction_success row")


def d02_failed_orders_have_one_failure_row(v):
    n = v.count(
        "SELECT count(*) FROM orders o WHERE o.status = 'FAILED' AND NOT EXISTS "
        "(SELECT 1 FROM transaction_failures t WHERE t.order_id = o.order_id);"
    )
    equal(n, 0, "FAILED orders with no transaction_failures row")


def d03_no_order_in_both_terminal_tables(v):
    n = v.count(
        "SELECT count(*) FROM transaction_success s "
        "JOIN transaction_failures f USING (order_id);"
    )
    equal(n, 0, "orders present in BOTH terminal tables")


def d04_status_agrees_with_terminal_tables(v):
    n = v.count(
        "SELECT count(*) FROM orders o "
        "WHERE (EXISTS (SELECT 1 FROM transaction_success t WHERE t.order_id=o.order_id) "
        "       AND o.status <> 'SUCCESS') "
        "   OR (EXISTS (SELECT 1 FROM transaction_failures t WHERE t.order_id=o.order_id) "
        "       AND o.status <> 'FAILED');"
    )
    equal(n, 0, "orders whose status disagrees with their terminal table")


def d05_non_terminal_orders_have_no_terminal_row(v):
    n = v.count(
        "SELECT count(*) FROM orders o WHERE o.status IN ('RECEIVED','IN_PROGRESS') AND ("
        "EXISTS (SELECT 1 FROM transaction_success t WHERE t.order_id=o.order_id) OR "
        "EXISTS (SELECT 1 FROM transaction_failures t WHERE t.order_id=o.order_id));"
    )
    equal(n, 0, "unfinished orders that already have a terminal row")


def d06_all_three_client_states_present(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT status FROM clients;")}
    missing = {"ACTIVE", "SUSPENDED", "CLOSED"} - found
    require(not missing, "seed data does not exercise client state(s): " + ", ".join(sorted(missing)))


def d07_delisted_instrument_still_referenced(v):
    n = v.count(
        "SELECT count(*) FROM orders o JOIN instruments i USING (instrument_id) "
        "WHERE i.is_active = FALSE;"
    )
    require(n > 0, "no orders point at a delisted instrument, so the case is untested")


def d08_positions_has_a_short(v):
    n = v.count("SELECT count(*) FROM portfolio_positions WHERE quantity < 0;")
    require(n > 0, "portfolio_positions has no negative (short) row, so the case is untested")


def d09_holding_has_no_negatives(v):
    n = v.count("SELECT count(*) FROM portfolio_holding WHERE quantity < 0;")
    equal(n, 0, "negative quantities in portfolio_holding")


def _replay_from_db(v):
    """Recompute both portfolio books from the orders actually in the database."""
    rows = v.rows(
        "SELECT o.client_id, o.instrument_id, o.product_type, o.type, o.quantity, "
        "o.price_per_unit FROM orders o "
        "JOIN transaction_success t ON t.order_id = o.order_id "
        "ORDER BY o.order_id;"
    )
    holding, positions = {}, {}
    for client_id, instrument_id, product_type, side, quantity, unit_price in rows:
        book = holding if product_type == "DELIVERY" else positions
        key = (int(client_id), int(instrument_id))
        qty, avg = book.get(key, (0, Decimal(0)))
        book[key] = apply_fill(qty, avg, side, int(quantity), price(unit_price))
    return holding, positions


def _compare_book(v, table, expected, label):
    actual = {
        (int(r[0]), int(r[1])): (int(r[2]), price(r[3]))
        for r in v.rows(
            "SELECT client_id, instrument_id, quantity, avg_price FROM " + table + ";"
        )
    }
    problems = []
    for key in sorted(set(expected) | set(actual)):
        want = expected.get(key)
        got = actual.get(key)
        where = "client " + str(key[0]) + " / instrument " + str(key[1])
        if want is None:
            problems.append(where + ": in " + table + " as " + str(got)
                            + " but no successful " + label + " order explains it")
        elif got is None:
            problems.append(where + ": successful orders imply " + str(want)
                            + " but there is no row in " + table)
        elif got[0] != want[0] or got[1] != want[1]:
            problems.append(where + ": " + table + " says qty=" + str(got[0])
                            + " avg=" + str(got[1]) + ", replaying the orders gives qty="
                            + str(want[0]) + " avg=" + str(want[1]))
    require(not problems, table + " disagrees with the orders:\n      " + "\n      ".join(problems))


def d10_holding_matches_delivery_orders(v):
    holding, _ = _replay_from_db(v)
    _compare_book(v, "portfolio_holding", holding, "DELIVERY")


def d11_positions_matches_intraday_orders(v):
    _, positions = _replay_from_db(v)
    _compare_book(v, "portfolio_positions", positions, "INTRADAY")


def d12_both_product_types_used(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT product_type FROM orders;")}
    missing = {"INTRADAY", "DELIVERY"} - found
    require(not missing, "seed data has no " + ", ".join(sorted(missing)) + " orders")


def d13_every_order_status_exercised(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT status FROM orders;")}
    missing = {"RECEIVED", "IN_PROGRESS", "SUCCESS", "FAILED"} - found
    require(not missing, "seed data never reaches order status: " + ", ".join(sorted(missing)))


def d14_in_progress_orders_are_marked(v):
    n = v.count(
        "SELECT count(*) FROM in_progress p JOIN orders o USING (order_id) "
        "WHERE o.status NOT IN ('IN_PROGRESS', 'RECEIVED');"
    )
    equal(n, 0, "rows sitting in the in_progress queue for orders that already finished")


# ===========================================================================
# runner
# ===========================================================================

CHECKS = [
    ("A", "tables exist", a01_tables_exist),
    ("A", "portfolio_positions exists", a02_portfolio_positions_exists),
    ("A", "portfolio_positions mirrors portfolio_holding", a03_positions_mirrors_holding),
    ("A", "bank_account.version present", a04_version_column),
    ("A", "orders.product_type present, NOT NULL, no default", a05_product_type_column),
    ("A", "money columns are exact numerics", a06_money_is_exact),
    ("A", "no float/money columns anywhere", a07_no_inexact_numeric_anywhere),
    ("A", "every migration on disk is recorded as applied", a08_every_migration_recorded),
    ("A", "migrations are NNN_ numbered and unique", a09_numbered_in_order),

    ("B", "at least three CHECK constraints", b01_at_least_three_checks),
    ("B", "a CHECK covers account state", b02_account_state_check),
    ("B", "UNIQUE on orders.idempotency_key", b03_idempotency_unique),
    ("B", "all expected foreign keys exist", b04_foreign_keys_present),
    ("B", "portfolio_holding forbids negative quantity", b05_holding_forbids_negative),
    ("B", "portfolio_positions allows negative quantity", b06_positions_allows_negative),
    ("B", "one portfolio row per (client, instrument)", b07_unique_portfolio_keys),
    ("B", "terminal tables are unique per order", b08_terminal_tables_unique_per_order),

    ("C", "duplicate idempotency_key raises 23505", c01_duplicate_idempotency_key_rejected),
    ("C", "unknown product_type rejected", c02_bad_product_type_rejected),
    ("C", "unknown order side rejected", c03_bad_side_rejected),
    ("C", "zero-quantity order rejected", c04_zero_quantity_rejected),
    ("C", "order for a missing client rejected", c05_missing_client_rejected),
    ("C", "unknown client status rejected", c06_bad_client_status_rejected),
    ("C", "ACTIVE <-> SUSPENDED is reversible", c07_suspension_is_reversible),
    ("C", "CLOSED cannot be reopened", c08_closed_is_terminal),
    ("C", "a client row cannot be deleted", c09_client_never_deleted),
    ("C", "an instrument row cannot be deleted", c10_instrument_never_deleted),
    ("C", "delisting keeps old orders resolvable", c11_delisting_keeps_orders_resolvable),
    ("C", "delisting without a date is rejected", c12_delisted_must_have_date),
    ("C", "an order cannot reach two terminal states", c13_single_terminal_state),
    ("C", "settling an order updates orders.status", c14_terminal_insert_updates_order_status),
    ("C", "portfolio_holding rejects a negative quantity", c15_holding_rejects_negative_quantity),
    ("C", "portfolio_positions accepts a short", c16_positions_accepts_negative_quantity),
    ("C", "duplicate (client, instrument) holding rejected", c17_one_portfolio_row_per_client_instrument),
    ("C", "stale balance writer detects it lost", c18_optimistic_concurrency_detects_the_loser),
    ("C", "negative bank balance rejected", c19_negative_balance_rejected),
    ("C", "sequences are past the seeded ids", c20_sequences_resynced_past_seed),
    ("C", "blank auth password rejected", c21_blank_password_rejected),
    ("C", "queue row cannot contradict its order's instrument", c22_in_progress_cannot_contradict_its_order),
    ("C", "queue row with the matching instrument is accepted", c23_in_progress_accepts_the_matching_instrument),

    ("D", "SUCCESS orders have a success row", d01_success_orders_have_one_success_row),
    ("D", "FAILED orders have a failure row", d02_failed_orders_have_one_failure_row),
    ("D", "no order in both terminal tables", d03_no_order_in_both_terminal_tables),
    ("D", "orders.status agrees with terminal tables", d04_status_agrees_with_terminal_tables),
    ("D", "unfinished orders have no terminal row", d05_non_terminal_orders_have_no_terminal_row),
    ("D", "all three client states are seeded", d06_all_three_client_states_present),
    ("D", "a delisted instrument still has orders", d07_delisted_instrument_still_referenced),
    ("D", "portfolio_positions contains a short", d08_positions_has_a_short),
    ("D", "portfolio_holding has no negatives", d09_holding_has_no_negatives),
    ("D", "portfolio_holding matches the DELIVERY orders", d10_holding_matches_delivery_orders),
    ("D", "portfolio_positions matches the INTRADAY orders", d11_positions_matches_intraday_orders),
    ("D", "both product types are exercised", d12_both_product_types_used),
    ("D", "all four order statuses are exercised", d13_every_order_status_exercised),
    ("D", "the in_progress queue holds only unfinished orders", d14_in_progress_orders_are_marked),
]

SECTION_TITLES = {
    "A": "Structure",
    "B": "Constraints",
    "C": "Behaviour",
    "D": "Data consistency",
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="verify_db.py",
        description="Verify the trade database against the SEC3-94 / SEC3-95 acceptance criteria.",
    )
    add_connection_args(parser)
    parser.add_argument("-v", "--verbose", action="store_true", help="list passing checks too")
    parser.add_argument("--only", metavar="SECTION", help="run one section only (A, B, C or D)")
    args = parser.parse_args(argv)

    try:
        cfg = DbConfig.resolve(args)
    except DbError as exc:
        print("error: " + str(exc))
        return 1

    print("Verifying " + cfg.describe())

    reachable, detail = cfg.server_reachable()
    if not reachable:
        print("error: cannot reach the server.\n" + detail)
        return 1
    if not cfg.database_exists():
        print("error: database " + cfg.dbname + " does not exist. Run: python scripts/apply_db.py")
        return 1

    verifier = Verifier(cfg)
    selected = [c for c in CHECKS if not args.only or c[0] == args.only.upper()]
    if not selected:
        print("error: no checks in section " + repr(args.only))
        return 2

    passed, failures = 0, []
    current_section = None

    for section, name, fn in selected:
        if section != current_section:
            current_section = section
            print("")
            print(section + ". " + SECTION_TITLES.get(section, section))
        try:
            fn(verifier)
        except CheckFailed as exc:
            failures.append((section, name, str(exc)))
            print("  FAIL  " + name)
            for line in str(exc).splitlines():
                print("        " + line)
        except DbError as exc:
            failures.append((section, name, str(exc)))
            print("  ERROR " + name)
            for line in str(exc).splitlines()[:6]:
                print("        " + line)
        else:
            passed += 1
            if args.verbose:
                print("  ok    " + name)

    print("")
    print("=" * 70)
    if failures:
        print("FAILED: " + str(passed) + " passed, " + str(len(failures)) + " failed")
        print("")
        for section, name, _ in failures:
            print("  " + section + " - " + name)
        return 1

    print("PASSED: all " + str(passed) + " checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
