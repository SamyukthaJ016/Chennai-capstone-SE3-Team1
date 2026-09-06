"""Tests over the analytical measures and the Plotly report.

The measures are checked against independent computations -- `statistics` for
the standard deviation, brute force for the drawdown -- rather than against
themselves, so a wrong formula fails rather than being confirmed by its own
output.

The report is tested at its FIGURE layer: every chart is built as a plain
`{"data": [...], "layout": {...}}` dict by a pure function, so trace counts,
x/y values, date handling and axis titles are all checked directly. Only
`_render` touches plotly, and `conftest.py` stubs it when plotly is absent so
the suite runs either way -- the stub imitates plotly's own output shape, so
the assembly assertions (fragments not documents, bundle embedded once, no
script fetched over the network) mean the same thing with or without it.

Assertions against the rendered document go through the `html` fixture rather
than `assert x in document`. The inline bundle makes that string ~3.6MB, and
pytest builds a failing `in` assertion's message by running difflib over the
whole thing -- which never finishes, so a stale assertion looks like a hung
suite. See `conftest.HtmlDoc`.
"""

from __future__ import annotations

import json
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import date, datetime

import pytest

from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import report as R
from ETL_Analysis import transform as T

TOLERANCE = 1e-3  # measures are stored rounded to 4dp


@pytest.fixture
def results():
    payloads, _ = E.extract_many(["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"])
    return T.transform_many(payloads, repair=True)


@pytest.fixture
def reliance(results):
    return next(r for r in results if r["symbol"] == "RELIANCE.NS")


@pytest.fixture
def document(results):
    return R.build_report(results, "TESTRUN", T.metrics,
                          generated_at=datetime(2026, 8, 26, 12, 0))


# ---------------------------------------------------------------------------
# The measures, against independent computations
# ---------------------------------------------------------------------------

def test_volatility_matches_the_statistics_module(reliance):
    returns = [r["daily_return_pct"] for r in reliance["rows"]
               if r["daily_return_pct"] is not None]
    assert reliance["summary"]["volatility_pct"] == pytest.approx(
        statistics.stdev(returns), abs=TOLERANCE)


def test_volatility_is_none_with_fewer_than_two_returns():
    """Standard deviation of one point is undefined, not zero."""
    assert T._stdev([1.0]) is None
    assert T._stdev([]) is None


def test_max_drawdown_matches_brute_force(reliance):
    """Worst peak-to-trough fall, checked against every (i, j) pair."""
    closes = [r["close"] for r in reliance["rows"]]
    worst = 0.0
    for i in range(len(closes)):
        for j in range(i + 1, len(closes)):
            worst = min(worst, (closes[j] - closes[i]) / closes[i] * 100)
    assert reliance["summary"]["max_drawdown_pct"] == pytest.approx(
        worst, abs=TOLERANCE)


def test_max_drawdown_is_zero_for_a_series_that_only_rises():
    assert T._max_drawdown_pct([100.0, 101.0, 102.0]) == 0.0


def test_max_drawdown_is_negative_for_a_series_that_falls():
    assert T._max_drawdown_pct([100.0, 90.0]) == pytest.approx(-10.0, abs=1e-4)


def test_period_return_matches_first_and_last_close(reliance):
    closes = [r["close"] for r in reliance["rows"]]
    expected = (closes[-1] - closes[0]) / closes[0] * 100
    assert reliance["summary"]["period_return_pct"] == pytest.approx(
        expected, abs=TOLERANCE)


def test_up_down_and_flat_days_account_for_every_return(results):
    for result in results:
        s = result["summary"]
        returns = [r["daily_return_pct"] for r in result["rows"]
                   if r["daily_return_pct"] is not None]
        if returns:
            assert s["up_days"] + s["down_days"] + s["flat_days"] == len(returns)


def test_best_and_worst_day_name_the_right_dates(reliance):
    rows = reliance["rows"]
    s = reliance["summary"]
    best_row = next(r for r in rows if r["date"] == s["best_day"])
    assert best_row["daily_return_pct"] == s["best_day_pct"]
    assert s["best_day_pct"] >= s["worst_day_pct"]


def test_observed_rows_excludes_repaired_and_synthetic(results):
    for result in results:
        s = result["summary"]
        observed = [r for r in result["rows"]
                    if not r["repaired"] and not r["synthetic"]]
        assert s["observed_rows"] == len(observed)


def test_total_turnover_skips_rows_with_no_volume(results):
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    expected = sum(r["turnover"] for r in infy["rows"]
                   if r["turnover"] is not None)
    assert infy["summary"]["total_turnover"] == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# The metric list
# ---------------------------------------------------------------------------

def test_metrics_are_produced_for_every_symbol(results):
    for result in results:
        assert T.metrics(result), result["symbol"]


def test_every_metric_has_a_label_and_a_unit(results):
    for result in results:
        for metric in T.metrics(result):
            assert metric["label"]
            assert metric["unit"] in {
                "price", "pct", "shares", "currency", "days", "rows"}
            assert isinstance(metric["value"], float)


def test_metric_keys_are_unique_within_a_symbol(results):
    for result in results:
        keys = [m["metric"] for m in T.metrics(result)]
        assert len(keys) == len(set(keys))


def test_metrics_omit_measures_that_could_not_be_computed():
    """A one-row payload has no returns, so no volatility. It must be absent
    rather than stored as zero, which would read as 'this never moves'."""
    payload = {"data": {"symbol": "ONE.NS", "candles": [
        {"date": "2026-07-01", "open": 100.0, "high": 105.0,
         "low": 99.0, "close": 103.0, "volume": 10},
    ]}}
    keys = {m["metric"] for m in T.metrics(T.transform(payload))}
    assert "volatility_pct" not in keys
    assert "close_last" in keys


def test_a_symbol_with_no_clean_rows_still_yields_count_metrics():
    payload = {"data": {"symbol": "BAD.NS", "candles": [
        {"date": "nope", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
    ]}}
    keys = {m["metric"] for m in T.metrics(T.transform(payload, repair=False))}
    assert "rows_quarantined" in keys


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,unit,expected", [
    (1.5, "pct", "+1.50%"),
    (-1.5, "pct", "-1.50%"),
    (2876.9, "price", "2,876.90"),
    (5412700, "shares", "5,412,700"),
    (9, "days", "9"),
])
def test_values_are_formatted_by_unit(value, unit, expected):
    assert R.format_value(value, unit) == expected


def test_large_currency_values_are_abbreviated():
    assert R.format_value(173_310_731_890, "currency") == "173.31bn"
    assert R.format_value(5_000_000, "currency") == "5.00m"


def test_a_missing_value_formats_as_a_dash():
    assert R.format_value(None, "price") == "-"


# ---------------------------------------------------------------------------
# Figure specs -- the layer where a wrong number would actually live
# ---------------------------------------------------------------------------

def test_comparison_figure_has_one_trace_per_symbol(results):
    figure, trimmed = R.comparison_figure(results)
    assert len(figure["data"]) == 3
    assert trimmed is False


def test_every_series_is_rebased_to_100_at_its_own_first_day(results):
    figure, _ = R.comparison_figure(results)
    for trace in figure["data"]:
        assert trace["y"][0] == 100.0


def test_the_comparison_x_axis_is_a_real_date_axis(results):
    """A date axis spaces a two-day gap as two days. A category axis would
    draw consecutive points evenly however far apart the dates are."""
    figure, _ = R.comparison_figure(results)
    assert figure["layout"]["xaxis"]["type"] == "date"


def test_each_series_carries_its_own_dates(results):
    """Symbols trade on different days. A shared index would put one symbol's
    fourth point on another symbol's fourth date."""
    figure, _ = R.comparison_figure(results)
    for result in results:
        symbol = result["summary"]["symbol"]
        trace = next(t for t in figure["data"] if t["name"] == symbol)
        assert trace["x"] == [r["date"].isoformat() for r in result["rows"]]


def test_quality_figure_stacks_to_the_candles_received(results):
    """The reconciliation invariant, drawn: the bar length is what arrived."""
    figure = R.quality_figure(results)
    assert figure["layout"]["barmode"] == "stack"
    for index, result in enumerate(results):
        total = sum(trace["x"][index] for trace in figure["data"])
        assert total == result["summary"]["candles_in"]


def test_close_figure_title_states_the_finding(results):
    """Not "RELIANCE.NS closing price" -- what the reader should take away."""
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    title = R.close_figure(reliance)["layout"]["title"]["text"]
    assert "RELIANCE.NS" in title
    assert "rose" in title or "fell" in title
    assert "%" in title


def _markers(figure) -> list:
    """Every point marker in a per-symbol price figure, in date order.

    The figure carries one trace per calendar quarter, always Q1..Q4 in that
    order, so a symbol whose data is all in July has three empty traces and
    one full one. Reading `data[0]` would read Q1 and see nothing.
    """
    return [symbol for trace in figure["data"]
            for symbol in trace["marker"]["symbol"]]


def _series(figure, key) -> list:
    """One axis of a quarter-split figure, flattened back to a single series."""
    return [value for trace in figure["data"] for value in trace[key]]


def test_close_figure_has_one_trace_per_calendar_quarter(results):
    """The quarter buttons address traces by position, so the four buckets
    must always be present and always in Q1..Q4 order -- including the empty
    ones. This is what `_markers` and `_series` above rely on."""
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    figure = R.close_figure(reliance)
    assert [trace["name"] for trace in figure["data"]] == list(R.QUARTER_LABELS)
    # July is Q3, so only the third bucket holds anything.
    assert [len(trace["x"]) for trace in figure["data"]][:2] == [0, 0]


def test_repaired_points_are_marked_on_the_price_chart(results):
    """A reader must be able to see which points were corrected."""
    malformed = next(r for r in results if r["symbol"] == "TATASTEEL.BO")
    assert _markers(R.close_figure(malformed)).count("diamond-open") == 3


def test_clean_symbols_have_no_marked_points(results):
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    assert set(_markers(R.close_figure(reliance))) == {"circle"}


def test_a_missing_volume_stays_null_rather_than_becoming_zero(results):
    """A zero bar would claim a day with no trading. Null leaves a gap."""
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    volumes = _series(R.volume_figure(infy), "y")
    assert None in volumes
    assert 0 not in volumes


def test_a_missing_volume_is_explained_on_the_chart(results):
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    note = R.volume_figure(infy)["layout"]["annotations"][0]["text"]
    assert "not drawn as zero" in note


def test_a_symbol_with_no_missing_volume_gets_no_annotation(results):
    reliance = next(r for r in results if r["symbol"] == "RELIANCE.NS")
    assert "annotations" not in R.volume_figure(reliance)["layout"]


def test_every_axis_on_every_figure_is_titled(results):
    """The sprint's readability bar: a non-technical reader, unaided."""
    figures = [R.comparison_figure(results)[0], R.quality_figure(results)]
    for result in results:
        figures += [R.close_figure(result), R.volume_figure(result)]
    for figure in figures:
        for axis in ("xaxis", "yaxis"):
            assert figure["layout"][axis]["title"]["text"]


def test_every_figure_is_json_serialisable(results):
    """Plotly serialises the figure to JSON in the page; a stray date or
    Decimal would blow up at render time rather than here."""
    figures = [R.comparison_figure(results)[0], R.quality_figure(results)]
    for result in results:
        figures += [R.close_figure(result), R.volume_figure(result)]
    for figure in figures:
        json.dumps(figure)


def test_figures_are_none_for_a_symbol_with_no_rows():
    empty = {"symbol": "X.NS", "currency": "INR", "rows": [], "quarantined": [],
             "summary": {"symbol": "X.NS", "candles_in": 0, "rows_kept": 0,
                         "rows_quarantined": 0}}
    assert R.close_figure(empty) is None
    assert R.volume_figure(empty) is None
    assert R.comparison_figure([empty]) == (None, False)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def test_report_is_a_complete_html_document(document):
    assert document.startswith("<!DOCTYPE html>")
    assert document.rstrip().endswith("</html>")


def test_the_plotly_bundle_is_embedded_exactly_once(html, document):
    """~3MB per copy. Once per chart would make the file unusable."""
    assert html(document).embedded_bundle_count() == 1


def test_the_report_opens_with_no_network_by_default(html, document):
    """The sprint requires artefacts that render on a locked-down machine.

    Asked as "which URLs does this page fetch a script from", not as "does
    the text `cdn.plot.ly` appear anywhere". Plotly's embedded bundle names
    its own CDN in a licence comment, so the substring is present in a file
    that fetches nothing -- the question has to be asked of the script tags.
    """
    doc = html(document)
    assert doc.script_srcs() == []
    doc.assert_absent("needs a network")


def test_cdn_mode_is_available_and_says_so(html, results):
    """Smaller files, but they need a network -- the reader should know."""
    doc = html(R.build_report(results, "CDN", T.metrics, inline_js=False))
    assert [src for src in doc.script_srcs() if "cdn.plot.ly" in src]
    assert doc.embedded_bundle_count() == 0
    doc.assert_contains("needs a network connection")


def test_a_chart_is_rendered_for_every_figure(document):
    """Two overview charts plus a price and volume chart per symbol."""
    assert document.count("plotly-graph-div") == 2 + 2 * 3


def test_report_names_every_symbol(html, results, document):
    html(document).assert_contains(
        *[result["summary"]["symbol"] for result in results])


def test_report_shows_quarantined_rows_and_reasons(html, document):
    html(document).assert_contains(
        "DUPLICATE_DATE", "MISSING_FIELD", "NOT_A_NUMBER")


def test_report_shows_repairs(html, document):
    html(document).assert_contains("repair_high_low", "Repaired and loaded")


def test_report_states_the_reconciliation_outcome(html, document):
    html(document).assert_contains("Reconciled")


def test_report_carries_the_educational_disclaimer(html, document):
    html(document.lower()).assert_contains("not for investment use")


def test_report_escapes_html_in_a_symbol_name(html):
    """A symbol from the wire must not be able to inject markup."""
    payload = {"data": {"symbol": "<script>x</script>", "candles": []}}
    result = T.transform(payload)
    doc = html(R.build_report([result], "RUN", T.metrics))
    doc.assert_absent("<script>x</script>")
    doc.assert_contains("&lt;script&gt;")


# ---------------------------------------------------------------------------
# The bug this test exists to prevent
# ---------------------------------------------------------------------------

def test_series_are_not_aligned_by_position():
    """Two symbols with different trading days must land on the right dates.

    An earlier renderer positioned points by list index, which drew a symbol's
    fourth point on ANOTHER symbol's fourth date -- silently claiming a price
    moved on a day it did not. Giving each trace its own real date values is
    what prevents that.
    """
    def result_for(symbol, days):
        rows = [{"symbol": symbol, "date": d, "open": 1.0, "high": 1.0,
                 "low": 1.0, "close": 100.0 + i, "adjclose": 1.0, "volume": 1,
                 "synthetic": False, "currency": "INR", "repaired": False,
                 "repairs": [], "daily_return_pct": None, "turnover": 1.0,
                 "range": 0.0, "change": 0.0}
                for i, d in enumerate(days)]
        return {"symbol": symbol, "currency": "INR", "rows": rows,
                "quarantined": [],
                "summary": T._summarise(symbol, rows, rows, [], True)}

    dense = [date(2026, 7, d) for d in (1, 2, 3, 4)]
    sparse = [date(2026, 7, 1), date(2026, 7, 4)]
    figure, _ = R.comparison_figure([result_for("DENSE.NS", dense),
                                     result_for("SPARSE.NS", sparse)])
    sparse_trace = next(t for t in figure["data"] if t["name"] == "SPARSE.NS")
    assert sparse_trace["x"] == ["2026-07-01", "2026-07-04"]


def test_write_report_creates_the_file(tmp_path, results):
    destination = tmp_path / "sub" / "report.html"
    written = R.write_report(results, "RUN", T.metrics, str(destination))
    assert destination.exists()
    assert destination.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert written == str(destination)
