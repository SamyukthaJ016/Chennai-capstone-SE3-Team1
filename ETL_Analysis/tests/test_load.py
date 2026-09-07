from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pytest

from ETL_Analysis import load as L
from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import transform as T


class SqliteMirror:
    def __init__(self):
        sqlite3.register_adapter(date, lambda d: d.isoformat())
        sqlite3.register_adapter(datetime, lambda d: d.isoformat(sep=" "))
        self._conn = sqlite3.connect(":memory:")
        self._cursor = None

    def execute(self, sql, params=None):
        self._cursor = self._conn.execute(sql, params or [])
        return self

    def executemany(self, sql, seq_of_params):
        self._cursor = self._conn.executemany(sql, seq_of_params)
        return self

    def fetchall(self):
        return self._cursor.fetchall()

    def scalar(self, sql):
        return self._conn.execute(sql).fetchone()[0]

    def close(self):
        self._conn.close()


@pytest.fixture
def con():
    mirror = SqliteMirror()
    L.ensure_schema(mirror)
    yield mirror
    mirror.close()


@pytest.fixture
def results():
    payloads, _ = E.extract_many(["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"])
    return T.transform_many(payloads, repair=True)


@pytest.mark.parametrize("symbol,expected", [
    ("RELIANCE.NS", "NSE"),
    ("INFY.NS", "NSE"),
    ("TATASTEEL.BO", "BSE"),
    ("AAPL", "US"),
    ("FX:EUR/USD", "FX"),
    ("X:BTCUSD", "CRYPTO"),
])
def test_exchange_is_derived_from_the_symbol_scheme(symbol, expected):
    assert L.exchange_for(symbol) == expected


def test_exchange_for_an_empty_symbol_is_unknown_not_a_crash():
    assert L.exchange_for("") == "UNKNOWN"


def test_date_key_is_yyyymmdd_matching_dim_date():
    assert L.date_key_for(date(2026, 9, 28)) == 20260928
    assert L.date_key_for(date(2026, 7, 1)) == 20260701


def test_price_row_column_count_matches_the_insert_statement():
    columns = L.INSERT_PRICE_SQL.count("?")
    row = {"symbol": "INFY.NS", "date": date(2026, 7, 1), "open": 1.0,
           "high": 2.0, "low": 0.5, "close": 1.5}
    assert len(L.price_row(row, "run", datetime.now())) == columns


def test_quarantine_row_column_count_matches_the_insert_statement():
    columns = L.INSERT_QUARANTINE_SQL.count("?")
    bad = {"symbol": "X.NS", "reason": "MISSING_FIELD", "detail": "d",
           "candle": {"date": "2026-07-02"}}
    assert len(L.quarantine_row(bad, "run", datetime.now())) == columns


def test_run_row_column_count_matches_the_insert_statement(results):
    columns = L.INSERT_RUN_SQL.count("?")
    assert len(L.run_row(results[0], "run", datetime.now())) == columns


def _column_index(name: str) -> int:
    columns = L.INSERT_PRICE_SQL.split("(", 1)[1].split(")", 1)[0]
    return [c.strip().strip('"')
            for c in columns.split(",")].index(name)


def test_repairs_are_serialised_as_json(results):
    malformed = next(r for r in results if r["symbol"] == "TATASTEEL.BO")
    repaired = next(r for r in malformed["rows"] if r["repaired"])
    tuple_row = L.price_row(repaired, "run", datetime.now())
    parsed = json.loads(tuple_row[_column_index("repairs")])
    assert parsed and parsed[0]["code"].startswith("repair_")


def test_quarantine_row_keeps_the_raw_date_as_text():
    bad = {"symbol": "X.BO", "reason": T.BAD_DATE_FORMAT, "detail": "d",
           "candle": {"date": "09/07/2026"}}
    assert L.quarantine_row(bad, "run", datetime.now())[2] == "09/07/2026"


def test_run_ids_are_unique():
    assert L.new_run_id() != L.new_run_id()


def test_schema_creates_the_four_tables(con):
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"daily_price", "quarantined_candle", "load_run", "run_metric"} <= names


def test_metrics_are_written_to_the_store(con, results):
    from ETL_Analysis import transform as T
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    L.write_result(con, reliance, "run-1")
    stored = con.scalar(
        "SELECT count(*) FROM run_metric WHERE symbol='RELIANCE.NS'")
    assert stored == len(T.metrics(reliance))
    assert stored > 15


def test_stored_metrics_keep_their_label_and_unit(con, results):
    L.write_result(con, results[0], "run-1")
    row = con.execute(
        "SELECT label, unit FROM run_metric WHERE metric='period_return_pct'"
    ).fetchall()[0]
    assert row[0] == "Return over period"
    assert row[1] == "pct"


def test_a_metric_value_round_trips(con, results):
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    L.write_result(con, reliance, "run-1")
    stored = con.execute(
        "SELECT value FROM run_metric "
        "WHERE symbol='RELIANCE.NS' AND metric='volatility_pct'"
    ).fetchall()[0][0]
    assert stored == pytest.approx(reliance["summary"]["volatility_pct"], abs=1e-4)


def test_rewriting_the_same_run_does_not_duplicate_metrics(con, results):
    L.write_result(con, results[0], "run-1")
    first = con.scalar("SELECT count(*) FROM run_metric")
    L.write_result(con, results[0], "run-1")
    assert con.scalar("SELECT count(*) FROM run_metric") == first


def test_a_second_run_keeps_both_sets_of_metrics(con, results):
    L.write_result(con, results[0], "run-1")
    L.write_result(con, results[0], "run-2")
    runs = con.execute("SELECT DISTINCT run_id FROM run_metric").fetchall()
    assert len(runs) == 2


def test_ensure_schema_is_safe_to_run_twice(con):
    L.ensure_schema(con)


def test_write_result_loads_clean_rows(con, results):
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    written = L.write_result(con, reliance, "run-1")
    assert written == 9
    assert con.scalar("SELECT count(*) FROM daily_price") == 9


def test_write_result_loads_quarantined_rows(con, results):
    malformed = next(r for r in results if r["symbol"] == "TATASTEEL.BO")
    L.write_result(con, malformed, "run-1")
    assert con.scalar("SELECT count(*) FROM quarantined_candle") == 3


def test_a_rerun_does_not_double_count(con, results):
    for result in results:
        L.write_result(con, result, "run-1")
    after_first = con.scalar("SELECT count(*) FROM daily_price")

    for result in results:
        L.write_result(con, result, "run-2")
    assert con.scalar("SELECT count(*) FROM daily_price") == after_first


def test_a_rerun_does_not_duplicate_quarantined_rows(con, results):
    for result in results:
        L.write_result(con, result, "run-1")
    after_first = con.scalar("SELECT count(*) FROM quarantined_candle")
    for result in results:
        L.write_result(con, result, "run-2")
    assert con.scalar("SELECT count(*) FROM quarantined_candle") == after_first


def test_a_rerun_records_a_second_ledger_row(con, results):
    L.write_result(con, results[0], "run-1")
    L.write_result(con, results[0], "run-2")
    assert con.scalar("SELECT count(*) FROM load_run") == 2


def test_reconciliation_passes_for_a_healthy_load(con, results):
    for result in results:
        L.write_result(con, result, "run-1")
    assert L.reconcile(con) == []


def test_reconciliation_catches_a_lost_row(con):
    con.execute(
        L.INSERT_RUN_SQL,
        ["run-x", "BROKEN.NS", True, 10, 4, 0, 3, None, None, None, None,
         datetime.now()],
    )
    failures = L.reconcile(con)
    assert len(failures) == 1
    assert failures[0][1] == "BROKEN.NS"


def test_loaded_row_carries_the_derived_exchange(con, results):
    for result in results:
        L.write_result(con, result, "run-1")
    rows = con.execute(
        "SELECT DISTINCT symbol, exchange FROM daily_price ORDER BY symbol"
    ).fetchall()
    assert ("TATASTEEL.BO", "BSE") in rows
    assert ("INFY.NS", "NSE") in rows


def test_null_volume_survives_the_round_trip(con, results):
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    L.write_result(con, infy, "run-1")
    nulls = con.execute(
        "SELECT count(*) FROM daily_price WHERE symbol='INFY.NS' AND volume IS NULL"
    ).fetchall()[0][0]
    assert nulls == 1


def test_repaired_rows_are_flagged_in_the_store(con, results):
    malformed = next(r for r in results if r["symbol"] == "TATASTEEL.BO")
    L.write_result(con, malformed, "run-1")
    flagged = con.scalar(
        "SELECT count(*) FROM daily_price WHERE repaired = 1")
    assert flagged == 3


def test_store_totals_match_the_transform_summary(con, results):
    for result in results:
        L.write_result(con, result, "run-1")
    expected = sum(r["summary"]["rows_kept"] for r in results)
    assert con.scalar("SELECT count(*) FROM daily_price") == expected
