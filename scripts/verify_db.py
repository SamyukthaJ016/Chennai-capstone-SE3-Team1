from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_config import REPO_ROOT, DbConfig, DbError, add_connection_args, quote_literal
from make_seed import apply_fill, price

SQLSTATE_RE = re.compile(r"ERROR:\s+([0-9A-Z]{5}):")

ENTITY_DIR = (REPO_ROOT / "sprint-05-domain-engine" / "src" / "main" / "java"
              / "com" / "team1" / "trading" / "domain" / "entity")

FIELD_RE = re.compile(r"^\s*private\s+(?:final\s+|static\s+|transient\s+)*"
                      r"[\w.<>,\[\]\s]+?\s+(\w+)\s*(?:=[^;]*)?;", re.M)
ENUM_BODY_RE = re.compile(r"enum\s+\w+\s*\{(.*?)\}", re.S)

EXPECTED_TABLES = [
    "auth", "bank_account", "clients", "instruments", "order_history", "orders",
    "portfolio_holding", "portfolio_positions", "schema_migrations",
]

ENTITY_TABLES = {
    "bank_account": ("BankAccount", {}),
    "clients": ("Client", {}),
    "auth": ("Auth", {}),
    "instruments": ("Instrument", {}),
    "orders": ("Order", {}),
    "order_history": ("OrderHistory", {}),
    "portfolio_holding": ("PortfolioHolding", {"portifolioid": "holding_id"}),
    "portfolio_positions": ("PortfolioPosition", {"portifolioid": "position_id"}),
}

ENUM_CONSTRAINTS = [
    ("chk_orders_status", "OrderStatus"),
    ("chk_orders_order_type", "OrderType"),
    ("chk_orders_side", "OrderSide"),
    ("chk_clients_account_state", "AccountStatus"),
    ("chk_order_history_previous_status", "OrderStatus"),
    ("chk_order_history_new_status", "OrderStatus"),
]

MONEY_COLUMNS = [
    ("bank_account", "account_balance"),
    ("clients", "wallet_balance"),
    ("orders", "price"),
    ("orders", "executed_price"),
    ("orders", "quantity"),
    ("portfolio_holding", "price_per_unit"),
    ("portfolio_holding", "overall_gains"),
    ("portfolio_positions", "price_per_unit"),
    ("portfolio_positions", "overall_gains"),
]

INEXACT_TYPES = {"real", "double precision", "float", "float4", "float8", "money"}

HOLDING_BOOK = "HOLDING"
POSITION_BOOK = "POSITION"


class CheckFailed(AssertionError):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def equal(actual, expected, what):
    if str(actual) != str(expected):
        raise CheckFailed(what + ": expected " + repr(expected) + ", got " + repr(actual))


def sqlstate_of(proc):
    match = SQLSTATE_RE.search(proc.stderr or "")
    return match.group(1) if match else None


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _entity_source(class_name):
    for candidate in (ENTITY_DIR / (class_name + ".java"),
                      ENTITY_DIR / "types" / (class_name + ".java")):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise CheckFailed(
        class_name + ".java was not found under " + str(ENTITY_DIR)
        + "\n  The database is meant to mirror the domain entities, so parity "
        "cannot be checked without them."
    )


def entity_fields(class_name):
    text = _entity_source(class_name)
    fields = FIELD_RE.findall(text)
    parent = re.search(r"class\s+\w+\s+extends\s+(\w+)", text)
    if parent:
        fields = entity_fields(parent.group(1)) + fields
    return fields


def entity_columns(table):
    class_name, aliases = ENTITY_TABLES[table]
    columns = []
    for field in entity_fields(class_name):
        column = aliases.get(field, snake(field))
        if column not in columns:
            columns.append(column)
    return columns


def enum_constants(enum_name):
    body = ENUM_BODY_RE.search(_entity_source(enum_name))
    require(body, enum_name + ".java does not look like an enum")
    found = []
    for token in body.group(1).replace("\n", " ").split(","):
        token = token.strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", token):
            found.append(token)
    require(found, enum_name + " declares no constants")
    return set(found)


class Verifier:
    def __init__(self, cfg):
        self.cfg = cfg

    def scalar(self, sql):
        return self.cfg.scalar(sql)

    def rows(self, sql):
        return self.cfg.rows(sql)

    def count(self, sql):
        return int(self.scalar(sql) or "0")

    def columns_of(self, table):
        return [r[0] for r in self.rows(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=" + quote_literal(table)
            + " ORDER BY ordinal_position;"
        )]

    def constraint_def(self, name):
        return self.scalar(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = 'public' AND c.conname = " + quote_literal(name) + ";"
        )

    def expect_rejected(self, sql, sqlstate, what):
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
        proc = self.cfg.run(script=script, verbose_errors=True)
        if proc.returncode != 0:
            raise CheckFailed(
                what + ": the database REJECTED it, but it should be accepted"
                + "\n      " + first_error_line(proc)
            )
        return proc.stdout


def first_error_line(proc):
    output = (proc.stderr or "") + (proc.stdout or "")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines:
        if "ERROR" in line:
            return line
    return lines[0] if lines else "(no output)"


def rollback_script(body):
    return "BEGIN;\n" + body.strip() + "\nROLLBACK;\n"


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


def a04_every_entity_has_a_table(v):
    found = {r[0] for r in v.rows(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE';"
    )}
    missing = sorted(
        table + " (" + ENTITY_TABLES[table][0] + ".java)"
        for table in ENTITY_TABLES if table not in found
    )
    require(not missing, "entity classes with no table: " + ", ".join(missing))


def a05_tables_match_their_entities(v):
    problems = []
    for table in sorted(ENTITY_TABLES):
        want = entity_columns(table)
        got = v.columns_of(table)
        if not got:
            problems.append(table + ": table does not exist")
            continue
        missing = [c for c in want if c not in got]
        extra = [c for c in got if c not in want]
        if missing:
            problems.append(
                table + " is missing column(s) the " + ENTITY_TABLES[table][0]
                + " entity declares: " + ", ".join(missing))
        if extra:
            problems.append(
                table + " has column(s) no field of " + ENTITY_TABLES[table][0]
                + " maps to: " + ", ".join(extra))
    require(not problems, "schema and entities disagree:\n      " + "\n      ".join(problems))


def a06_order_type_column(v):
    dtype = v.scalar(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='order_type';"
    )
    require(dtype == "character varying",
            "orders.order_type missing or wrong type: " + repr(dtype))

    nullable = v.scalar(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='order_type';"
    )
    equal(nullable, "NO", "orders.order_type nullability")

    default = v.scalar(
        "SELECT coalesce(column_default, '') FROM information_schema.columns "
        "WHERE table_name='orders' AND column_name='order_type';"
    )
    require(
        default == "",
        "orders.order_type must have NO default (" + repr(default) + "): a default would "
        "let a caller that forgot to set it silently book an intraday fill into holdings",
    )


def a07_instruments_are_keyed_by_symbol(v):
    dtype = v.scalar(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='instruments' AND column_name='instrument_id';"
    )
    require(
        dtype == "character varying",
        "instruments.instrument_id must be the symbol string the entities use, got "
        + repr(dtype),
    )
    for table in ("orders", "portfolio_holding", "portfolio_positions"):
        referencing = v.scalar(
            "SELECT data_type FROM information_schema.columns WHERE table_name="
            + quote_literal(table) + " AND column_name='instrument_id';"
        )
        equal(referencing, "character varying", table + ".instrument_id type")


def a08_money_is_exact(v):
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


def a09_no_inexact_numeric_anywhere(v):
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


def a10_every_migration_recorded(v):
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


def a11_numbered_in_order(v):
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


def b01_at_least_three_checks(v):
    n = v.count(
        "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE c.contype='c' AND n.nspname='public' AND c.conname LIKE 'chk_%';"
    )
    require(n >= 3, "expected at least 3 named CHECK constraints, found " + str(n))


def b02_check_vocabularies_match_the_enums(v):
    problems = []
    for conname, enum_name in ENUM_CONSTRAINTS:
        definition = v.constraint_def(conname)
        if not definition:
            problems.append(conname + " does not exist")
            continue
        in_sql = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", definition))
        in_java = enum_constants(enum_name)
        if in_sql != in_java:
            problems.append(
                conname + " allows " + repr(sorted(in_sql)) + " but "
                + enum_name + ".java declares " + repr(sorted(in_java)))
    require(not problems,
            "CHECK vocabularies disagree with the enums:\n      "
            + "\n      ".join(problems))


def b03_idempotency_unique(v):
    definition = v.constraint_def("uq_orders_idempotency_key")
    require(
        definition and "idempotency_key" in definition,
        "UNIQUE constraint on orders.idempotency_key is missing - idempotency must be "
        "enforced by the database, not a read-then-write",
    )


def b04_foreign_keys_present(v):
    expected = {
        ("clients", "bank_account"),
        ("bank_account", "clients"),
        ("auth", "clients"),
        ("orders", "clients"),
        ("orders", "instruments"),
        ("order_history", "orders"),
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
    definition = v.constraint_def("chk_portfolio_holding_quantity_non_negative")
    require(definition, "portfolio_holding is missing its non-negative quantity CHECK")
    require("quantity" in definition, "unexpected definition: " + definition)


def b06_positions_allows_negative(v):
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
        require(v.constraint_def(conname),
                table + " is missing UNIQUE (client_id, instrument_id)")


def b08_order_history_records_a_real_transition(v):
    definition = v.constraint_def("chk_order_history_status_actually_changed")
    require(
        definition,
        "order_history must refuse an event whose previous_status equals its new_status - "
        "an audit row that records no change is noise",
    )


def b09_bank_account_and_clients_reference_each_other(v):
    require(v.constraint_def("fk_bank_account_client"),
            "bank_account.client_id has no foreign key to clients")
    definition = v.constraint_def("fk_bank_account_client")
    require(
        "DEFERRABLE" in definition.upper(),
        "fk_bank_account_client must be DEFERRABLE: bank_account and clients point at "
        "each other, so one of the two has to be checked at COMMIT for either to load",
    )


_NEW_ORDER = (
    "INSERT INTO orders (client_id, account_id, instrument_id, order_type, side, "
    "quantity, price, idempotency_key) VALUES "
)


def c01_duplicate_idempotency_key_rejected(v):
    existing = v.scalar("SELECT idempotency_key FROM orders ORDER BY order_id LIMIT 1;")
    require(existing, "no seeded orders to test against")
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 'RELIANCE', 'HOLDING', 'BUY', 1, 100.0000, "
        + quote_literal(existing) + ");",
        "23505",
        "a second order reusing an existing idempotency_key",
    )


def c02_bad_order_type_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 'RELIANCE', 'SWING', 'BUY', 1, 100.0000, 'verify-bad-type');",
        "23514",
        "an order with order_type = 'SWING'",
    )


def c03_bad_side_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 'RELIANCE', 'HOLDING', 'HOLD', 1, 100.0000, 'verify-bad-side');",
        "23514",
        "an order with side = 'HOLD'",
    )


def c04_zero_quantity_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 'RELIANCE', 'HOLDING', 'BUY', 0, 100.0000, 'verify-zero-qty');",
        "23514",
        "an order with quantity = 0",
    )


def c05_missing_client_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(99999, 1, 'RELIANCE', 'HOLDING', 'BUY', 1, 100.0000, 'verify-no-client');",
        "23503",
        "an order for a client_id that does not exist",
    )


def c06_missing_instrument_rejected(v):
    v.expect_rejected(
        _NEW_ORDER + "(1, 1, 'NOSUCHSYM', 'HOLDING', 'BUY', 1, 100.0000, 'verify-no-instr');",
        "23503",
        "an order for a symbol that is not listed",
    )


def c07_bad_client_state_rejected(v):
    v.expect_rejected(
        "UPDATE clients SET account_state = 'DORMANT' WHERE client_id = 1;",
        "23514",
        "setting a client to an undefined account_state",
    )


def c08_suspension_is_reversible(v):
    v.expect_accepted(
        rollback_script(
            "UPDATE clients SET account_state = 'SUSPENDED' WHERE client_id = 1;\n"
            "UPDATE clients SET account_state = 'ACTIVE'    WHERE client_id = 1;\n"
            "UPDATE clients SET account_state = 'SUSPENDED' WHERE client_id = 1;"
        ),
        "ACTIVE <-> SUSPENDED round trip",
    )


def c09_closed_is_terminal(v):
    closed = v.scalar("SELECT client_id FROM clients WHERE account_state = 'CLOSED' LIMIT 1;")
    require(closed, "seed data has no CLOSED client to test with")
    v.expect_rejected(
        "UPDATE clients SET account_state = 'ACTIVE' WHERE client_id = " + closed + ";",
        "23514",
        "reopening a CLOSED client",
    )


def c10_client_never_deleted(v):
    v.expect_rejected(
        "DELETE FROM clients WHERE client_id = 1;",
        "23001",
        "deleting a client row",
    )


def c11_instrument_never_deleted(v):
    v.expect_rejected(
        "DELETE FROM instruments WHERE instrument_id = 'RELIANCE';",
        "23001",
        "deleting an instrument row",
    )


def c12_delisting_keeps_orders_resolvable(v):
    out = v.expect_accepted(
        "BEGIN;\n"
        "UPDATE instruments SET active = FALSE, updated_on = now() "
        "WHERE instrument_id = 'RELIANCE';\n"
        "SELECT count(*) FROM orders o JOIN instruments i USING (instrument_id) "
        "WHERE i.instrument_id = 'RELIANCE';\n"
        "ROLLBACK;\n",
        "delisting RELIANCE",
    )
    numbers = [int(t) for t in re.findall(r"^\s*(\d+)\s*$", out, re.M)]
    require(
        numbers and max(numbers) > 0,
        "after delisting, orders no longer resolve their instrument (got " + repr(out) + ")",
    )


def c13_deactivating_without_a_date_is_accepted(v):
    v.expect_accepted(
        rollback_script(
            "UPDATE instruments SET active = FALSE WHERE instrument_id = 'RELIANCE';"
        ),
        "Instrument.deactivate() leaves updatedOn null, so the database must accept it",
    )


def c14_bad_order_status_rejected(v):
    v.expect_rejected(
        "UPDATE orders SET status = 'SUCCESS' WHERE order_id = 1;",
        "23514",
        "an order status outside the OrderStatus enum",
    )


def c15_filled_without_executed_price_rejected(v):
    v.expect_rejected(
        _NEW_ORDER.replace("idempotency_key)", "idempotency_key, status)")
        + "(1, 1, 'RELIANCE', 'HOLDING', 'BUY', 1, 100.0000, 'verify-filled-noprice', "
          "'FILLED');",
        "23514",
        "a FILLED order with no executed_price",
    )


def c16_executed_price_only_when_filled(v):
    v.expect_rejected(
        _NEW_ORDER.replace("idempotency_key)", "idempotency_key, executed_price)")
        + "(1, 1, 'RELIANCE', 'HOLDING', 'BUY', 1, 100.0000, 'verify-newprice', 100.0000);",
        "23514",
        "an executed_price on an order that is still NEW",
    )


def c17_holding_rejects_negative_quantity(v):
    v.expect_rejected(
        "INSERT INTO portfolio_holding (client_id, instrument_id, quantity, price_per_unit) "
        "VALUES (3, 'ICICIBANK', -10, 100.0000);",
        "23514",
        "a negative quantity in portfolio_holding",
    )


def c18_positions_accepts_negative_quantity(v):
    v.expect_accepted(
        rollback_script(
            "INSERT INTO portfolio_positions (client_id, instrument_id, quantity, "
            "price_per_unit) VALUES (3, 'ICICIBANK', -10, 100.0000);"
        ),
        "a negative (short) quantity in portfolio_positions",
    )


def c19_one_portfolio_row_per_client_instrument(v):
    existing = v.rows(
        "SELECT client_id, instrument_id FROM portfolio_holding ORDER BY holding_id LIMIT 1;"
    )
    require(existing, "no seeded holdings to test against")
    client_id, instrument_id = existing[0][0], existing[0][1]
    v.expect_rejected(
        "INSERT INTO portfolio_holding (client_id, instrument_id, quantity, price_per_unit) "
        "VALUES (" + client_id + ", " + quote_literal(instrument_id) + ", 1, 1.0000);",
        "23505",
        "a second holding row for the same (client, instrument)",
    )


def c20_optimistic_concurrency_detects_the_loser(v):
    email = v.scalar("SELECT email FROM auth ORDER BY email LIMIT 1;")
    require(email, "no seeded credentials to test with")
    v.expect_accepted(
        "BEGIN;\n"
        "DO $verify$\n"
        "DECLARE stale INT; n INT;\n"
        "BEGIN\n"
        "  SELECT version INTO stale FROM auth WHERE email = " + quote_literal(email) + ";\n"
        "  UPDATE auth SET password_hash = 'rotated-1', updated = now(), "
        "version = version + 1\n"
        "   WHERE email = " + quote_literal(email) + " AND version = stale;\n"
        "  GET DIAGNOSTICS n = ROW_COUNT;\n"
        "  IF n <> 1 THEN RAISE EXCEPTION 'first writer should have won, updated % row(s)', n; "
        "END IF;\n"
        "  UPDATE auth SET password_hash = 'rotated-2', updated = now(), "
        "version = version + 1\n"
        "   WHERE email = " + quote_literal(email) + " AND version = stale;\n"
        "  GET DIAGNOSTICS n = ROW_COUNT;\n"
        "  IF n <> 0 THEN RAISE EXCEPTION 'stale writer should have lost, updated % row(s)', n; "
        "END IF;\n"
        "END\n"
        "$verify$;\n"
        "ROLLBACK;\n",
        "optimistic concurrency on auth.version",
    )


def c21_negative_bank_balance_rejected(v):
    account = v.scalar("SELECT account_number FROM bank_account ORDER BY account_number LIMIT 1;")
    v.expect_rejected(
        "UPDATE bank_account SET account_balance = -1 WHERE account_number = "
        + quote_literal(account) + ";",
        "23514",
        "driving a bank_account balance negative",
    )


def c22_negative_wallet_balance_rejected(v):
    v.expect_rejected(
        "UPDATE clients SET wallet_balance = -1 WHERE client_id = 1;",
        "23514",
        "driving a client wallet balance negative",
    )


def c23_sequences_resynced_past_seed(v):
    max_id = v.count("SELECT coalesce(max(order_id), 0) FROM orders;")
    out = v.expect_accepted(
        "BEGIN;\n"
        + _NEW_ORDER
        + "(1, 1, 'RELIANCE', 'HOLDING', 'BUY', 1, 100.0000, 'verify-sequence-probe') "
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


def c24_blank_password_rejected(v):
    email = v.scalar("SELECT email FROM clients ORDER BY client_id LIMIT 1;")
    v.expect_rejected(
        "UPDATE auth SET password_hash = '   ' WHERE email = " + quote_literal(email) + ";",
        "23514",
        "a blank auth password_hash",
    )


def c25_history_for_a_missing_order_rejected(v):
    v.expect_rejected(
        "INSERT INTO order_history (order_id, event_type, previous_status, new_status) "
        "VALUES (99999, 'FILLED', 'NEW', 'FILLED');",
        "23503",
        "an audit row for an order that does not exist",
    )


def c26_history_accepts_a_real_transition(v):
    order_id = v.scalar("SELECT order_id FROM orders WHERE status = 'NEW' LIMIT 1;")
    require(order_id, "seed data has no NEW order to test with")
    v.expect_accepted(
        rollback_script(
            "INSERT INTO order_history (order_id, event_type, previous_status, new_status) "
            "VALUES (" + order_id + ", 'CANCELLED', 'NEW', 'CANCELLED');"
        ),
        "recording a NEW -> CANCELLED transition",
    )


def c27_history_rejects_an_unknown_status(v):
    order_id = v.scalar("SELECT order_id FROM orders LIMIT 1;")
    v.expect_rejected(
        "INSERT INTO order_history (order_id, event_type, previous_status, new_status) "
        "VALUES (" + order_id + ", 'SETTLED', 'NEW', 'SETTLED');",
        "23514",
        "an audit row naming a status outside the OrderStatus enum",
    )


def d01_filled_orders_have_an_executed_price(v):
    n = v.count(
        "SELECT count(*) FROM orders WHERE status = 'FILLED' AND executed_price IS NULL;"
    )
    equal(n, 0, "FILLED orders with no executed_price")


def d02_unfinished_orders_have_no_executed_price(v):
    n = v.count(
        "SELECT count(*) FROM orders WHERE status <> 'FILLED' AND executed_price IS NOT NULL;"
    )
    equal(n, 0, "orders that were never filled but carry an executed_price")


def d03_every_order_has_a_created_event(v):
    n = v.count(
        "SELECT count(*) FROM orders o WHERE NOT EXISTS ("
        "SELECT 1 FROM order_history h WHERE h.order_id = o.order_id "
        "AND h.event_type = 'CREATED');"
    )
    equal(n, 0, "orders with no CREATED row in order_history")


def d04_last_event_agrees_with_order_status(v):
    problems = v.rows(
        "SELECT o.order_id, o.status, last.new_status FROM orders o "
        "JOIN LATERAL (SELECT h.new_status FROM order_history h "
        "              WHERE h.order_id = o.order_id "
        "              ORDER BY h.event_timestamp DESC, h.history_id DESC LIMIT 1) last "
        "  ON TRUE "
        "WHERE last.new_status IS DISTINCT FROM o.status;"
    )
    require(
        not problems,
        "orders whose latest audit event disagrees with orders.status: "
        + ", ".join("order " + r[0] + " is " + r[1] + " but history ends at " + r[2]
                    for r in problems),
    )


def d05_history_records_no_self_transitions(v):
    n = v.count(
        "SELECT count(*) FROM order_history "
        "WHERE previous_status IS NOT NULL AND previous_status = new_status;"
    )
    equal(n, 0, "audit rows that record a transition to the status already held")


def d06_all_three_client_states_present(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT account_state FROM clients;")}
    missing = enum_constants("AccountStatus") - found
    require(not missing,
            "seed data does not exercise client state(s): " + ", ".join(sorted(missing)))


def d07_every_order_status_exercised(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT status FROM orders;")}
    missing = enum_constants("OrderStatus") - found
    require(not missing,
            "seed data never reaches order status: " + ", ".join(sorted(missing)))


def d08_both_order_types_used(v):
    found = {r[0] for r in v.rows("SELECT DISTINCT order_type FROM orders;")}
    missing = enum_constants("OrderType") - found
    require(not missing, "seed data has no " + ", ".join(sorted(missing)) + " orders")


def d09_delisted_instrument_still_referenced(v):
    n = v.count(
        "SELECT count(*) FROM orders o JOIN instruments i USING (instrument_id) "
        "WHERE i.active = FALSE;"
    )
    require(n > 0, "no orders point at a delisted instrument, so the case is untested")


def d10_positions_has_a_short(v):
    n = v.count("SELECT count(*) FROM portfolio_positions WHERE quantity < 0;")
    require(n > 0, "portfolio_positions has no negative (short) row, so the case is untested")


def d11_holding_has_no_negatives(v):
    n = v.count("SELECT count(*) FROM portfolio_holding WHERE quantity < 0;")
    equal(n, 0, "negative quantities in portfolio_holding")


def _replay_from_db(v):
    rows = v.rows(
        "SELECT client_id, instrument_id, order_type, side, quantity, executed_price "
        "FROM orders WHERE status = 'FILLED' ORDER BY order_id;"
    )
    holding, positions = {}, {}
    for client_id, instrument_id, order_type, side, quantity, executed in rows:
        book = holding if order_type == HOLDING_BOOK else positions
        key = (int(client_id), instrument_id)
        qty, avg = book.get(key, (0, Decimal(0)))
        book[key] = apply_fill(qty, avg, side, int(Decimal(quantity)), price(executed))
    return holding, positions


def _compare_book(v, table, expected, label):
    actual = {
        (int(r[0]), r[1]): (int(r[2]), price(r[3]))
        for r in v.rows(
            "SELECT client_id, instrument_id, quantity, price_per_unit FROM " + table + ";"
        )
    }
    problems = []
    for key in sorted(set(expected) | set(actual)):
        want = expected.get(key)
        got = actual.get(key)
        where = "client " + str(key[0]) + " / " + str(key[1])
        if want is None:
            problems.append(where + ": in " + table + " as " + str(got)
                            + " but no filled " + label + " order explains it")
        elif got is None:
            problems.append(where + ": filled orders imply " + str(want)
                            + " but there is no row in " + table)
        elif got[0] != want[0] or got[1] != want[1]:
            problems.append(where + ": " + table + " says qty=" + str(got[0])
                            + " price=" + str(got[1]) + ", replaying the orders gives qty="
                            + str(want[0]) + " price=" + str(want[1]))
    require(not problems, table + " disagrees with the orders:\n      " + "\n      ".join(problems))


def d12_holding_matches_holding_orders(v):
    holding, _ = _replay_from_db(v)
    _compare_book(v, "portfolio_holding", holding, HOLDING_BOOK)


def d13_positions_matches_position_orders(v):
    _, positions = _replay_from_db(v)
    _compare_book(v, "portfolio_positions", positions, POSITION_BOOK)


def d14_bank_account_and_clients_agree(v):
    problems = v.rows(
        "SELECT c.client_id, c.account_number, b.client_id FROM clients c "
        "JOIN bank_account b ON b.account_number = c.account_number "
        "WHERE b.client_id <> c.client_id;"
    )
    require(
        not problems,
        "clients and bank_account disagree about ownership: "
        + ", ".join("client " + r[0] + " holds " + r[1] + " but that account names client "
                    + r[2] for r in problems),
    )


def d15_every_client_has_credentials(v):
    missing = v.rows(
        "SELECT c.client_id, c.email FROM clients c "
        "WHERE NOT EXISTS (SELECT 1 FROM auth a WHERE a.email = c.email);"
    )
    require(
        not missing,
        "clients with no auth row: "
        + ", ".join(r[0] + " (" + r[1] + ")" for r in missing),
    )


CHECKS = [
    ("A", "tables exist", a01_tables_exist),
    ("A", "portfolio_positions exists", a02_portfolio_positions_exists),
    ("A", "portfolio_positions mirrors portfolio_holding", a03_positions_mirrors_holding),
    ("A", "every entity class has a table", a04_every_entity_has_a_table),
    ("A", "every table matches its entity's fields", a05_tables_match_their_entities),
    ("A", "orders.order_type present, NOT NULL, no default", a06_order_type_column),
    ("A", "instruments are keyed by symbol", a07_instruments_are_keyed_by_symbol),
    ("A", "money columns are exact numerics", a08_money_is_exact),
    ("A", "no float/money columns anywhere", a09_no_inexact_numeric_anywhere),
    ("A", "every migration on disk is recorded as applied", a10_every_migration_recorded),
    ("A", "migrations are NNN_ numbered and unique", a11_numbered_in_order),

    ("B", "at least three CHECK constraints", b01_at_least_three_checks),
    ("B", "CHECK vocabularies match the Java enums", b02_check_vocabularies_match_the_enums),
    ("B", "UNIQUE on orders.idempotency_key", b03_idempotency_unique),
    ("B", "all expected foreign keys exist", b04_foreign_keys_present),
    ("B", "portfolio_holding forbids negative quantity", b05_holding_forbids_negative),
    ("B", "portfolio_positions allows negative quantity", b06_positions_allows_negative),
    ("B", "one portfolio row per (client, instrument)", b07_unique_portfolio_keys),
    ("B", "order_history refuses a no-op transition", b08_order_history_records_a_real_transition),
    ("B", "bank_account and clients reference each other",
     b09_bank_account_and_clients_reference_each_other),

    ("C", "duplicate idempotency_key raises 23505", c01_duplicate_idempotency_key_rejected),
    ("C", "unknown order_type rejected", c02_bad_order_type_rejected),
    ("C", "unknown order side rejected", c03_bad_side_rejected),
    ("C", "zero-quantity order rejected", c04_zero_quantity_rejected),
    ("C", "order for a missing client rejected", c05_missing_client_rejected),
    ("C", "order for an unlisted symbol rejected", c06_missing_instrument_rejected),
    ("C", "unknown client account_state rejected", c07_bad_client_state_rejected),
    ("C", "ACTIVE <-> SUSPENDED is reversible", c08_suspension_is_reversible),
    ("C", "CLOSED cannot be reopened", c09_closed_is_terminal),
    ("C", "a client row cannot be deleted", c10_client_never_deleted),
    ("C", "an instrument row cannot be deleted", c11_instrument_never_deleted),
    ("C", "delisting keeps old orders resolvable", c12_delisting_keeps_orders_resolvable),
    ("C", "deactivate() without a date is accepted", c13_deactivating_without_a_date_is_accepted),
    ("C", "an unknown order status is rejected", c14_bad_order_status_rejected),
    ("C", "FILLED without an executed price rejected", c15_filled_without_executed_price_rejected),
    ("C", "executed price only on a FILLED order", c16_executed_price_only_when_filled),
    ("C", "portfolio_holding rejects a negative quantity", c17_holding_rejects_negative_quantity),
    ("C", "portfolio_positions accepts a short", c18_positions_accepts_negative_quantity),
    ("C", "duplicate (client, instrument) holding rejected",
     c19_one_portfolio_row_per_client_instrument),
    ("C", "stale credential writer detects it lost", c20_optimistic_concurrency_detects_the_loser),
    ("C", "negative bank balance rejected", c21_negative_bank_balance_rejected),
    ("C", "negative wallet balance rejected", c22_negative_wallet_balance_rejected),
    ("C", "sequences are past the seeded ids", c23_sequences_resynced_past_seed),
    ("C", "blank auth password rejected", c24_blank_password_rejected),
    ("C", "audit row for a missing order rejected", c25_history_for_a_missing_order_rejected),
    ("C", "audit row for a real transition accepted", c26_history_accepts_a_real_transition),
    ("C", "audit row with an unknown status rejected", c27_history_rejects_an_unknown_status),

    ("D", "FILLED orders carry an executed price", d01_filled_orders_have_an_executed_price),
    ("D", "unfilled orders carry no executed price", d02_unfinished_orders_have_no_executed_price),
    ("D", "every order has a CREATED event", d03_every_order_has_a_created_event),
    ("D", "the last event agrees with orders.status", d04_last_event_agrees_with_order_status),
    ("D", "no audit row records a self-transition", d05_history_records_no_self_transitions),
    ("D", "all three client states are seeded", d06_all_three_client_states_present),
    ("D", "all four order statuses are exercised", d07_every_order_status_exercised),
    ("D", "both order types are exercised", d08_both_order_types_used),
    ("D", "a delisted instrument still has orders", d09_delisted_instrument_still_referenced),
    ("D", "portfolio_positions contains a short", d10_positions_has_a_short),
    ("D", "portfolio_holding has no negatives", d11_holding_has_no_negatives),
    ("D", "portfolio_holding matches the HOLDING orders", d12_holding_matches_holding_orders),
    ("D", "portfolio_positions matches the POSITION orders", d13_positions_matches_position_orders),
    ("D", "bank_account and clients agree on ownership", d14_bank_account_and_clients_agree),
    ("D", "every client has credentials", d15_every_client_has_credentials),
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
        description="Verify the trade database against the domain entities and the "
                    "SEC3-94 / SEC3-95 acceptance criteria.",
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

    selected = [c for c in CHECKS if not args.only or c[0] == args.only.upper()]
    if not selected:
        print("error: no checks in section " + repr(args.only))
        return 2

    verifier = Verifier(cfg)
    failures = []
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
            print("      " + str(exc))
        except DbError as exc:
            failures.append((section, name, str(exc)))
            print("  ERROR " + name)
            print("      " + str(exc))
        else:
            if args.verbose:
                print("  ok    " + name)

    print("")
    print("=" * 70)
    if failures:
        print("FAILED: " + str(len(failures)) + " of " + str(len(selected)) + " checks")
        for section, name, _ in failures:
            print("  " + section + " - " + name)
        return 1

    print("PASSED: all " + str(len(selected)) + " checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
