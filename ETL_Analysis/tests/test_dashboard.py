"""Tests over the dashboard.

Two halves again. The presentation helpers are pure -- results in, rows and
strings out -- so what the page will show is asserted without rendering a
page. Then `streamlit.testing.v1.AppTest` renders the real app against a real
store and drives it, which is the only way to catch the failures that live in
the wiring: a widget that raises, a query that never runs, an entry point that
never reaches the page at all.

Both halves skip rather than pretend when their dependency is absent.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from ETL_Analysis import dashboard as D
from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import load as L
from ETL_Analysis import transform as T

FIXTURE_SYMBOLS = ["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"]


@pytest.fixture
def results():
    payloads, _ = E.extract_many(FIXTURE_SYMBOLS)
    return T.transform_many(payloads, repair=True)


@pytest.fixture
def malformed(results):
    return next(r for r in results if r["symbol"] == "TATASTEEL.BO")


# ===========================================================================
# Presentation helpers
# ===========================================================================

@pytest.mark.parametrize("value,expected", [
    (0, "0"),
    (999, "999"),
    (12_904, "12,904"),
    (1_290_400, "1.29m"),
    (2_500_000_000, "2.50bn"),
    (-1_500_000, "-1.50m"),
])
def test_large_figures_are_abbreviated_on_a_stat_tile(value, expected):
    assert D.compact(value) == expected


def test_a_missing_figure_is_a_dash_not_a_zero():
    """An unknown turnover is not a turnover of nothing."""
    assert D.compact(None) == "-"


def test_a_percentage_keeps_its_sign():
    assert D.compact(1.5, "pct") == "+1.50%"
    assert D.compact(-1.5, "pct") == "-1.50%"


def test_a_date_span_within_one_year_names_the_year_once():
    assert D.date_span(date(2026, 7, 1), date(2026, 7, 14)) == \
        "01 Jul - 14 Jul 2026"


def test_a_date_span_across_years_names_both():
    assert D.date_span(date(2025, 8, 26), date(2026, 8, 27)) == \
        "26 Aug 2025 - 27 Aug 2026"


def test_a_missing_date_span_is_a_dash():
    assert D.date_span(None, None) == "-"
    assert D.date_span(date(2026, 7, 1), None) == "-"


def test_values_are_formatted_the_same_way_as_in_the_report():
    """One formatter, so a number is written the same wherever it appears."""
    from ETL_Analysis import report as R
    for value, unit in ((1.5, "pct"), (2876.9, "price"), (5412700, "shares")):
        assert D.format_value(value, unit) == R.format_value(value, unit)


# ---------------------------------------------------------------------------
# totals_for
# ---------------------------------------------------------------------------

def test_totals_add_up_across_symbols(results):
    totals = D.totals_for(results)
    assert totals["symbols"] == 3
    assert totals["rows_loaded"] == sum(
        r["summary"]["rows_kept"] for r in results)
    assert totals["rows_quarantined"] == 3
    assert totals["rows_repaired"] == 3


def test_clean_rows_are_the_loaded_rows_that_were_not_repaired(results):
    totals = D.totals_for(results)
    assert totals["rows_clean"] == totals["rows_loaded"] - totals["rows_repaired"]


def test_the_totals_reconcile(results):
    """The invariant the whole design exists to keep visible."""
    totals = D.totals_for(results)
    assert totals["candles_in"] == (totals["rows_loaded"]
                                    + totals["rows_quarantined"])


def test_the_date_span_covers_every_symbol(results):
    totals = D.totals_for(results)
    assert totals["date_from"] == min(r["summary"]["date_from"] for r in results)
    assert totals["date_to"] == max(r["summary"]["date_to"] for r in results)


def test_advancers_and_decliners_are_counted_separately(results):
    totals = D.totals_for(results)
    returns = [r["summary"]["period_return_pct"] for r in results]
    assert totals["advancers"] == sum(1 for v in returns if v > 0)
    assert totals["decliners"] == sum(1 for v in returns if v < 0)


def test_totals_of_nothing_do_not_raise():
    """An over-narrow filter is a legitimate state, not an error."""
    totals = D.totals_for([])
    assert totals["symbols"] == 0
    assert totals["date_from"] is None


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def test_the_leaderboard_is_ordered_best_first(results):
    """The ordering is the point of the table."""
    rows = D.leaderboard_rows(results)
    returns = [row["Return %"] for row in rows]
    assert returns == sorted(returns, reverse=True)


def test_the_leaderboard_holds_every_symbol_with_rows(results):
    """Charts are capped; the table is not. Nothing is hidden."""
    assert {row["Symbol"] for row in D.leaderboard_rows(results)} == \
        set(FIXTURE_SYMBOLS)


def test_a_symbol_with_no_rows_is_left_out_of_the_leaderboard():
    """It has no return to rank on. The data-quality tab is where it shows."""
    empty = {"symbol": "X.NS", "currency": None, "rows": [], "quarantined": [],
             "summary": T.summarise_rows("X.NS", [], [], True)}
    assert D.leaderboard_rows([empty]) == []


def test_the_price_table_has_one_row_per_trading_day(malformed):
    assert len(D.price_table_rows(malformed)) == len(malformed["rows"])


def test_the_price_table_carries_the_provenance_flags(malformed):
    """A reader filtering for observed data needs both flags in the table,
    not only on the chart."""
    row = D.price_table_rows(malformed)[0]
    assert "Synthetic" in row
    assert "Repaired" in row


def test_the_repair_table_has_one_row_per_repair(results):
    """Not per repaired row: a row can carry two repairs."""
    rows = D.repair_table_rows(results)
    expected = sum(len(row["repairs"]) for result in results
                   for row in result["rows"] if row["repaired"])
    assert len(rows) == expected


def test_every_repair_says_what_changed(results):
    for row in D.repair_table_rows(results):
        assert row["Repair"]
        assert row["What changed"]


def test_the_quarantine_table_keeps_the_date_as_it_arrived(results):
    """A row rejected for a bad date has no valid date to key on, so the
    table has to show the text that came off the wire."""
    rows = D.quarantine_table_rows(results)
    assert len(rows) == 3
    assert all(row["Reason"] for row in rows)


def test_measure_cards_leave_out_the_row_counts(results):
    """Dispositions are not measures; the data-quality tab is their home."""
    keys = {card["metric"] for card in D.measure_cards(results[0])}
    assert "period_return_pct" in keys
    assert "rows_quarantined" not in keys
    assert "candles_in" not in keys


def test_every_measure_card_is_labelled_and_formatted(results):
    for card in D.measure_cards(results[0]):
        assert card["label"]
        assert card["value"] and card["value"] != "None"


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------

def test_running_with_no_symbols_is_refused_not_attempted():
    outcome = D.run_pipeline_from_app("x.duckdb", ["  ", ""], None)
    assert outcome["ok"] is False
    assert "at least one symbol" in outcome["message"]


def test_the_run_message_names_the_interval():
    from ETL_Analysis import pipeline as P
    calls = {}

    def fake_run(symbols, **kwargs):
        calls.update(kwargs, symbols=symbols)
        return 0

    original = P.run
    P.run = fake_run
    try:
        outcome = D.run_pipeline_from_app("x.duckdb", ["A.NS"], "1wk")
    finally:
        P.run = original
    assert outcome["ok"] is True
    assert "1wk" in outcome["message"]
    assert calls["interval"] == "1wk"


def test_a_symbol_from_the_wire_cannot_inject_markup():
    """Everything the page interpolates goes through the same escaper."""
    tile = D.stat_tile("<b>k</b>", "<script>x</script>")
    assert "<script>x</script>" not in tile
    assert "&lt;script&gt;" in tile


def test_the_masthead_names_the_store_and_the_run():
    head = D.masthead("w.duckdb", "RUN-1", None)
    assert "w.duckdb" in head
    assert "RUN-1" in head
    assert "never" in head


def test_the_masthead_survives_a_store_that_has_never_been_loaded():
    assert "none" in D.masthead("w.duckdb", None, None)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def test_the_launch_command_runs_this_file_under_streamlit():
    command = D.launch_command("my.duckdb")
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4].endswith("dashboard.py")
    assert command[-2:] == ["--db", "my.duckdb"]


def test_the_launch_command_pins_the_theme():
    """So the dashboard looks the same whatever the reader's own streamlit
    settings say, and whatever directory it is started from."""
    command = D.launch_command("my.duckdb")
    assert "--theme.base" in command
    assert command[command.index("--theme.base") + 1] == "light"


def test_the_port_and_headless_flags_are_passed_through():
    command = D.launch_command("my.duckdb", port=8765, headless=True)
    assert command[command.index("--server.port") + 1] == "8765"
    assert command[command.index("--server.headless") + 1] == "true"


def test_a_child_process_refuses_to_launch_another(monkeypatch, capsys):
    """A misdetection would otherwise fork an unbounded chain of servers,
    each waiting on the next."""
    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    assert D.launch("my.duckdb") == 1
    assert "refusing to start another" in capsys.readouterr().err


def test_the_defaults_point_at_the_pipeline_s_own_store():
    assert D.parse_args([]).db == L.DEFAULT_DB_PATH
    assert D.parse_args(["--db", "x.duckdb"]).db == "x.duckdb"


# ===========================================================================
# The rendered app, driven end to end.
# ===========================================================================

DASHBOARD_FILE = str(Path(D.__file__).resolve())


@pytest.fixture(scope="module")
def app_test():
    """The AppTest class -- and the skip point for a machine without the
    optional dependencies. Guarding here rather than at module level keeps
    every pure helper above under test on a bare install."""
    pytest.importorskip("duckdb", reason="the dashboard reads a DuckDB store")
    return pytest.importorskip(
        "streamlit.testing.v1",
        reason="rendering the app needs streamlit").AppTest


@pytest.fixture(scope="module")
def store_path(app_test, tmp_path_factory):
    path = tmp_path_factory.mktemp("dash") / "warehouse.duckdb"
    payloads, _ = E.extract_many(FIXTURE_SYMBOLS)
    L.load_many(T.transform_many(payloads, repair=True), db_path=str(path))
    return str(path)


@pytest.fixture
def app(app_test, store_path, monkeypatch):
    """The real app, rendered against a real store.

    CHILD_ENV_VAR is set so that a regression in the "am I inside streamlit"
    check fails as a refusal rather than by forking a server and hanging the
    suite.
    """
    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", store_path])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=120)
    at.run()
    return at


def test_the_app_renders_without_raising(app):
    assert not app.exception
    assert not app.error


def test_the_entry_point_reaches_the_page(app):
    """`sys.exit()` inside streamlit's script runner never finishes the run,
    so the page comes out blank. This is the test that catches that."""
    assert len(app.markdown) > 10


def test_every_tab_is_present(app):
    assert [tab.label for tab in app.tabs] == [
        "Overview", "Claims", "Instrument", "Data quality", "Runs",
        "SQL console"]


def test_the_rail_scopes_the_whole_page(app):
    labels = [m.label for m in app.multiselect]
    assert "Venue" in labels
    assert any(label.startswith("Symbols (") for label in labels)


def test_the_provenance_filters_are_offered(app):
    labels = [box.label for box in app.checkbox]
    assert "Exclude repaired rows" in labels
    assert "Exclude vendor-interpolated rows" in labels


def test_the_run_form_is_offered(app):
    """The pipeline can be re-run from the page, with an interval."""
    labels = [t.label for t in app.text_input]
    assert "Interval to request" in labels
    assert "Symbols" in labels
    assert any("Run the pipeline" in (b.label or "") for b in app.button)


def test_running_the_pipeline_from_the_page_loads_and_refreshes(
        app_test, tmp_path, monkeypatch):
    """The whole feature: press the button, the store grows, and the page is
    showing the new rows rather than the cached old ones."""
    from ETL_Analysis import extract_fixtures as EF, load as LD, store as ST

    db = str(tmp_path / "w.duckdb")
    LD.load_many(T.transform_many(EF.extract_many(["RELIANCE.NS"])[0]),
                 db_path=db)

    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", db])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=180)
    at.run()
    assert at.dataframe[0].value.shape[0] == 1

    next(t for t in at.text_input if t.label == "Symbols").set_value(
        "RELIANCE.NS INFY.NS TATASTEEL.BO")
    next(b for b in at.button
         if "Run the pipeline" in (b.label or "")).click().run()

    assert not at.exception
    assert any("Loaded 3 symbol" in m.value for m in at.success)
    assert at.dataframe[0].value.shape[0] == 3
    with ST.connect(db) as handle:
        assert len(ST.runs(handle)) == 2


def test_a_failing_run_reports_instead_of_crashing_the_page(
        app_test, tmp_path, monkeypatch):
    """A button has no stderr. A run that fails must leave a sentence, not a
    half-rendered page."""
    from ETL_Analysis import extract_fixtures as EF, load as LD

    db = str(tmp_path / "w.duckdb")
    LD.load_many(T.transform_many(EF.extract_many(["RELIANCE.NS"])[0]),
                 db_path=db)
    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", db])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=180)
    at.run()

    next(t for t in at.text_input if t.label == "Symbols").set_value("NOPE.NS")
    next(b for b in at.button
         if "Run the pipeline" in (b.label or "")).click().run()
    assert not at.exception
    assert at.error


def test_the_claims_tab_says_it_ignores_the_rail(app):
    """A reader who filters to six symbols and sees the claims unchanged has
    to be told why, or the page looks broken."""
    assert any("ignores the filters in the rail" in m.value
               for m in app.markdown)


def test_the_claims_tab_says_nothing_is_hard_coded(app):
    """The claims are computed from the store, so the page says so -- a
    reader has to know the sentences move with the data."""
    assert any("None of the numbers is typed" in m.value
               for m in app.markdown)


def test_a_thin_store_reports_its_claims_as_unsupported(app):
    """The app fixture is three fixture symbols over two weeks. That cannot
    support a claim about a market, and the page must say so rather than
    render a confident sentence about twelve rows."""
    assert any("cannot support every claim" in w.value for w in app.warning)


def test_a_rich_store_states_its_claims_on_the_page(
        app_test, tmp_path, monkeypatch):
    """The other half: given data that supports them, the generated claims
    are rendered with their computed figures."""
    from ETL_Analysis import claims as claims_module
    from ETL_Analysis import store as store_module
    # `tests/` is not a package, so pytest puts this directory on sys.path
    # and the sibling module imports by its bare name.
    from test_claims import _synthetic_store

    db = _synthetic_store(tmp_path / "rich.duckdb")
    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", db])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=180)
    at.run()

    assert not at.exception
    with store_module.connect(db) as handle:
        findings = [f for f in claims_module.generate(handle) if f.available]
    assert findings, "the synthetic store should support claims"

    page = " ".join(m.value for m in at.markdown)
    for index, finding in enumerate(findings, start=1):
        assert f"Claim {index}" in page
        assert finding.headline in page


def test_the_page_reports_the_reconciliation_outcome(app):
    assert any("Balanced" in m.value for m in app.markdown)


def test_the_page_carries_the_educational_disclaimer(app):
    assert any("not for investment use" in m.value.lower()
               for m in app.markdown)


def test_every_chart_has_a_table_beside_it(app):
    """The relief rule: three of the six series colours sit below 3:1 against
    the page, so the numbers must also be readable as text."""
    assert len(app.dataframe) >= 4


def test_the_tables_can_be_taken_away(app):
    assert len(app.get("download_button")) >= 3


def _leaderboard(app):
    """The Overview tab's ranked table, which is the first one rendered."""
    return app.dataframe[0].value


def test_excluding_repaired_rows_changes_what_is_shown(app):
    """The filter has to reach the QUERY, not merely toggle a widget."""
    before = _leaderboard(app)
    was = before.loc[before["Symbol"] == "TATASTEEL.BO"].iloc[0]
    assert was["Repaired"] == 3

    box = next(c for c in app.checkbox if c.label == "Exclude repaired rows")
    after = box.check().run()
    assert not after.exception

    now = _leaderboard(after)
    row = now.loc[now["Symbol"] == "TATASTEEL.BO"].iloc[0]
    assert row["Repaired"] == 0
    assert row["Trading days"] == was["Trading days"] - 3


def test_excluding_repaired_rows_recomputes_the_measures(app):
    """A filtered chart beside an unfiltered number is the failure this
    guards against."""
    before = _leaderboard(app)
    was = before.loc[before["Symbol"] == "TATASTEEL.BO"].iloc[0]["Return %"]

    box = next(c for c in app.checkbox if c.label == "Exclude repaired rows")
    after = box.check().run()
    now = _leaderboard(after)
    assert now.loc[now["Symbol"] == "TATASTEEL.BO"].iloc[0]["Return %"] != was


def test_the_page_says_when_rows_are_being_excluded(app):
    """A number computed over a subset must not be presented as the whole."""
    box = next(c for c in app.checkbox if c.label == "Exclude repaired rows")
    after = box.check().run()
    assert any("Excluding repaired rows" in m.value for m in after.markdown)


def test_the_console_runs_the_query_in_the_box(app):
    """`AppTest.run()` mutates and returns the SAME object, so the count has
    to be taken before the click rather than off `app` afterwards."""
    before = len(app.dataframe)
    button = next(b for b in app.button if b.label == "Run query")
    after = button.click().run()
    assert not after.exception
    assert not after.error
    assert len(after.dataframe) == before + 1

    results = after.dataframe[-1].value
    assert list(results.columns) == ["symbol", "trading_days", "first_day",
                                     "last_day"]
    assert set(results["symbol"]) == set(FIXTURE_SYMBOLS)


def test_the_console_refuses_a_write_and_says_why(app):
    app.text_area(key="sql").set_value("DROP TABLE daily_price").run()
    button = next(b for b in app.button if b.label == "Run query")
    after = button.click().run()
    assert not after.exception
    assert any("DROP" in message.value for message in after.error)


def test_the_console_reports_a_broken_query_without_crashing(app):
    app.text_area(key="sql").set_value("SELECT * FROM no_such_table").run()
    button = next(b for b in app.button if b.label == "Run query")
    after = button.click().run()
    assert not after.exception
    assert after.error


def test_an_example_query_can_be_loaded_into_the_box(app):
    picker = next(s for s in app.selectbox
                  if s.label == "Start from an example")
    picker.set_value("Reconciliation check").run()
    loader = next(b for b in app.button if b.label == "Load this example")
    after = loader.click().run()
    assert not after.exception
    assert "candles_in <> rows_kept" in after.text_area(key="sql").value


def test_every_example_query_is_accepted_by_the_guard():
    """A console whose own examples are refused is a console nobody trusts."""
    from ETL_Analysis import store as S
    for title, sql in D.EXAMPLE_QUERIES:
        assert S.check_query(sql), title


def test_every_example_query_actually_runs(store_path):
    from ETL_Analysis import store as S
    with S.connect(store_path) as handle:
        for title, sql in D.EXAMPLE_QUERIES:
            outcome = S.run_console_query(handle, sql)
            assert outcome["columns"], title


def test_switching_instrument_redraws_the_page(app):
    picker = next(s for s in app.selectbox if s.label == "Instrument")
    other = [option for option in picker.options if option != picker.value]
    after = picker.set_value(other[0]).run()
    assert not after.exception
    assert any(other[0] in m.value for m in after.markdown)


def test_plotly_availability_is_checked_rather_than_assumed():
    assert isinstance(D.plotly_available(), bool)


def test_the_page_degrades_instead_of_crashing_without_plotly(
        app_test, store_path, monkeypatch):
    """`st.plotly_chart` reaches for `plotly.tools`, so a missing plotly used
    to surface as a traceback in the middle of the page. Every chart here has
    a table beside it, so the right answer is a message and the rest of the
    page, not a stack trace.

    Blocked through `sys.meta_path` rather than by monkeypatching the module:
    streamlit runs the file as `__main__`, so the function object the page
    calls is not the one `import ETL_Analysis.dashboard` binds.
    """
    class Block:
        def find_spec(self, name, path=None, target=None):
            if name.startswith("plotly"):
                raise ImportError(f"blocked: {name}")
            return None

    for name in [n for n in sys.modules if n.startswith("plotly")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [Block()] + sys.meta_path)

    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", store_path])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=120)
    at.run()

    assert not at.exception
    assert any("pip install plotly" in message.value
               for message in at.warning)
    # The numbers are still there, which is the point of degrading.
    assert at.dataframe
    assert any("not for investment use" in m.value.lower() for m in at.markdown)


def test_a_store_that_does_not_exist_is_explained_not_crashed(
        app_test, tmp_path, monkeypatch):
    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    missing = str(tmp_path / "nothing.duckdb")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", missing])
    at = app_test.from_file(DASHBOARD_FILE, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Run the pipeline first" in message.value
               for message in at.error)


def test_a_new_run_is_picked_up_without_restarting_the_app(
        app_test, store_path, monkeypatch):
    """The whole point of a dashboard over a report: it is current because
    the store changed, not because anything regenerated a file."""
    from ETL_Analysis import store as S

    monkeypatch.setenv(D.CHILD_ENV_VAR, "1")
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", store_path])

    at = app_test.from_file(DASHBOARD_FILE, default_timeout=120)
    at.run()
    assert not at.exception
    before = S.store_stamp(store_path)

    payloads, _ = E.extract_many(["RELIANCE.NS"])
    L.load_many(T.transform_many(payloads), db_path=store_path)
    assert S.store_stamp(store_path) != before

    at.run()
    assert not at.exception
    with S.connect(store_path) as handle:
        assert len(S.runs(handle)) == 2
