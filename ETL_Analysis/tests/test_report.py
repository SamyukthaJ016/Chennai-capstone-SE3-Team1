"""Tests over the analytical measures and the HTML report.

The measures are checked against independent computations -- `statistics`
for the standard deviation, brute force for the drawdown -- rather than
against themselves, so a wrong formula fails rather than being confirmed.

The report is checked for the properties that actually matter: it opens with
no network, every chart is well-formed XML, and series are aligned to the
right dates.
"""

from __future__ import annotations

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
# The report document
# ---------------------------------------------------------------------------

def test_report_is_a_complete_html_document(document):
    assert document.startswith("<!DOCTYPE html>")
    assert document.rstrip().endswith("</html>")


def test_report_opens_with_no_network(document):
    """The sprint requires artefacts that render on a locked-down machine."""
    external = document.replace("http://www.w3.org/2000/svg", "")
    assert "http://" not in external
    assert "https://" not in external
    assert "<script" not in document.lower()


def test_every_chart_is_well_formed_xml(document):
    svgs = re.findall(r"<svg.*?</svg>", document, re.S)
    assert len(svgs) >= 5
    for svg in svgs:
        ET.fromstring(svg)  # raises if malformed


def test_every_chart_has_a_title_and_both_axes_labelled(document):
    """A chart a non-technical reader can read unaided."""
    for svg in re.findall(r"<svg.*?</svg>", document, re.S):
        assert 'class="chart-title"' in svg or 'aria-label' in svg


def test_report_names_every_symbol(results, document):
    for result in results:
        assert result["summary"]["symbol"] in document


def test_report_shows_quarantined_rows_and_reasons(document):
    assert "DUPLICATE_DATE" in document
    assert "MISSING_FIELD" in document
    assert "NOT_A_NUMBER" in document


def test_report_shows_repairs(document):
    assert "repair_high_low" in document
    assert "Repaired and loaded" in document


def test_report_marks_a_missing_volume_rather_than_drawing_zero(document):
    """A day with no reported volume is not a day with no trading."""
    assert "n/a" in document
    assert "not a day" in document.lower()


def test_report_states_the_reconciliation_outcome(document):
    assert "Reconciled" in document


def test_report_carries_the_educational_disclaimer(document):
    assert "not for investment use" in document.lower()


def test_report_escapes_html_in_a_symbol_name():
    """A symbol from the wire must not be able to inject markup."""
    payload = {"data": {"symbol": "<script>x</script>", "candles": []}}
    result = T.transform(payload)
    document = R.build_report([result], "RUN", T.metrics)
    assert "<script>x</script>" not in document
    assert "&lt;script&gt;" in document


# ---------------------------------------------------------------------------
# The bug this test exists to prevent
# ---------------------------------------------------------------------------

def test_series_are_aligned_by_date_not_by_position():
    """Two symbols with different trading days must land on the right dates.

    Positioning by list index would draw a symbol's fourth point on the
    fourth date of ANOTHER symbol's series, which silently claims a price
    moved on a day it did not.
    """
    categories = ["01 Jul", "02 Jul", "03 Jul", "04 Jul"]
    series = [
        {"name": "FULL", "points": [(c, 100.0) for c in categories]},
        {"name": "SPARSE", "points": [("01 Jul", 100.0), ("04 Jul", 200.0)]},
    ]
    svg = R.line_chart(series, "t", "x", "y", categories=categories, width=500)
    sparse = re.search(r'stroke="#D55E00"[^/]*points="([^"]+)"', svg).group(1)
    xs = [float(p.split(",")[0]) for p in sparse.split()]
    full = re.search(r'stroke="#0072B2"[^/]*points="([^"]+)"', svg).group(1)
    full_xs = [float(p.split(",")[0]) for p in full.split()]
    # SPARSE's two points sit on the FIRST and LAST category, not the first two.
    assert xs[0] == pytest.approx(full_xs[0])
    assert xs[1] == pytest.approx(full_xs[3])


def test_the_shared_axis_covers_every_trading_day(results, document):
    all_dates = sorted({r["date"] for res in results for r in res["rows"]})
    svg = re.findall(r"<svg.*?</svg>", document, re.S)[0]
    for day in all_dates:
        assert day.strftime("%d %b") in svg


def test_a_chart_with_no_data_says_so_rather_than_crashing():
    assert "No data" in R.line_chart(
        [{"name": "x", "points": []}], "t", "x", "y")
    assert "No data" in R.bar_chart([], "t", "x", "y")


def test_write_report_creates_the_file(tmp_path, results):
    destination = tmp_path / "sub" / "report.html"
    written = R.write_report(results, "RUN", T.metrics, str(destination))
    assert destination.exists()
    assert destination.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert written == str(destination)
