from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path

from . import transform as transform_module

DEFAULT_DB_PATH = "warehouse.duckdb"

DEFAULT_INTERVAL = "1d"
SCHEMA_FILE = Path(__file__).parent / "analytics_schema.sql"

log = logging.getLogger(__name__)


def exchange_for(symbol: str) -> str:
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
    return value.year * 10000 + value.month * 100 + value.day


def price_row(row: dict, run_id: str, loaded_at: datetime) -> tuple:
    return (
        row["symbol"],
        row["date"],
        row.get("interval") or DEFAULT_INTERVAL,
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
    return f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


INSERT_PRICE_SQL = """
INSERT INTO daily_price (
    symbol, trade_date, "interval", date_key, exchange, currency,
    "open", "high", "low", "close", adj_close, volume,
    price_range, price_change, daily_return_pct, turnover,
    synthetic, repaired, repairs, run_id, loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

DELETE_PRICE_SQL = ('DELETE FROM daily_price '
                    'WHERE symbol = ? AND trade_date = ? AND "interval" = ?')

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


def connect(db_path: str = DEFAULT_DB_PATH):
    try:
        import duckdb
    except ImportError as exc:
        raise ImportError(
            "duckdb is required for the load step. Install it with:\n"
            "    pip install duckdb\n"
            "Or run the pipeline with --print to use the console loader."
        ) from exc
    return duckdb.connect(db_path)


def _ddl_statements(sql_text: str) -> list[str]:
    body = "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )
    return [statement.strip() for statement in body.split(";") if statement.strip()]


def _first_answer(con, attempts: list) -> set:
    for sql, params, column in attempts:
        try:
            rows = con.execute(sql, params).fetchall()
        except Exception:
            continue
        return {row[column] for row in rows}
    return set()


def _table_names(con) -> set:
    return _first_answer(con, [
        ("SELECT table_name FROM information_schema.tables "
         "WHERE table_schema = 'main'", [], 0),
        ("SELECT name FROM sqlite_master WHERE type = 'table'", [], 0),
    ])


def _columns_of(con, table: str) -> set:
    return _first_answer(con, [
        ("SELECT column_name FROM information_schema.columns "
         "WHERE table_schema = 'main' AND table_name = ?", [table], 0),
        (f'PRAGMA table_info("{table}")', [], 1),
    ])


def migrate_interval_into_the_grain(con) -> bool:
    if "daily_price" not in _table_names(con):
        return False
    if "interval" in _columns_of(con, "daily_price"):
        return False

    log.warning("migrating daily_price: adding `interval` to the primary key; "
                "existing rows are stamped %r", DEFAULT_INTERVAL)
    con.execute("BEGIN TRANSACTION")
    try:
        for statement in _ddl_statements(SCHEMA_FILE.read_text(encoding="utf-8")):
            if "CREATE TABLE IF NOT EXISTS daily_price" in statement:
                con.execute(statement.replace(
                    "CREATE TABLE IF NOT EXISTS daily_price",
                    "CREATE TABLE daily_price__migrating"))
                break
        con.execute(f"""
            INSERT INTO daily_price__migrating
            SELECT symbol, trade_date, '{DEFAULT_INTERVAL}', date_key, exchange,
                   currency, "open", "high", "low", "close", adj_close, volume,
                   price_range, price_change, daily_return_pct, turnover,
                   synthetic, repaired, repairs, run_id, loaded_at
              FROM daily_price
        """)
        con.execute("DROP TABLE daily_price")
        con.execute("ALTER TABLE daily_price__migrating RENAME TO daily_price")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return True


def ensure_schema(con) -> None:
    migrate_interval_into_the_grain(con)
    for statement in _ddl_statements(SCHEMA_FILE.read_text(encoding="utf-8")):
        con.execute(statement)


def write_result(con, result: dict, run_id: str) -> int:
    now = datetime.now()
    rows = result["rows"]
    quarantined = result["quarantined"]
    symbol = result["summary"]["symbol"]

    for row in rows:
        con.execute(DELETE_PRICE_SQL, [row["symbol"], row["date"],
                                       row.get("interval") or DEFAULT_INTERVAL])
    if rows:
        con.executemany(
            INSERT_PRICE_SQL, [price_row(r, run_id, now) for r in rows]
        )

    con.execute(DELETE_QUARANTINE_SQL, [symbol])
    if quarantined:
        con.executemany(
            INSERT_QUARANTINE_SQL,
            [quarantine_row(b, run_id, now) for b in quarantined],
        )

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

    con.execute(DELETE_RUN_SQL, [run_id, symbol])
    con.execute(INSERT_RUN_SQL, list(run_row(result, run_id, now)))
    return len(rows)


def reconcile(con) -> list:
    return con.execute(RECONCILE_SQL).fetchall()


def load(result: dict, db_path: str = DEFAULT_DB_PATH, run_id: str | None = None) -> int:
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
