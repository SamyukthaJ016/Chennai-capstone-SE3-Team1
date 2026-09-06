from __future__ import annotations

import pytest

from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import load as L
from ETL_Analysis import pipeline as P
from ETL_Analysis import report as R

@pytest.fixture
def db(tmp_path):
    pytest.importorskip("duckdb", reason="the load step writes DuckDB")
    return str(tmp_path / "warehouse.duckdb")


def test_a_run_loads_the_store_and_reports_success(db, capsys):
    assert P.run(P.DEFAULT_SYMBOLS, db_path=db) == 0
    printed = capsys.readouterr().out
    assert "RUN SUMMARY" in printed
    assert "rows loaded ........ 21" in printed


def test_a_run_says_how_to_open_the_dashboard(db, capsys):
    P.run(P.DEFAULT_SYMBOLS, db_path=db)
    assert "python -m ETL_Analysis.dashboard" in capsys.readouterr().out


def test_the_run_reconciles(db, capsys):
    P.run(P.DEFAULT_SYMBOLS, db_path=db)
    printed = capsys.readouterr().out
    assert "reconciled" in printed
    assert "RECONCILIATION FAILED" not in printed


def test_the_defaults_are_the_three_fixture_symbols():
    assert set(P.DEFAULT_SYMBOLS) == set(E.available_symbols())


def test_strict_mode_quarantines_what_repair_mode_fixes(db, capsys):
    P.run(["TATASTEEL.BO"], db_path=db, repair=False)
    printed = capsys.readouterr().out
    assert "rows loaded ........ 1" in printed
    assert "rows quarantined ... 6" in printed


def test_extract_is_injectable(db):
    called = []

    def fake_extract(symbol):
        called.append(symbol)
        return E.extract("RELIANCE.NS")

    assert P.run(["ANYTHING"], extract_fn=fake_extract, db_path=db) == 0
    assert called == ["ANYTHING"]


def test_one_failing_symbol_does_not_abandon_the_others(db, capsys):
    def flaky(symbol):
        if symbol == "BROKEN.NS":
            raise E.SymbolNotAvailable("no such symbol")
        return E.extract(symbol)

    assert P.run(["RELIANCE.NS", "BROKEN.NS"], extract_fn=flaky,
                 db_path=db) == 0
    printed = capsys.readouterr().out
    assert "symbols failed ..... 1" in printed
    assert "BROKEN.NS: no such symbol" in printed


def test_a_run_with_nothing_extracted_fails_loudly(db):
    def always_fails(symbol):
        raise E.SymbolNotAvailable("nope")

    assert P.run(["A.NS"], extract_fn=always_fails, db_path=db) == 1


def test_the_console_loader_needs_no_store(tmp_path, capsys):
    absent = str(tmp_path / "never-created.duckdb")
    assert P.run(["RELIANCE.NS"], to_console=True, db_path=absent) == 0
    assert "RELIANCE.NS" in capsys.readouterr().out
    assert not (tmp_path / "never-created.duckdb").exists()


def test_no_report_is_written_by_default(db, tmp_path):
    P.run(["RELIANCE.NS"], db_path=db)
    assert not list(tmp_path.glob("*.html"))


def test_the_legacy_report_is_written_when_asked(db, tmp_path):
    destination = tmp_path / "report.html"
    assert P.run(["RELIANCE.NS"], db_path=db, report_path=str(destination)) == 0
    assert destination.exists()
    assert destination.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_the_report_only_describes_data_that_landed(db, tmp_path):
    destination = tmp_path / "report.html"
    P.run(["TATASTEEL.BO"], db_path=db, report_path=str(destination))
    document = destination.read_text(encoding="utf-8")

    import duckdb

    with duckdb.connect(db, read_only=True) as connection:
        stored = connection.execute(
            "SELECT count(*) FROM daily_price").fetchone()[0]
    assert stored == 4
    assert "TATASTEEL.BO" in document


def test_the_interval_reaches_extract(db):
    seen = {}

    def fake_extract(symbol, interval=None):
        seen[symbol] = interval
        return E.extract("RELIANCE.NS")

    assert P.run(["A.NS"], extract_fn=fake_extract, db_path=db,
                 interval="1wk") == 0
    assert seen == {"A.NS": "1wk"}


def test_an_extract_without_an_interval_is_called_the_old_way(db):
    calls = []

    def fake_extract(symbol):
        calls.append(symbol)
        return E.extract("RELIANCE.NS")

    assert P.run(["A.NS"], extract_fn=fake_extract, db_path=db) == 0
    assert calls == ["A.NS"]


def test_rows_are_stamped_with_what_arrived_not_what_was_asked_for(db):
    import duckdb

    assert P.main(["--db", db, "--symbols", "RELIANCE.NS",
                   "--interval", "1wk"]) == 0
    with duckdb.connect(db, read_only=True) as connection:
        found = connection.execute(
            'SELECT DISTINCT "interval" FROM daily_price').fetchall()
    assert found == [("1d",)]


def test_listing_symbols_pulls_nothing(capsys):
    assert P.main(["--list-symbols"]) == 0
    printed = capsys.readouterr().out
    assert "symbol(s) in the universe" in printed
    assert "NSE" in printed


def test_the_cli_loads_the_store(db, capsys):
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS"]) == 0
    assert "rows loaded ........ 9" in capsys.readouterr().out


def test_legacy_report_with_no_path_uses_the_default(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS",
                   "--legacy-report"]) == 0
    assert (tmp_path / R.DEFAULT_REPORT_PATH).exists()


def test_legacy_report_takes_a_path(db, tmp_path):
    destination = tmp_path / "out" / "run.html"
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS",
                   "--legacy-report", str(destination)]) == 0
    assert destination.exists()


def test_omitting_legacy_report_writes_no_html(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS"]) == 0
    assert not list(tmp_path.glob("*.html"))


def test_the_dashboard_flag_launches_after_a_successful_run(db, monkeypatch):
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS", "--dashboard"]) == 0
    assert launched == [db]


def test_the_dashboard_is_not_launched_after_a_failed_run(db, monkeypatch):
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    monkeypatch.setattr(P.extract_fixtures, "extract",
                        lambda *a, **k: (_ for _ in ()).throw(
                            E.SymbolNotAvailable("nope")))
    assert P.main(["--db", db, "--symbols", "X.NS", "--dashboard"]) == 1
    assert launched == []


def test_the_dashboard_flag_refuses_the_console_loader(db, monkeypatch):
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS", "--print",
                   "--dashboard"]) == 1
    assert launched == []


def test_an_unknown_symbol_offline_fails_the_run(db):
    assert P.main(["--db", db, "--symbols", "NOTREAL.NS"]) == 1


def test_the_store_path_is_honoured(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    named = tmp_path / "somewhere-else.duckdb"
    assert P.main(["--db", str(named), "--symbols", "RELIANCE.NS"]) == 0
    assert named.exists()
    assert not (tmp_path / L.DEFAULT_DB_PATH).exists()
