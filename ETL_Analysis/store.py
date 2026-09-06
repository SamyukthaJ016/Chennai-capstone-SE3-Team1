from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import load as load_module
from . import transform as transform_module

DEFAULT_DB_PATH = load_module.DEFAULT_DB_PATH

TABLES = ("daily_price", "quarantined_candle", "load_run", "run_metric")

MAX_CONSOLE_ROWS = 2000

log = logging.getLogger(__name__)


class StoreUnavailable(RuntimeError):
    pass


class UnsafeQuery(ValueError):
    pass


READ_STATEMENTS = frozenset({
    "select", "with", "from", "table", "values", "describe", "desc", "show",
    "explain", "summarize", "pragma",
})

WRITE_KEYWORDS = frozenset({
    "insert", "update", "delete", "merge", "upsert", "truncate",
    "create", "drop", "alter", "replace", "rename",
    "attach", "detach", "install", "load", "copy", "export", "import",
    "begin", "commit", "rollback", "checkpoint", "vacuum", "reindex",
    "set", "reset", "use", "call", "prepare", "execute", "deallocate",
})

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WORD = re.compile(r"[a-z_][a-z0-9_]*")


def strip_sql_comments(sql: str) -> str:
    return _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql))


def check_query(sql: str) -> str:
    if not sql or not sql.strip():
        raise UnsafeQuery("Enter a query first.")

    body = strip_sql_comments(sql).strip().rstrip(";").strip()
    if not body:
        raise UnsafeQuery("That query is only comments.")
    if ";" in body:
        raise UnsafeQuery(
            "One statement at a time. Remove the ';' and everything after it."
        )

    words = _WORD.findall(body.lower())
    if not words:
        raise UnsafeQuery("That does not look like a SQL statement.")

    if words[0] not in READ_STATEMENTS:
        raise UnsafeQuery(
            f"'{words[0].upper()}' is not a read statement. The console opens "
            f"the store read-only, so it runs "
            f"{', '.join(sorted(w.upper() for w in READ_STATEMENTS))} only."
        )

    offending = sorted(set(words) & WRITE_KEYWORDS)
    if offending:
        raise UnsafeQuery(
            f"{', '.join(w.upper() for w in offending)} cannot run here: the "
            f"console reads the store, it does not change it or reach outside "
            f"it. Load data with the pipeline instead."
        )
    return body


def _float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int(value) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def price_row(record: dict) -> dict:
    return {
        "symbol": record["symbol"],
        "date": _as_date(record["trade_date"]),
        "interval": record.get("interval"),
        "exchange": record.get("exchange"),
        "open": _float(record["open"]),
        "high": _float(record["high"]),
        "low": _float(record["low"]),
        "close": _float(record["close"]),
        "adjclose": _float(record.get("adj_close")),
        "volume": _int(record.get("volume")),
        "synthetic": bool(record.get("synthetic")),
        "currency": record.get("currency"),
        "repaired": bool(record.get("repaired")),
        "repairs": _repairs(record.get("repairs")),
        "range": _float(record.get("price_range")),
        "change": _float(record.get("price_change")),
        "daily_return_pct": _float(record.get("daily_return_pct")),
        "turnover": _float(record.get("turnover")),
        "run_id": record.get("run_id"),
    }


def _repairs(value) -> list[dict]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def quarantine_row(record: dict) -> dict:
    candle = record.get("candle_json")
    if isinstance(candle, str):
        try:
            candle = json.loads(candle)
        except ValueError:
            candle = {"date": record.get("raw_date"), "raw": candle}
    return {
        "symbol": record.get("symbol"),
        "reason": record.get("reason"),
        "detail": record.get("detail"),
        "candle": candle if isinstance(candle, dict) else {},
        "run_id": record.get("run_id"),
    }


def build_results(price_records: list[dict],
                  quarantine_records: list[dict] | None = None,
                  candles_in: dict | None = None,
                  repair: bool = True) -> list[dict]:
    by_symbol: dict[str, list[dict]] = {}
    for record in price_records:
        by_symbol.setdefault(record["symbol"], []).append(price_row(record))

    bad_by_symbol: dict[str, list[dict]] = {}
    for record in quarantine_records or []:
        bad_by_symbol.setdefault(record["symbol"], []).append(
            quarantine_row(record))

    results = []
    for symbol in sorted(set(by_symbol) | set(bad_by_symbol)):
        rows = by_symbol.get(symbol, [])
        bad = bad_by_symbol.get(symbol, [])
        summary = transform_module.summarise_rows(
            symbol, rows, bad, repair=repair,
            candles_in=(candles_in or {}).get(symbol),
        )
        results.append({
            "symbol": symbol,
            "currency": rows[0]["currency"] if rows else None,
            "interval": "1d",
            "rows": rows,
            "quarantined": bad,
            "summary": summary,
        })

    results.sort(
        key=lambda r: abs(r["summary"].get("period_return_pct") or 0.0),
        reverse=True,
    )
    return results


class StoreHandle:

    def __init__(self, connection, used_snapshot: bool, path: str):
        self.connection = connection
        self.used_snapshot = used_snapshot
        self.path = path

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            log.debug("ignoring an error while closing the store", exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def store_stamp(db_path: str = DEFAULT_DB_PATH) -> tuple:
    path = Path(db_path)
    if not path.is_file():
        return (str(path), 0, 0)
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _snapshot(path: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="etl-store-")) / path.name
    shutil.copy2(path, target)
    wal = path.with_name(path.name + ".wal")
    if wal.is_file():
        shutil.copy2(wal, target.with_name(target.name + ".wal"))
    return target


LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_SECONDS = 0.4


def connect(db_path: str = DEFAULT_DB_PATH,
            allow_snapshot: bool = True) -> StoreHandle:
    path = Path(db_path)
    if not path.is_file():
        raise StoreUnavailable(
            f"No store at {path}. Run the pipeline first:\n"
            f"    python -m ETL_Analysis.pipeline"
        )
    try:
        import duckdb
    except ImportError as exc:
        raise StoreUnavailable(
            "duckdb is required to read the store. Install it with:\n"
            "    pip install duckdb"
        ) from exc

    last_error: Exception | None = None
    for attempt in range(1, LOCK_RETRY_ATTEMPTS + 1):
        try:
            return StoreHandle(duckdb.connect(str(path), read_only=True),
                               used_snapshot=False, path=str(path))
        except Exception as exc:
            last_error = exc

        if allow_snapshot:
            try:
                copy = _snapshot(path)
                log.info("store is locked; reading a copy of it instead")
                return StoreHandle(duckdb.connect(str(copy), read_only=True),
                                   used_snapshot=True, path=str(path))
            except Exception as exc:
                last_error = exc

        if attempt < LOCK_RETRY_ATTEMPTS:
            time.sleep(LOCK_RETRY_SECONDS)

    raise StoreUnavailable(
        f"Could not read {path}. A pipeline run is probably writing to it -- "
        f"DuckDB allows many readers or one writer, not both. Try again once "
        f"the run finishes.\n\nThe driver said: {last_error}"
    )


def records(handle: StoreHandle, sql: str, params: list | tuple = ()) -> list[dict]:
    cursor = handle.connection.execute(sql, list(params))
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def has_tables(handle: StoreHandle) -> bool:
    found = {row["table_name"] for row in records(
        handle,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'",
    )}
    return set(TABLES).issubset(found)


def schema(handle: StoreHandle) -> dict:
    out: dict[str, list[tuple[str, str]]] = {}
    for row in records(
        handle,
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position",
    ):
        out.setdefault(row["table_name"], []).append(
            (row["column_name"], row["data_type"]))
    return out


def run_console_query(handle: StoreHandle, sql: str,
                      max_rows: int = MAX_CONSOLE_ROWS) -> dict:
    statement = check_query(sql)
    started = time.perf_counter()
    cursor = handle.connection.execute(statement)
    fetched = cursor.fetchmany(max_rows + 1)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "columns": [description[0] for description in cursor.description],
        "rows": fetched[:max_rows],
        "truncated": len(fetched) > max_rows,
        "elapsed_ms": elapsed_ms,
        "statement": statement,
    }


def runs(handle: StoreHandle) -> list[dict]:
    return records(handle, """
        SELECT run_id,
               count(*)                 AS symbols,
               sum(candles_in)          AS candles_in,
               sum(rows_kept)           AS rows_kept,
               sum(rows_repaired)       AS rows_repaired,
               sum(rows_quarantined)    AS rows_quarantined,
               min(date_from)           AS date_from,
               max(date_to)             AS date_to,
               bool_and(repair_enabled) AS repair_enabled,
               max(loaded_at)           AS loaded_at
          FROM load_run
         GROUP BY run_id
         ORDER BY loaded_at DESC, run_id DESC
    """)


def latest_run_id(handle: StoreHandle) -> str | None:
    found = records(
        handle,
        "SELECT run_id FROM load_run ORDER BY loaded_at DESC, run_id DESC LIMIT 1",
    )
    return found[0]["run_id"] if found else None


def ledger(handle: StoreHandle, run_id: str | None = None) -> list[dict]:
    sql = ("SELECT run_id, symbol, repair_enabled, candles_in, rows_kept, "
           "rows_repaired, rows_quarantined, date_from, date_to, "
           "period_return_pct, avg_volume, loaded_at FROM load_run")
    params: list = []
    if run_id:
        sql += " WHERE run_id = ?"
        params.append(run_id)
    return records(handle, sql + " ORDER BY loaded_at DESC, symbol", params)


def candles_in_by_symbol(handle: StoreHandle, run_id: str | None = None) -> dict:
    rows = records(handle, """
        SELECT symbol, candles_in
          FROM (SELECT symbol, candles_in, loaded_at,
                       row_number() OVER (PARTITION BY symbol
                                          ORDER BY loaded_at DESC) AS rn
                  FROM load_run
                 WHERE (? IS NULL OR run_id = ?))
         WHERE rn = 1
    """, [run_id, run_id])
    return {row["symbol"]: _int(row["candles_in"]) for row in rows}


def intervals(handle: StoreHandle) -> list:
    return [row["interval"] for row in records(handle, """
        SELECT "interval", count(*) AS rows_loaded
          FROM daily_price
         GROUP BY "interval"
         ORDER BY rows_loaded DESC, "interval"
    """)]


def universe(handle: StoreHandle, interval: str | None = None) -> list[dict]:
    where = ' WHERE "interval" = ?' if interval else ""
    return records(handle, f"""
        SELECT symbol,
               any_value(exchange) AS exchange,
               count(*)            AS rows_loaded,
               min(trade_date)     AS date_from,
               max(trade_date)     AS date_to
          FROM daily_price{where}
         GROUP BY symbol
         ORDER BY symbol
    """, [interval] if interval else [])


def date_bounds(handle: StoreHandle, interval: str | None = None) -> tuple:
    sql = "SELECT min(trade_date) AS lo, max(trade_date) AS hi FROM daily_price"
    params: list = []
    if interval:
        sql += ' WHERE "interval" = ?'
        params.append(interval)
    found = records(handle, sql, params)
    if not found:
        return None, None
    return _as_date(found[0]["lo"]), _as_date(found[0]["hi"])


def price_records(handle: StoreHandle, symbols: list[str] | None = None,
                  date_from: date | None = None, date_to: date | None = None,
                  exclude_repaired: bool = False,
                  exclude_synthetic: bool = False,
                  run_id: str | None = None,
                  interval: str | None = None) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if symbols:
        clauses.append(f"symbol IN ({', '.join(['?'] * len(symbols))})")
        params.extend(symbols)
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    if date_from:
        clauses.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("trade_date <= ?")
        params.append(date_to)
    if exclude_repaired:
        clauses.append("NOT repaired")
    if exclude_synthetic:
        clauses.append("NOT synthetic")
    if interval:
        clauses.append('"interval" = ?')
        params.append(interval)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return records(handle, f"""
        SELECT symbol, trade_date, "interval", date_key, exchange, currency,
               "open", "high", "low", "close", adj_close, volume,
               price_range, price_change, daily_return_pct, turnover,
               synthetic, repaired, repairs, run_id
          FROM daily_price{where}
         ORDER BY symbol, trade_date
    """, params)


def quarantine_records(handle: StoreHandle, symbols: list[str] | None = None,
                       run_id: str | None = None) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if symbols:
        clauses.append(f"symbol IN ({', '.join(['?'] * len(symbols))})")
        params.extend(symbols)
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return records(handle, f"""
        SELECT run_id, symbol, raw_date, reason, detail, candle_json,
               quarantined_at
          FROM quarantined_candle{where}
         ORDER BY symbol, raw_date
    """, params)


def metric_history(handle: StoreHandle, metric: str,
                   symbols: list[str] | None = None) -> list[dict]:
    params: list = [metric]
    clause = ""
    if symbols:
        clause = f" AND symbol IN ({', '.join(['?'] * len(symbols))})"
        params.extend(symbols)
    return records(handle, f"""
        SELECT r.run_id, r.symbol, r.value, r.label, r.unit, l.loaded_at
          FROM run_metric r
          LEFT JOIN (SELECT run_id, max(loaded_at) AS loaded_at
                       FROM load_run GROUP BY run_id) l
            ON l.run_id = r.run_id
         WHERE r.metric = ?{clause}
         ORDER BY l.loaded_at, r.run_id, r.symbol
    """, params)


def available_metrics(handle: StoreHandle) -> list:
    found = {row["metric"]: row["label"] for row in records(
        handle, "SELECT DISTINCT metric, label FROM run_metric")}
    ordered = [(key, found[key])
               for key, _, _ in transform_module.METRIC_SPEC if key in found]
    known = {key for key, _ in ordered}
    return ordered + sorted((m, l) for m, l in found.items() if m not in known)


def reconciliation(handle: StoreHandle) -> list[dict]:
    return records(handle, """
        SELECT run_id, symbol, candles_in, rows_kept, rows_quarantined
          FROM load_run
         WHERE candles_in <> rows_kept + rows_quarantined
         ORDER BY run_id DESC, symbol
    """)


def quarantine_reasons(handle: StoreHandle,
                       symbols: list[str] | None = None) -> list[dict]:
    params: list = []
    where = ""
    if symbols:
        where = f" WHERE symbol IN ({', '.join(['?'] * len(symbols))})"
        params.extend(symbols)
    return records(handle, f"""
        SELECT reason, count(*) AS rows_affected,
               count(DISTINCT symbol) AS symbols
          FROM quarantined_candle{where}
         GROUP BY reason
         ORDER BY rows_affected DESC, reason
    """, params)


def repair_records(handle: StoreHandle, symbols: list[str] | None = None) -> list[dict]:
    params: list = []
    where = " WHERE repaired"
    if symbols:
        where += f" AND symbol IN ({', '.join(['?'] * len(symbols))})"
        params.extend(symbols)
    return records(handle, f"""
        SELECT symbol, trade_date, repairs, run_id
          FROM daily_price{where}
         ORDER BY symbol, trade_date
    """, params)
