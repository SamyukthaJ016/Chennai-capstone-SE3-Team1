from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import load as L
from ETL_Analysis import store as S
from ETL_Analysis import transform as T

FIXTURE_SYMBOLS = ["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM daily_price",
    "select symbol from daily_price",
    "  WITH x AS (SELECT 1) SELECT * FROM x  ",
    "FROM daily_price SELECT symbol",
    "DESCRIBE daily_price",
    "SHOW TABLES",
    "SUMMARIZE daily_price",
    "EXPLAIN SELECT 1",
    "PRAGMA database_list",
    "VALUES (1), (2)",
    "TABLE daily_price",
    "SELECT * FROM daily_price;",
    "SELECT * FROM daily_price;   ",
])
def test_a_read_statement_is_allowed(sql):
    assert S.check_query(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM daily_price",
    "DROP TABLE daily_price",
    "INSERT INTO daily_price VALUES (1)",
    "UPDATE daily_price SET close = 0",
    "CREATE TABLE t (a INT)",
    "ALTER TABLE daily_price ADD COLUMN x INT",
    "TRUNCATE daily_price",
])
def test_a_write_statement_is_refused(sql):
    with pytest.raises(S.UnsafeQuery):
        S.check_query(sql)


@pytest.mark.parametrize("sql", [
    "ATTACH 'other.duckdb' AS other",
    "INSTALL httpfs",
    "LOAD httpfs",
    "COPY daily_price TO 'out.csv'",
    "EXPORT DATABASE 'dump'",
    "SET memory_limit = '1GB'",
])
def test_a_statement_that_reaches_outside_the_file_is_refused(sql):
    with pytest.raises(S.UnsafeQuery):
        S.check_query(sql)


def test_a_write_hidden_behind_a_cte_is_refused():
    with pytest.raises(S.UnsafeQuery) as exc:
        S.check_query("WITH doomed AS (SELECT 1) DELETE FROM daily_price")
    assert "DELETE" in str(exc.value)


def test_a_second_statement_is_refused():
    with pytest.raises(S.UnsafeQuery) as exc:
        S.check_query("SELECT 1; DROP TABLE daily_price")
    assert "One statement" in str(exc.value)


def test_a_write_hidden_in_a_comment_is_refused():
    with pytest.raises(S.UnsafeQuery):
        S.check_query("SELECT 1 -- harmless\n; DROP TABLE daily_price")


def test_a_block_comment_does_not_hide_a_second_statement():
    with pytest.raises(S.UnsafeQuery):
        S.check_query("SELECT 1 /* nothing to see */ ; DROP TABLE daily_price")


def test_a_comment_before_a_read_statement_is_fine():
    assert S.check_query("-- what landed\nSELECT * FROM daily_price")


def test_an_empty_query_is_refused():
    for sql in ("", "   ", "\n\t"):
        with pytest.raises(S.UnsafeQuery):
            S.check_query(sql)


def test_a_query_that_is_only_comments_is_refused():
    with pytest.raises(S.UnsafeQuery) as exc:
        S.check_query("-- just thinking out loud")
    assert "only comments" in str(exc.value)


def test_the_refusal_names_what_was_wrong():
    with pytest.raises(S.UnsafeQuery) as exc:
        S.check_query("DROP TABLE daily_price")
    assert "DROP" in str(exc.value)


def test_the_statement_comes_back_without_its_trailing_semicolon():
    assert S.check_query("SELECT 1;").strip() == "SELECT 1"


def test_a_column_named_like_a_keyword_does_not_trip_the_guard():
    assert S.check_query("SELECT * FROM load_run")
    assert S.check_query("SELECT rows_updated_at FROM load_run")


def _record(**overrides) -> dict:
    record = {
        "symbol": "RELIANCE.NS", "trade_date": date(2026, 7, 1),
        "date_key": 20260701, "exchange": "NSE", "currency": "INR",
        "open": Decimal("100.5000"), "high": Decimal("102.0000"),
        "low": Decimal("99.0000"), "close": Decimal("101.2500"),
        "adj_close": Decimal("101.2500"), "volume": 1234,
        "price_range": Decimal("3.0000"), "price_change": Decimal("0.7500"),
        "daily_return_pct": Decimal("1.250000"),
        "turnover": Decimal("124942.5000"),
        "synthetic": False, "repaired": False, "repairs": "[]",
        "run_id": "RUN",
    }
    record.update(overrides)
    return record


def test_decimals_become_floats():
    row = S.price_row(_record())
    for key in ("open", "high", "low", "close", "adjclose", "turnover",
                "daily_return_pct", "range", "change"):
        assert isinstance(row[key], float), key


def test_the_row_uses_the_transform_vocabulary_not_the_table_vocabulary():
    row = S.price_row(_record())
    assert row["date"] == date(2026, 7, 1)
    assert row["range"] == 3.0
    assert row["change"] == 0.75
    assert "trade_date" not in row
    assert "price_range" not in row


def test_volume_comes_back_as_an_integer():
    assert S.price_row(_record(volume=1234))["volume"] == 1234
    assert isinstance(S.price_row(_record(volume=1234))["volume"], int)


def test_a_null_volume_stays_null():
    assert S.price_row(_record(volume=None))["volume"] is None


def test_flags_come_back_as_real_booleans():
    row = S.price_row(_record(synthetic=True, repaired=True))
    assert row["synthetic"] is True
    assert row["repaired"] is True


def test_repairs_json_is_parsed_back_into_a_list():
    payload = [{"code": "repair_volume", "detail": "sentinel"}]
    row = S.price_row(_record(repairs=json.dumps(payload)))
    assert row["repairs"] == payload


@pytest.mark.parametrize("value", [None, "", "not json", "{}", "7"])
def test_unreadable_repairs_text_becomes_an_empty_list(value):
    assert S.price_row(_record(repairs=value))["repairs"] == []


def test_a_timestamp_where_a_date_belongs_is_narrowed():
    assert S.price_row(
        _record(trade_date=datetime(2026, 7, 1, 9, 15)))["date"] == date(2026, 7, 1)


def test_an_iso_string_where_a_date_belongs_is_parsed():
    assert S.price_row(_record(trade_date="2026-07-01"))["date"] == date(2026, 7, 1)


def test_a_quarantine_record_keeps_the_original_candle():
    candle = {"date": "09/07/2026", "open": 1, "close": "n/a"}
    row = S.quarantine_row({
        "run_id": "RUN", "symbol": "X.BO", "raw_date": "09/07/2026",
        "reason": "NOT_A_NUMBER", "detail": "non-numeric close",
        "candle_json": json.dumps(candle),
    })
    assert row["candle"] == candle
    assert row["reason"] == "NOT_A_NUMBER"


def test_an_unparseable_candle_still_yields_a_quarantine_row():
    row = S.quarantine_row({
        "symbol": "X.BO", "raw_date": "09/07/2026", "reason": "BAD",
        "detail": "d", "candle_json": "{not json",
    })
    assert row["candle"]["date"] == "09/07/2026"
    assert row["reason"] == "BAD"


def test_records_are_grouped_into_one_result_per_symbol():
    records = [_record(symbol="A.NS"), _record(symbol="A.NS",
                                               trade_date=date(2026, 7, 2)),
               _record(symbol="B.NS")]
    results = S.build_results(records)
    assert {r["symbol"] for r in results} == {"A.NS", "B.NS"}
    assert len(next(r for r in results if r["symbol"] == "A.NS")["rows"]) == 2


def test_results_lead_with_the_biggest_mover():
    flat = [_record(symbol="FLAT.NS", trade_date=date(2026, 7, d),
                    close=Decimal("100.0")) for d in (1, 2)]
    mover = [_record(symbol="MOVER.NS", trade_date=date(2026, 7, 1),
                     close=Decimal("100.0")),
             _record(symbol="MOVER.NS", trade_date=date(2026, 7, 2),
                     close=Decimal("150.0"))]
    results = S.build_results(flat + mover)
    assert results[0]["symbol"] == "MOVER.NS"


def test_a_symbol_with_only_quarantined_rows_still_appears():
    results = S.build_results([], [{
        "symbol": "BAD.NS", "reason": "MISSING_FIELD", "detail": "no close",
        "candle_json": "{}", "run_id": "RUN",
    }])
    assert [r["symbol"] for r in results] == ["BAD.NS"]
    assert results[0]["summary"]["rows_quarantined"] == 1
    assert results[0]["rows"] == []


def test_counts_reconcile_without_a_ledger():
    results = S.build_results(
        [_record(symbol="A.NS")],
        [{"symbol": "A.NS", "reason": "R", "detail": "d", "candle_json": "{}"}])
    summary = results[0]["summary"]
    assert summary["candles_in"] == summary["rows_kept"] + summary["rows_quarantined"]


def test_a_ledger_count_overrides_the_rows_in_hand():
    results = S.build_results([_record(symbol="A.NS")], [],
                              candles_in={"A.NS": 99})
    assert results[0]["summary"]["candles_in"] == 99


def test_measures_are_recomputed_over_the_rows_given():
    rows = [_record(symbol="A.NS", trade_date=date(2026, 7, d),
                    close=Decimal(str(close)))
            for d, close in ((1, 100.0), (2, 110.0), (3, 121.0))]
    summary = S.build_results(rows)[0]["summary"]
    assert summary["period_return_pct"] == pytest.approx(21.0, abs=1e-6)
    assert summary["up_days"] == 2


def test_rows_are_sorted_by_date_however_they_arrived():
    rows = [_record(symbol="A.NS", trade_date=date(2026, 7, d))
            for d in (3, 1, 2)]
    charted = S.build_results(rows)[0]["rows"]
    assert [r["date"].day for r in charted] == [1, 2, 3]


@pytest.fixture(scope="module")
def duckdb():
    return pytest.importorskip("duckdb", reason="the read layer needs DuckDB")


@pytest.fixture(scope="module")
def loaded_store(duckdb, tmp_path_factory):
    path = tmp_path_factory.mktemp("store") / "warehouse.duckdb"
    payloads, _ = E.extract_many(FIXTURE_SYMBOLS)
    results = T.transform_many(payloads, repair=True)
    totals = L.load_many(results, db_path=str(path))
    return {"path": str(path), "results": results, "totals": totals}


@pytest.fixture
def handle(loaded_store):
    with S.connect(loaded_store["path"]) as opened:
        yield opened


def test_the_store_opens_and_has_every_table(handle):
    assert S.has_tables(handle)
    assert set(S.TABLES).issubset(S.schema(handle))


def test_it_opens_the_live_file_not_a_copy(handle):
    assert handle.used_snapshot is False


def test_a_missing_store_says_how_to_make_one(tmp_path):
    with pytest.raises(S.StoreUnavailable) as exc:
        S.connect(str(tmp_path / "nothing.duckdb"))
    assert "Run the pipeline first" in str(exc.value)


def test_the_connection_cannot_write(handle):
    with pytest.raises(Exception):
        handle.connection.execute("DELETE FROM daily_price")


def test_every_loaded_symbol_is_in_the_universe(handle):
    assert {row["symbol"] for row in S.universe(handle)} == set(FIXTURE_SYMBOLS)


def test_the_venue_is_derived_by_the_contract_rule(handle):
    venues = {row["symbol"]: row["exchange"] for row in S.universe(handle)}
    assert venues["RELIANCE.NS"] == "NSE"
    assert venues["TATASTEEL.BO"] == "BSE"


def test_the_latest_run_is_the_one_just_loaded(handle, loaded_store):
    assert S.latest_run_id(handle) == loaded_store["totals"]["run_id"]


def test_the_ledger_reconciles(handle):
    assert S.reconciliation(handle) == []


def test_the_run_rollup_totals_the_ledger(handle, loaded_store):
    run = S.runs(handle)[0]
    assert run["symbols"] == len(FIXTURE_SYMBOLS)
    assert run["rows_kept"] == loaded_store["totals"]["rows_loaded"]
    assert run["rows_quarantined"] == loaded_store["totals"]["rows_quarantined"]


def test_date_bounds_span_every_symbol(handle):
    lo, hi = S.date_bounds(handle)
    assert lo == date(2026, 7, 1)
    assert hi >= date(2026, 7, 9)


def _from_store(handle, symbol):
    return S.build_results(
        S.price_records(handle, symbols=[symbol]),
        S.quarantine_records(handle, symbols=[symbol]),
        candles_in=S.candles_in_by_symbol(handle),
    )[0]


ROUND_TRIP_COUNTS = ("candles_in", "rows_kept", "rows_quarantined",
                     "rows_repaired", "trading_days", "up_days", "down_days",
                     "date_from", "date_to")
ROUND_TRIP_MEASURES = ("close_first", "close_last", "close_min", "close_max",
                       "close_mean", "period_return_pct", "volatility_pct",
                       "max_drawdown_pct", "avg_daily_range_pct")


@pytest.mark.parametrize("symbol", FIXTURE_SYMBOLS)
def test_the_store_gives_back_the_measures_the_pipeline_put_in(
        handle, loaded_store, symbol):
    original = next(r for r in loaded_store["results"] if r["symbol"] == symbol)
    restored = _from_store(handle, symbol)

    for key in ROUND_TRIP_COUNTS:
        assert restored["summary"].get(key) == original["summary"].get(key), key
    for key in ROUND_TRIP_MEASURES:
        assert restored["summary"].get(key) == pytest.approx(
            original["summary"].get(key), abs=1e-4), key


@pytest.mark.parametrize("symbol", FIXTURE_SYMBOLS)
def test_the_rows_come_back_identical(handle, loaded_store, symbol):
    original = next(r for r in loaded_store["results"] if r["symbol"] == symbol)
    restored = _from_store(handle, symbol)
    assert len(restored["rows"]) == len(original["rows"])
    for was, now in zip(original["rows"], restored["rows"]):
        assert now["date"] == was["date"]
        assert now["close"] == pytest.approx(was["close"])
        assert now["volume"] == was["volume"]
        assert now["repaired"] == was["repaired"]
        assert now["synthetic"] == was["synthetic"]


def test_repairs_survive_the_round_trip(handle):
    restored = _from_store(handle, "TATASTEEL.BO")
    repaired = [r for r in restored["rows"] if r["repaired"]]
    assert len(repaired) == 3
    codes = {entry["code"] for row in repaired for entry in row["repairs"]}
    assert codes == {"repair_high_low", "repair_volume", "repair_date"}
    assert all(entry["detail"] for row in repaired for entry in row["repairs"])


def test_quarantined_candles_survive_the_round_trip(handle):
    restored = _from_store(handle, "TATASTEEL.BO")
    assert len(restored["quarantined"]) == 3
    assert {bad["reason"] for bad in restored["quarantined"]} == {
        "DUPLICATE_DATE", "MISSING_FIELD", "NOT_A_NUMBER"}


def test_filtering_by_symbol_returns_only_that_symbol(handle):
    records = S.price_records(handle, symbols=["INFY.NS"])
    assert {r["symbol"] for r in records} == {"INFY.NS"}


def test_a_symbol_from_the_wire_cannot_become_sql(handle):
    assert S.price_records(handle, symbols=["'; DROP TABLE daily_price; --"]) == []
    assert S.has_tables(handle)


def test_filtering_by_date_narrows_the_window(handle):
    records = S.price_records(handle, date_from=date(2026, 7, 3),
                              date_to=date(2026, 7, 7))
    assert records
    assert all(date(2026, 7, 3) <= r["trade_date"] <= date(2026, 7, 7)
               for r in records)


def test_excluding_repaired_rows_removes_exactly_those(handle):
    everything = S.price_records(handle, symbols=["TATASTEEL.BO"])
    observed = S.price_records(handle, symbols=["TATASTEEL.BO"],
                               exclude_repaired=True)
    assert len(everything) - len(observed) == 3
    assert not any(r["repaired"] for r in observed)


def test_excluding_synthetic_rows_removes_exactly_those(handle):
    everything = S.price_records(handle, symbols=["INFY.NS"])
    observed = S.price_records(handle, symbols=["INFY.NS"],
                               exclude_synthetic=True)
    assert len(everything) - len(observed) == sum(
        1 for r in everything if r["synthetic"])
    assert not any(r["synthetic"] for r in observed)


def test_measures_are_recomputed_when_repaired_rows_are_excluded(handle):
    everything = S.build_results(S.price_records(handle, symbols=["TATASTEEL.BO"]))
    observed = S.build_results(
        S.price_records(handle, symbols=["TATASTEEL.BO"], exclude_repaired=True))
    assert (observed[0]["summary"]["trading_days"]
            < everything[0]["summary"]["trading_days"])
    assert observed[0]["summary"]["rows_repaired"] == 0


def test_the_interval_is_part_of_the_grain(handle):
    records = S.price_records(handle, symbols=["RELIANCE.NS"])
    assert {r["interval"] for r in records} == {"1d"}
    assert S.intervals(handle) == ["1d"]


def test_filtering_by_interval_narrows_the_rows(handle):
    assert S.price_records(handle, interval="1d")
    assert S.price_records(handle, interval="1wk") == []


def test_a_second_interval_does_not_overwrite_the_first(duckdb, tmp_path):
    path = str(tmp_path / "w.duckdb")
    payloads, _ = E.extract_many(["RELIANCE.NS"])
    daily = T.transform_many(payloads)
    L.load_many(daily, db_path=path)

    weekly = T.transform_many(payloads)
    for result in weekly:
        for row in result["rows"]:
            row["interval"] = "1wk"
    L.load_many(weekly, db_path=path)

    with S.connect(path) as handle:
        assert sorted(S.intervals(handle)) == ["1d", "1wk"]
        assert len(S.price_records(handle, interval="1d")) == len(daily[0]["rows"])
        assert len(S.price_records(handle, interval="1wk")) == len(daily[0]["rows"])


def test_reloading_one_interval_is_still_idempotent(duckdb, tmp_path):
    path = str(tmp_path / "w.duckdb")
    payloads, _ = E.extract_many(["RELIANCE.NS"])
    results = T.transform_many(payloads)
    L.load_many(results, db_path=path)
    L.load_many(results, db_path=path)
    with S.connect(path) as handle:
        assert len(S.price_records(handle)) == len(results[0]["rows"])


def test_quarantine_reasons_are_counted(handle):
    reasons = {row["reason"]: row["rows_affected"]
               for row in S.quarantine_reasons(handle)}
    assert reasons == {"DUPLICATE_DATE": 1, "MISSING_FIELD": 1,
                       "NOT_A_NUMBER": 1}


def test_repair_records_name_every_repaired_row(handle):
    assert len(S.repair_records(handle, symbols=["TATASTEEL.BO"])) == 3


def test_every_stored_metric_is_offered_in_spec_order(handle):
    metrics = S.available_metrics(handle)
    keys = [key for key, _ in metrics]
    assert "period_return_pct" in keys
    spec_order = [key for key, _, _ in T.METRIC_SPEC if key in set(keys)]
    assert keys[:len(spec_order)] == spec_order


def test_metric_history_returns_a_value_per_symbol_per_run(handle):
    rows = S.metric_history(handle, "period_return_pct", FIXTURE_SYMBOLS)
    assert {row["symbol"] for row in rows} == set(FIXTURE_SYMBOLS)
    assert all(row["run_id"] for row in rows)


def test_metric_history_of_an_unknown_measure_is_empty(handle):
    assert S.metric_history(handle, "not_a_measure", FIXTURE_SYMBOLS) == []


def test_the_console_runs_a_read(handle):
    outcome = S.run_console_query(handle, "SELECT symbol FROM daily_price")
    assert outcome["columns"] == ["symbol"]
    assert outcome["rows"]
    assert outcome["truncated"] is False
    assert outcome["elapsed_ms"] >= 0


def test_the_console_caps_its_result(handle):
    outcome = S.run_console_query(handle, "SELECT * FROM daily_price",
                                  max_rows=5)
    assert len(outcome["rows"]) == 5
    assert outcome["truncated"] is True


def test_a_result_exactly_at_the_cap_is_not_called_truncated(handle):
    outcome = S.run_console_query(
        handle, "SELECT symbol FROM daily_price LIMIT 5", max_rows=5)
    assert len(outcome["rows"]) == 5
    assert outcome["truncated"] is False


def test_the_console_refuses_a_write_before_the_engine_sees_it(handle):
    with pytest.raises(S.UnsafeQuery):
        S.run_console_query(handle, "DROP TABLE daily_price")
    assert S.has_tables(handle)


def test_the_stamp_changes_when_the_store_is_written(duckdb, tmp_path):
    path = str(tmp_path / "w.duckdb")
    payloads, _ = E.extract_many(["RELIANCE.NS"])
    L.load_many(T.transform_many(payloads), db_path=path)
    before = S.store_stamp(path)

    L.load_many(T.transform_many(payloads), db_path=path)
    assert S.store_stamp(path) != before


def test_the_stamp_of_a_missing_store_is_stable(tmp_path):
    absent = str(tmp_path / "nothing.duckdb")
    assert S.store_stamp(absent) == S.store_stamp(absent)


def _runs_of(path):
    with S.connect(path) as opened:
        return S.runs(opened)


def test_a_read_does_not_hold_the_store_open(duckdb, tmp_path):
    path = str(tmp_path / "w.duckdb")
    payloads, _ = E.extract_many(["RELIANCE.NS"])
    results = T.transform_many(payloads)
    L.load_many(results, db_path=path)

    with S.connect(path) as opened:
        assert S.universe(opened)

    L.load_many(results, db_path=path)
    assert len(_runs_of(path)) == 2


@pytest.fixture
def locked_store(duckdb, tmp_path):
    path = str(tmp_path / "w.duckdb")
    payloads, _ = E.extract_many(["RELIANCE.NS"])
    L.load_many(T.transform_many(payloads), db_path=path)
    writer = duckdb.connect(path)
    try:
        yield path
    finally:
        writer.close()


def test_a_locked_store_either_reads_a_copy_or_explains_itself(locked_store):
    try:
        handle = S.connect(locked_store)
    except S.StoreUnavailable as exc:
        assert "pipeline run is probably writing" in str(exc)
        return
    with handle:
        assert handle.used_snapshot is True
        assert S.universe(handle)


def test_the_snapshot_fallback_can_be_refused(locked_store):
    with pytest.raises(S.StoreUnavailable):
        S.connect(locked_store, allow_snapshot=False)


def test_a_locked_store_is_not_retried_forever(locked_store):
    import time as clock
    started = clock.perf_counter()
    with pytest.raises(S.StoreUnavailable):
        S.connect(locked_store, allow_snapshot=False)
    budget = S.LOCK_RETRY_ATTEMPTS * S.LOCK_RETRY_SECONDS + 5
    assert clock.perf_counter() - started < budget
