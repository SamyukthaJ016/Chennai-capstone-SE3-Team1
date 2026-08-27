"""Load: the only part of the pipeline that writes.

Writes the transform's output into the analytical store, DuckDB. Two things
land there, per the sprint's decision:

  - the analysis rows   -> daily_price
  - the rejected rows   -> quarantined_candle

plus a ledger row per symbol per run in load_run, so "what did this load and
do the numbers add up" is answerable in SQL rather than only in a console log.

DDL lives in `analytics_schema.sql` next to this module, in portable ANSI SQL.

The previous print-only loader is kept as `load_print.py`, so the pipeline can
still be demonstrated on a machine with no DuckDB installed.

IDEMPOTENT BY CONSTRUCTION
    The contract requires it: "Make the load idempotent: re-running yesterday's
    load must not double-count. Merge on the natural key, do not blindly
    insert."

    daily_price is merged on (symbol, trade_date): the loader DELETEs exactly
    the dates it is about to write, then INSERTs. Deleting by date rather than
    by symbol means a narrow re-pull does not destroy history from a wider one.
    quarantined_candle is replaced per symbol for the same reason.

STRUCTURE
    Everything that shapes a row is a pure function -- `exchange_for`,
    `date_key_for`, `price_row`, `quarantine_row` -- and is tested without a
    database. Only `connect`, `ensure_schema` and `write_result` touch DuckDB.
    If a number lands wrong, the pure functions are where to look first.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path

from . import transform as transform_module

DEFAULT_DB_PATH = "warehouse.duckdb"
SCHEMA_FILE = Path(__file__).parent / "analytics_schema.sql"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure shaping logic. No database, no I/O -- testable on its own.
# ---------------------------------------------------------------------------

def exchange_for(symbol: str) -> str:
    """Map a Fauxnance symbol to its venue.

    The same rule contracts/analytics-schema.sql states for DIM_INSTRUMENT:
    a .NS suffix means NSE, .BO means BSE, an FX: prefix means FX, X: means
    crypto, and a plain ticker means a US venue.
    """
    if not symbol:
        return "UNKNOWN"
    upper = symbol.upper()
    if upper.startswith("FX:"):
        return "FX"
    if upper.startswith("X:"):
        return "CRYPTO"
    if upper.endswith(".NS"):
        return "NSE"
    if upper.endswith(".BO"):
        return "BSE"
    return "US"


def date_key_for(value: date) -> int:
    """YYYYMMDD, matching DIM_DATE.date_key in the contract."""
    return value.year * 10000 + value.month * 100 + value.day


def price_row(row: dict, run_id: str, loaded_at: datetime) -> tuple:
    """Flatten one clean transform row into a daily_price tuple.

    Column order must match INSERT_PRICE_SQL below.
    """
    return (
        row["symbol"],
        row["date"],
        date_key_for(row["date"]),
        exchange_for(row["symbol"]),
        row.get("currency"),
        row["open"],
        row["high"],
        row["low"],
        row["close"],
        row.get("adjclose"),
        row.get("volume"),
        row.get("range"),
        row.get("change"),
        row.get("daily_return_pct"),
        row.get("turnover"),
        bool(row.get("synthetic", False)),
        bool(row.get("repaired", False)),
        json.dumps(row.get("repairs") or []),
        run_id,
        loaded_at,
    )


def quarantine_row(bad: dict, run_id: str, quarantined_at: datetime) -> tuple:
    """Flatten one quarantined candle into a quarantined_candle tuple."""
    candle = bad.get("candle")
    raw_date = candle.get("date") if isinstance(candle, dict) else None
    return (
        run_id,
        bad.get("symbol"),
        str(raw_date) if raw_date is not None else None,
        bad.get("reason"),
        bad.get("detail"),
        json.dumps(candle, default=str),
        quarantined_at,
    )


def run_row(result: dict, run_id: str, loaded_at: datetime) -> tuple:
    """Flatten one transform result into a load_run ledger tuple."""
    s = result["summary"]
    return (
        run_id,
        s["symbol"],
        bool(s.get("repair_enabled", True)),
        s["candles_in"],
        s["rows_kept"],
        s.get("rows_repaired", 0),
        s["rows_quarantined"],
        s.get("date_from"),
        s.get("date_to"),
        s.get("period_return_pct"),
        s.get("avg_volume"),
        loaded_at,
    )


def new_run_id() -> str:
    """Sortable, unique, readable in a result set."""
    return f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# SQL. Placeholders are `?`, which DuckDB and SQLite both use -- which is what
# lets the SQLite mirror in tests exercise these exact statements.
# ---------------------------------------------------------------------------

INSERT_PRICE_SQL = """
INSERT INTO daily_price (
    symbol, trade_date, date_key, exchange, currency,
    "open", "high", "low", "close", adj_close, volume,
    price_range, price_change, daily_return_pct, turnover,
    synthetic, repaired, repairs, run_id, loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

DELETE_PRICE_SQL = "DELETE FROM daily_price WHERE symbol = ? AND trade_date = ?"

INSERT_QUARANTINE_SQL = """
INSERT INTO quarantined_candle (
    run_id, symbol, raw_date, reason, detail, candle_json, quarantined_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

DELETE_QUARANTINE_SQL = "DELETE FROM quarantined_candle WHERE symbol = ?"

INSERT_RUN_SQL = """
INSERT INTO load_run (
    run_id, symbol, repair_enabled, candles_in, rows_kept, rows_repaired,
    rows_quarantined, date_from, date_to, period_return_pct, avg_volume,
    loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_METRIC_SQL = """
INSERT INTO run_metric (
    run_id, symbol, metric, label, unit, value, computed_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

DELETE_METRIC_SQL = "DELETE FROM run_metric WHERE run_id = ? AND symbol = ?"

DELETE_RUN_SQL = "DELETE FROM load_run WHERE run_id = ? AND symbol = ?"

RECONCILE_SQL = """
SELECT run_id, symbol, candles_in, rows_kept, rows_quarantined
  FROM load_run
 WHERE candles_in <> rows_kept + rows_quarantined
"""


# ---------------------------------------------------------------------------
# The database boundary.
# ---------------------------------------------------------------------------

def connect(db_path: str = DEFAULT_DB_PATH):
    """Open the DuckDB store. One file on disk, no server, no credentials."""
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "duckdb is required for the load step. Install it with:\n"
            "    pip install duckdb\n"
            "Or run the pipeline with --print to use the console loader."
        ) from exc
    return duckdb.connect(db_path)


def _ddl_statements(sql_text: str) -> list[str]:
    """Split the DDL file into individual statements.

    Executed one at a time rather than as one blob, because drivers differ on
    whether a single execute() accepts multiple statements. Splitting is safe
    here: the DDL contains no string literal with a semicolon in it.
    """
    body = "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )
    return [statement.strip() for statement in body.split(";") if statement.strip()]


def ensure_schema(con) -> None:
    """Create the tables if they are not already there.

    The DDL is CREATE TABLE IF NOT EXISTS throughout, so this is safe on every
    run and needs no migration ledger at this size.
    """
    for statement in _ddl_statements(SCHEMA_FILE.read_text(encoding="utf-8")):
        con.execute(statement)


def write_result(con, result: dict, run_id: str) -> int:
    """Merge one transformed result into the store. Returns rows written.

    Delete-then-insert order matters: clear the natural keys being rewritten
    before inserting, or a re-run duplicates them.
    """
    now = datetime.now()
    rows = result["rows"]
    quarantined = result["quarantined"]
    symbol = result["summary"]["symbol"]

    # Merge on the natural key: clear exactly the dates about to be written.
    for row in rows:
        con.execute(DELETE_PRICE_SQL, [row["symbol"], row["date"]])
    if rows:
        con.executemany(
            INSERT_PRICE_SQL, [price_row(r, run_id, now) for r in rows]
        )

    # Quarantine is a full replace per symbol: this run's verdict on this
    # symbol supersedes the previous one.
    con.execute(DELETE_QUARANTINE_SQL, [symbol])
    if quarantined:
        con.executemany(
            INSERT_QUARANTINE_SQL,
            [quarantine_row(b, run_id, now) for b in quarantined],
        )

    # Analytical metrics, long format. Replaced per (run_id, symbol) so a
    # repeated write within one run does not duplicate them.
    con.execute(DELETE_METRIC_SQL, [run_id, symbol])
    metric_rows = transform_module.metrics(result)
    if metric_rows:
        con.executemany(
            INSERT_METRIC_SQL,
            [
                (run_id, m["symbol"], m["metric"], m["label"], m["unit"],
                 m["value"], now)
                for m in metric_rows
            ],
        )

    # The ledger row is replaced for this (run_id, symbol) too, so
    # write_result is idempotent across all four tables rather than three.
    con.execute(DELETE_RUN_SQL, [run_id, symbol])
    con.execute(INSERT_RUN_SQL, list(run_row(result, run_id, now)))
    return len(rows)


def reconcile(con) -> list:
    """Return any run rows where candles_in != kept + quarantined.

    Empty is the healthy answer. A non-empty result means the pipeline lost a
    row between arriving and landing, which is the failure this whole design
    exists to make visible.
    """
    return con.execute(RECONCILE_SQL).fetchall()


# ---------------------------------------------------------------------------
# Entry points used by pipeline.py
# ---------------------------------------------------------------------------

def load(result: dict, db_path: str = DEFAULT_DB_PATH, run_id: str | None = None) -> int:
    """Load a single transformed result. Returns rows written."""
    run_id = run_id or new_run_id()
    con = connect(db_path)
    try:
        ensure_schema(con)
        written = write_result(con, result, run_id)
        return written
    finally:
        con.close()


def load_many(
    results: list[dict],
    db_path: str = DEFAULT_DB_PATH,
    run_id: str | None = None,
) -> dict:
    """Load several transformed results into one store, on one connection."""
    run_id = run_id or new_run_id()
    totals = {
        "run_id": run_id,
        "db_path": db_path,
        "symbols": 0,
        "rows_loaded": 0,
        "rows_repaired": 0,
        "rows_quarantined": 0,
        "reasons": {},
        "repairs": {},
        "metrics_written": 0,
        "reconciliation_failures": [],
    }

    con = connect(db_path)
    try:
        ensure_schema(con)
        for result in results:
            summary = result["summary"]
            totals["symbols"] += 1
            totals["rows_loaded"] += write_result(con, result, run_id)
            totals["rows_repaired"] += summary.get("rows_repaired", 0)
            totals["rows_quarantined"] += summary["rows_quarantined"]
            for reason, count in summary["quarantine_reasons"].items():
                totals["reasons"][reason] = totals["reasons"].get(reason, 0) + count
            for code, count in summary.get("repair_counts", {}).items():
                totals["repairs"][code] = totals["repairs"].get(code, 0) + count
            totals["metrics_written"] += len(transform_module.metrics(result))
            log.info(
                "loaded %s: %d row(s), %d quarantined",
                summary["symbol"], summary["rows_kept"], summary["rows_quarantined"],
            )

        totals["reconciliation_failures"] = reconcile(con)
    finally:
        con.close()

    return totals
