"""Tests over the fourth module: the wiring.

`pipeline.py` does nothing but call the three steps and report which one
failed, so that is exactly what is checked here -- that extract is injectable,
that a failing symbol does not take the run down with it, that the flags mean
what the help text says, and that the exit code tells the truth.

Nothing here touches the network. The live client is never imported; where a
test needs extract to misbehave it passes a callable that does.
"""

from __future__ import annotations

import pytest

from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import load as L
from ETL_Analysis import pipeline as P
from ETL_Analysis import report as R

@pytest.fixture
def db(tmp_path):
    """A store path -- and the skip point for a machine without DuckDB.

    Guarding here rather than at module level keeps the flag parsing, the
    console loader and --list-symbols under test on a machine that has never
    installed a database.
    """
    pytest.importorskip("duckdb", reason="the load step writes DuckDB")
    return str(tmp_path / "warehouse.duckdb")


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_a_run_loads_the_store_and_reports_success(db, capsys):
    assert P.run(P.DEFAULT_SYMBOLS, db_path=db) == 0
    printed = capsys.readouterr().out
    assert "RUN SUMMARY" in printed
    assert "rows loaded ........ 21" in printed


def test_a_run_says_how_to_open_the_dashboard(db, capsys):
    """The run's output is where a teammate finds out the dashboard exists."""
    P.run(P.DEFAULT_SYMBOLS, db_path=db)
    assert "python -m ETL_Analysis.dashboard" in capsys.readouterr().out


def test_the_run_reconciles(db, capsys):
    P.run(P.DEFAULT_SYMBOLS, db_path=db)
    printed = capsys.readouterr().out
    assert "reconciled" in printed
    assert "RECONCILIATION FAILED" not in printed


def test_the_defaults_are_the_three_fixture_symbols():
    """Offline, the fixtures are the only symbols there are."""
    assert set(P.DEFAULT_SYMBOLS) == set(E.available_symbols())


def test_strict_mode_quarantines_what_repair_mode_fixes(db, capsys):
    P.run(["TATASTEEL.BO"], db_path=db, repair=False)
    printed = capsys.readouterr().out
    assert "rows loaded ........ 1" in printed
    assert "rows quarantined ... 6" in printed


# ---------------------------------------------------------------------------
# Extract is injected, and a bad symbol does not end the run
# ---------------------------------------------------------------------------

def test_extract_is_injectable(db):
    """The whole point of the split: --live swaps this callable and transform
    and load never learn about it."""
    called = []

    def fake_extract(symbol):
        called.append(symbol)
        return E.extract("RELIANCE.NS")

    assert P.run(["ANYTHING"], extract_fn=fake_extract, db_path=db) == 0
    assert called == ["ANYTHING"]


def test_one_failing_symbol_does_not_abandon_the_others(db, capsys):
    """Failing the run over one bad symbol would throw away eight good ones."""
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
    """An empty store that looks like a successful run is the worse failure."""
    def always_fails(symbol):
        raise E.SymbolNotAvailable("nope")

    assert P.run(["A.NS"], extract_fn=always_fails, db_path=db) == 1


# ---------------------------------------------------------------------------
# The console loader
# ---------------------------------------------------------------------------

def test_the_console_loader_needs_no_store(tmp_path, capsys):
    """--print keeps the pipeline demonstrable on a machine with no DuckDB."""
    absent = str(tmp_path / "never-created.duckdb")
    assert P.run(["RELIANCE.NS"], to_console=True, db_path=absent) == 0
    assert "RELIANCE.NS" in capsys.readouterr().out
    assert not (tmp_path / "never-created.duckdb").exists()


# ---------------------------------------------------------------------------
# The legacy report
# ---------------------------------------------------------------------------

def test_no_report_is_written_by_default(db, tmp_path):
    """The dashboard reads the store, so a run has nothing to render."""
    P.run(["RELIANCE.NS"], db_path=db)
    assert not list(tmp_path.glob("*.html"))


def test_the_legacy_report_is_written_when_asked(db, tmp_path):
    destination = tmp_path / "report.html"
    assert P.run(["RELIANCE.NS"], db_path=db, report_path=str(destination)) == 0
    assert destination.exists()
    assert destination.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_the_report_only_describes_data_that_landed(db, tmp_path):
    """Written after the load, so it can never describe a row that failed
    to be stored."""
    destination = tmp_path / "report.html"
    P.run(["TATASTEEL.BO"], db_path=db, report_path=str(destination))
    document = destination.read_text(encoding="utf-8")

    import duckdb

    with duckdb.connect(db, read_only=True) as connection:
        stored = connection.execute(
            "SELECT count(*) FROM daily_price").fetchone()[0]
    assert stored == 4
    assert "TATASTEEL.BO" in document


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

def test_the_interval_reaches_extract(db):
    """--interval is a request parameter, passed to whichever client is bound."""
    seen = {}

    def fake_extract(symbol, interval=None):
        seen[symbol] = interval
        return E.extract("RELIANCE.NS")

    assert P.run(["A.NS"], extract_fn=fake_extract, db_path=db,
                 interval="1wk") == 0
    assert seen == {"A.NS": "1wk"}


def test_an_extract_without_an_interval_is_called_the_old_way(db):
    """The offline client's signature must keep working unchanged."""
    calls = []

    def fake_extract(symbol):
        calls.append(symbol)
        return E.extract("RELIANCE.NS")

    assert P.run(["A.NS"], extract_fn=fake_extract, db_path=db) == 0
    assert calls == ["A.NS"]


def test_rows_are_stamped_with_what_arrived_not_what_was_asked_for(db):
    """The fixtures are daily. Asking for weekly offline must not relabel
    them -- the store would then claim a granularity it does not hold."""
    import duckdb

    assert P.main(["--db", db, "--symbols", "RELIANCE.NS",
                   "--interval", "1wk"]) == 0
    with duckdb.connect(db, read_only=True) as connection:
        found = connection.execute(
            'SELECT DISTINCT "interval" FROM daily_price').fetchall()
    assert found == [("1d",)]


def test_listing_symbols_pulls_nothing(capsys):
    """--list-symbols is free: it reads the file and exits."""
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
    """It launches the dashboard rather than rendering anything itself."""
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS", "--dashboard"]) == 0
    assert launched == [db]


def test_the_dashboard_is_not_launched_after_a_failed_run(db, monkeypatch):
    """Opening a dashboard over a store nothing was written to is a page of
    stale numbers presented as fresh ones."""
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    monkeypatch.setattr(P.extract_fixtures, "extract",
                        lambda *a, **k: (_ for _ in ()).throw(
                            E.SymbolNotAvailable("nope")))
    assert P.main(["--db", db, "--symbols", "X.NS", "--dashboard"]) == 1
    assert launched == []


def test_the_dashboard_flag_refuses_the_console_loader(db, monkeypatch):
    """--print writes to stdout, so there is no store for a dashboard to
    read. Opening one would show the PREVIOUS run's numbers."""
    launched = []
    monkeypatch.setattr(P.dashboard_module, "launch",
                        lambda path: launched.append(path) or 0)
    assert P.main(["--db", db, "--symbols", "RELIANCE.NS", "--print",
                   "--dashboard"]) == 1
    assert launched == []


def test_an_unknown_symbol_offline_fails_the_run(db):
    """Offline there are only fixtures, and a 404 is what a live run would
    get for the same request."""
    assert P.main(["--db", db, "--symbols", "NOTREAL.NS"]) == 1


def test_the_store_path_is_honoured(db, tmp_path, monkeypatch):
    """--db must write where it was told, not to the default beside the CWD."""
    monkeypatch.chdir(tmp_path)
    named = tmp_path / "somewhere-else.duckdb"
    assert P.main(["--db", str(named), "--symbols", "RELIANCE.NS"]) == 0
    assert named.exists()
    assert not (tmp_path / L.DEFAULT_DB_PATH).exists()
