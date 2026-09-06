"""Tests over the dashboard's figure builders.

Same split as `test_report.py`, for the same reason: every chart is a plain
`{"data": [...], "layout": {...}}` dict built by a pure function, so a chart
showing the wrong number fails here rather than in a browser.

The palette assertions look like style checks and are not. The ordering IS the
colour-blindness margin -- adjacent slots are the pair a reader has to tell
apart -- so an innocent-looking reshuffle can put the suite's worst pair back
below the separation floor without anything else changing.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from ETL_Analysis import charts as C
from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import transform as T


@pytest.fixture
def results():
    payloads, _ = E.extract_many(["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"])
    return T.transform_many(payloads, repair=True)


@pytest.fixture
def reliance(results):
    return next(r for r in results if r["symbol"] == "RELIANCE.NS")


@pytest.fixture
def malformed(results):
    return next(r for r in results if r["symbol"] == "TATASTEEL.BO")


def _synthetic(symbol: str, drift: float, days: int = 10) -> dict:
    """A clean, made-up series, for the cases the fixtures do not cover."""
    base = 100.0
    rows = []
    for offset in range(days):
        base *= 1 + drift
        rows.append({
            "symbol": symbol, "date": date(2026, 7, 1) + timedelta(days=offset),
            "open": base * 0.99, "high": base * 1.02, "low": base * 0.98,
            "close": round(base, 2), "adjclose": base,
            "volume": 10_000 + offset, "synthetic": False, "currency": "INR",
            "repaired": False, "repairs": [],
        })
    return {
        "symbol": symbol, "currency": "INR", "interval": "1d",
        "rows": rows, "quarantined": [],
        "summary": T.summarise_rows(symbol, rows, [], True),
    }


def _all_figures(results):
    figures = [C.comparison_figure(results)[0], C.disposition_figure(results)]
    for result in results:
        figures += [C.price_figure(result), C.price_figure(result, by_quarter=True),
                    C.volume_figure(result), C.return_histogram(result)]
    figures.append(C.reason_figure([{"reason": "MISSING_FIELD",
                                     "rows_affected": 3, "symbols": 1}]))
    figures.append(C.metric_history_figure(
        [{"run_id": "r1", "symbol": "A.NS", "value": 1.0}], "Return", "pct"))
    return [figure for figure in figures if figure is not None]


# ---------------------------------------------------------------------------
# The palette. The order is a safety property, not a preference.
# ---------------------------------------------------------------------------

def test_the_palette_order_is_the_validated_one():
    """Checked with the colour validator, not by eye. Reordering these needs
    a re-run of that check, which is why the expected list is spelled out."""
    assert C.SERIES_COLOURS == ["#0072B2", "#D55E00", "#009E73",
                                "#E69F00", "#CC79A7", "#56B4E9"]


def test_reddish_purple_is_not_next_to_bluish_green():
    """The pair that fails: separation under deuteranopia is dE 7.6, inside
    the band that needs a second non-colour encoding. Orange between them
    lifts the worst adjacent pair to 9.6."""
    pairs = list(zip(C.SERIES_COLOURS, C.SERIES_COLOURS[1:]))
    assert ("#CC79A7", "#009E73") not in pairs
    assert ("#009E73", "#CC79A7") not in pairs


def test_status_colours_are_not_series_colours():
    """A status colour must never be able to impersonate a series."""
    for status in (C.STATUS_GOOD, C.STATUS_WARNING, C.STATUS_CRITICAL):
        assert status not in C.SERIES_COLOURS


def test_colour_follows_the_entity_not_the_rank():
    """A caller passes a stable index, so filtering a series out must not
    repaint the survivors."""
    assert C.colour_for(0) == C.SERIES_COLOURS[0]
    assert C.colour_for(2) == C.SERIES_COLOURS[2]
    assert C.colour_for(len(C.SERIES_COLOURS)) == C.SERIES_COLOURS[0]


# ---------------------------------------------------------------------------
# Readability rules that apply to every figure
# ---------------------------------------------------------------------------

def test_every_axis_on_every_figure_is_titled(results):
    """The sprint's bar: a non-technical reader, unaided. An unlabelled axis
    is the usual way that fails.

    The title has to be non-EMPTY, not merely present. `axis()` takes it as a
    required argument, so passing "" satisfies the signature and still ships
    a bare axis -- which is exactly what two of these figures used to do.
    """
    for figure in _all_figures(results):
        for name in ("xaxis", "yaxis"):
            assert name in figure["layout"]
            title = figure["layout"][name].get("title", {}).get("text", "")
            assert title.strip(), (name, figure["layout"].get("title"))


def test_a_stacked_legend_reads_in_the_same_order_as_its_bars(results):
    """Plotly reverses a stacked chart's legend by default, so the key ends up
    describing the segments back to front."""
    figure = C.disposition_figure(results)
    assert figure["layout"]["legend"]["traceorder"] == "normal"


def test_no_figure_has_a_second_y_axis(results):
    """Two scales on one plot invent a correlation by choosing where to align
    them, and a reader cannot see that choice."""
    for figure in _all_figures(results):
        assert "yaxis2" not in figure["layout"]
        for trace in figure["data"]:
            assert trace.get("yaxis") in (None, "y")


def test_every_figure_is_json_serialisable(results):
    """Plotly serialises the figure to JSON in the page; a stray date or
    Decimal would blow up at render time rather than here."""
    for figure in _all_figures(results):
        json.dumps(figure)


def test_a_count_axis_never_offers_a_fraction_of_a_row(results):
    """Plotly picks ticks for continuous data, so a chart whose tallest bar
    is 1 gets ticks at 0, 0.2, 0.4 -- and a fifth of a row does not exist."""
    figures = [
        C.disposition_figure(results),
        C.reason_figure([{"reason": "MISSING_FIELD", "rows_affected": 1,
                          "symbols": 1}]),
        C.return_histogram(next(r for r in results
                                if r["symbol"] == "TATASTEEL.BO")),
    ]
    counted = [(figures[0], "xaxis"), (figures[1], "xaxis"),
               (figures[2], "yaxis")]
    for figure, name in counted:
        spec = figure["layout"][name]
        assert spec["tickformat"] == ",d"
        assert spec["dtick"] == 1


def test_a_count_axis_leaves_larger_scales_to_plotly():
    """Above ten, plotly's own steps are already whole numbers, and forcing
    dtick=1 would draw a tick per row."""
    spec = C.count_axis("Rows", 400)
    assert "dtick" not in spec
    assert spec["tickformat"] == ",d"


def test_the_reason_axis_title_is_short_enough_to_render(results):
    """A long title on a rotated axis is clipped rather than wrapped."""
    figure = C.reason_figure([{"reason": "X", "rows_affected": 1, "symbols": 1}])
    assert len(figure["layout"]["yaxis"]["title"]["text"]) <= 20


def test_gridlines_are_solid(results):
    """Dashed reads as 'threshold' or 'projection' when it is only a grid."""
    for figure in _all_figures(results):
        for name in ("xaxis", "yaxis"):
            assert "dash" not in figure["layout"][name]


# ---------------------------------------------------------------------------
# Direct labels
# ---------------------------------------------------------------------------

def test_stagger_leaves_well_separated_labels_alone():
    assert C.stagger([100.0, 50.0, 10.0], min_gap=5.0) == [100.0, 50.0, 10.0]


def test_stagger_pushes_colliding_labels_apart():
    placed = C.stagger([100.0, 99.5, 99.0], min_gap=5.0)
    assert placed[0] == 100.0
    assert placed[0] - placed[1] >= 5.0
    assert placed[1] - placed[2] >= 5.0


def test_stagger_keeps_the_original_ordering():
    """A label must not overtake the series above it while being nudged."""
    values = [10.0, 30.0, 29.0, 5.0]
    placed = C.stagger(values, min_gap=8.0)
    by_value = sorted(range(len(values)), key=lambda i: values[i])
    by_placed = sorted(range(len(placed)), key=lambda i: placed[i])
    assert by_value == by_placed


def test_stagger_of_nothing_is_nothing():
    assert C.stagger([], min_gap=1.0) == []


def test_a_few_series_are_directly_labelled(results):
    """Selective direct labels: the endpoint only, never every point."""
    figure, _ = C.comparison_figure(results)
    labels = {a["text"].strip() for a in figure["layout"]["annotations"]}
    assert labels == {"RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"}


def test_many_series_fall_back_to_the_legend_alone():
    """Six labels stacked at one x is not a label, it is a smudge."""
    many = [_synthetic(f"SYM{i}.NS", i / 500) for i in range(6)]
    figure, _ = C.comparison_figure(many)
    assert "annotations" not in figure["layout"]
    assert figure["layout"]["showlegend"] is not False


def test_a_legend_is_present_whenever_there_are_two_series(results):
    figure, _ = C.comparison_figure(results)
    assert figure["layout"]["legend"]
    assert figure["layout"]["showlegend"] is True


def test_a_lone_series_needs_no_legend_box(results):
    """The title names it; a one-entry legend is furniture."""
    figure, _ = C.comparison_figure(results[:1])
    assert figure["layout"]["showlegend"] is False


# ---------------------------------------------------------------------------
# comparison_figure
# ---------------------------------------------------------------------------

def test_every_series_is_rebased_to_100_at_its_own_first_day(results):
    figure, _ = C.comparison_figure(results)
    for trace in figure["data"]:
        assert trace["y"][0] == 100.0


def test_each_series_carries_its_own_dates(results):
    """Symbols trade on different days. A shared index would put one symbol's
    fourth point on another symbol's fourth date."""
    figure, _ = C.comparison_figure(results)
    for result in results:
        trace = next(t for t in figure["data"]
                     if t["name"] == result["summary"]["symbol"])
        assert trace["x"] == [r["date"].isoformat() for r in result["rows"]]


def test_the_comparison_x_axis_is_a_real_date_axis(results):
    """A date axis spaces a two-day gap as two days."""
    figure, _ = C.comparison_figure(results)
    assert figure["layout"]["xaxis"]["type"] == "date"


def test_the_comparison_chart_is_capped_so_it_stays_readable():
    many = [_synthetic(f"SYM{i:02d}.NS", (i - 20) / 1000) for i in range(40)]
    figure, trimmed = C.comparison_figure(many)
    assert trimmed is True
    assert len(figure["data"]) == C.MAX_COMPARISON_SERIES


def test_the_capped_chart_keeps_the_biggest_movers():
    many = [_synthetic(f"SYM{i:02d}.NS", (i - 20) / 1000) for i in range(40)]
    figure, _ = C.comparison_figure(many)
    charted = {t["name"] for t in figure["data"]}
    assert "SYM39.NS" in charted   # largest riser
    assert "SYM00.NS" in charted   # largest faller


def test_a_narrow_set_is_not_trimmed(results):
    figure, trimmed = C.comparison_figure(results)
    assert trimmed is False
    assert len(figure["data"]) == 3


def test_a_series_of_one_day_cannot_be_rebased(results):
    """One point is not a movement, so it is not charted."""
    single = dict(results[0])
    single["rows"] = results[0]["rows"][:1]
    assert C.comparison_figure([single]) == (None, False)


def test_comparison_of_nothing_is_none():
    assert C.comparison_figure([]) == (None, False)


# ---------------------------------------------------------------------------
# disposition_figure
# ---------------------------------------------------------------------------

def test_disposition_bars_stack_to_the_candles_received(results):
    """The reconciliation invariant, drawn: the bar length is what arrived."""
    figure = C.disposition_figure(results)
    assert figure["layout"]["barmode"] == "stack"
    for index, result in enumerate(results):
        total = sum(trace["x"][index] for trace in figure["data"])
        assert total == result["summary"]["candles_in"]


def test_disposition_uses_the_status_palette_not_series_colours(results):
    """These are states with a direction, not three identities."""
    colours = [t["marker"]["color"] for t in C.disposition_figure(results)["data"]]
    assert colours == [C.STATUS_GOOD, C.STATUS_WARNING, C.STATUS_CRITICAL]


def test_disposition_segments_are_separated_by_a_surface_gap(results):
    """A surface-coloured gap, not a contrasting outline around each mark."""
    for trace in C.disposition_figure(results)["data"]:
        assert trace["marker"]["line"]["color"] == C.SURFACE


def test_every_disposition_segment_carries_its_own_name(results):
    """Status never travels on colour alone."""
    names = [t["name"] for t in C.disposition_figure(results)["data"]]
    assert names == ["Loaded clean", "Loaded after repair", "Quarantined"]


def test_disposition_of_nothing_is_none():
    assert C.disposition_figure([]) is None


# ---------------------------------------------------------------------------
# price_figure
# ---------------------------------------------------------------------------

def test_repaired_points_are_drawn_as_open_diamonds(malformed):
    """A reader must see which points were corrected rather than observed --
    and the SHAPE carries it, so it survives a greyscale print."""
    markers = C.price_figure(malformed)["data"][0]["marker"]["symbol"]
    assert markers.count("diamond-open") == 3


def test_clean_symbols_have_no_marked_points(reliance):
    markers = C.price_figure(reliance)["data"][0]["marker"]["symbol"]
    assert set(markers) == {"circle"}


def test_a_repaired_symbol_says_so_on_the_chart(malformed):
    note = C.price_figure(malformed)["layout"]["annotations"][0]["text"]
    assert "repaired by the transform, not observed" in note


def test_a_clean_symbol_gets_no_repair_note(reliance):
    assert "annotations" not in C.price_figure(reliance)["layout"]


def test_a_single_series_needs_no_legend(reliance):
    """The section heading above the chart already names it."""
    assert C.price_figure(reliance)["layout"]["showlegend"] is False


def test_quarter_mode_charts_only_the_quarters_present(reliance):
    """The fixtures are all July 2026, so there is one quarter and one trace.
    Empty buckets would put three unreachable entries in the legend."""
    figure = C.price_figure(reliance, by_quarter=True)
    assert [trace["name"] for trace in figure["data"]] == ["Q3"]
    assert figure["layout"]["showlegend"] is True


def test_quarter_mode_puts_july_in_q3(reliance):
    figure = C.price_figure(reliance, by_quarter=True)
    assert len(figure["data"][0]["x"]) == len(reliance["rows"])


# ---------------------------------------------------------------------------
# Quarters. The bug this pins is silent: it draws a line nobody can see is
# wrong.
# ---------------------------------------------------------------------------

def test_the_same_quarter_in_two_years_is_two_buckets():
    """Keying on the quarter alone would draw September 2025 and September
    2026 as one line called Q3, joining two points a year apart and inventing
    the move between them. The store spans exactly that."""
    rows = [{"date": date(2025, 9, 15)}, {"date": date(2026, 9, 15)}]
    assert [label for label, _ in C.split_by_quarter(rows)] == [
        "2025 Q3", "2026 Q3"]


def test_quarters_come_back_in_chronological_order():
    rows = [{"date": date(2026, 3, 2)}, {"date": date(2025, 9, 15)},
            {"date": date(2025, 12, 1)}]
    assert [label for label, _ in C.split_by_quarter(rows)] == [
        "2025 Q3", "2025 Q4", "2026 Q1"]


def test_a_single_year_of_data_does_not_print_the_year():
    """"2026 Q1" is noise when every row is from 2026."""
    rows = [{"date": date(2026, 2, 1)}, {"date": date(2026, 5, 1)}]
    assert [label for label, _ in C.split_by_quarter(rows)] == ["Q1", "Q2"]


def test_no_row_is_lost_or_duplicated_by_the_split():
    rows = [{"date": date(2025, 9, d)} for d in range(1, 20)]
    rows += [{"date": date(2026, 1, d)} for d in range(1, 15)]
    buckets = C.split_by_quarter(rows)
    assert sum(len(bucket) for _, bucket in buckets) == len(rows)


def test_rows_inside_a_quarter_keep_their_date_order():
    rows = [{"date": date(2026, 3, 9)}, {"date": date(2026, 1, 4)},
            {"date": date(2026, 2, 7)}]
    rows.sort(key=lambda r: r["date"])
    (_, bucket), = C.split_by_quarter(rows)
    assert [r["date"].day for r in bucket] == [4, 7, 9]


def test_splitting_nothing_gives_nothing():
    assert C.split_by_quarter([]) == []


def test_quarter_mode_loses_no_rows(malformed):
    figure = C.price_figure(malformed, by_quarter=True)
    charted = sum(len(trace["x"]) for trace in figure["data"])
    assert charted == len(malformed["rows"])


def test_price_figure_of_no_rows_is_none():
    assert C.price_figure({"symbol": "X.NS", "rows": [], "quarantined": [],
                           "summary": {"symbol": "X.NS"}}) is None


# ---------------------------------------------------------------------------
# volume_figure
# ---------------------------------------------------------------------------

def test_a_missing_volume_stays_null_rather_than_becoming_zero(results):
    """A zero bar would claim a day with no trading. Null leaves a gap."""
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    volumes = C.volume_figure(infy)["data"][0]["y"]
    assert None in volumes
    assert 0 not in volumes


def test_a_missing_volume_is_explained_on_the_chart(results):
    infy = next(r for r in results if r["symbol"] == "INFY.NS")
    note = C.volume_figure(infy)["layout"]["annotations"][0]["text"]
    assert "not drawn as zero" in note


def test_a_symbol_with_no_missing_volume_gets_no_annotation(reliance):
    assert "annotations" not in C.volume_figure(reliance)["layout"]


def test_volume_starts_at_zero(reliance):
    """A truncated volume axis exaggerates a difference in traded shares."""
    assert C.volume_figure(reliance)["layout"]["yaxis"]["rangemode"] == "tozero"


def test_volume_figure_of_no_rows_is_none():
    assert C.volume_figure({"symbol": "X.NS", "rows": [], "quarantined": [],
                            "summary": {"symbol": "X.NS"}}) is None


# ---------------------------------------------------------------------------
# return_histogram
# ---------------------------------------------------------------------------

def test_the_histogram_covers_every_return_the_measures_used(reliance):
    returns = [r["daily_return_pct"] for r in reliance["rows"]
               if r["daily_return_pct"] is not None]
    assert C.return_histogram(reliance)["data"][0]["x"] == returns


def test_the_histogram_marks_zero(reliance):
    """Up days and down days are only separable if zero is drawn."""
    assert C.return_histogram(reliance)["layout"]["shapes"][0]["x0"] == 0


def test_a_series_too_short_to_have_a_distribution_is_none(reliance):
    single = dict(reliance)
    single["rows"] = reliance["rows"][:1]
    assert C.return_histogram(single) is None


# ---------------------------------------------------------------------------
# reason_figure and metric_history_figure
# ---------------------------------------------------------------------------

def test_reason_bars_are_one_colour_because_reasons_are_nominal():
    """Shading each bar by its own length would spend the colour channel
    restating the bar length."""
    figure = C.reason_figure([
        {"reason": "MISSING_FIELD", "rows_affected": 3, "symbols": 1},
        {"reason": "NOT_A_NUMBER", "rows_affected": 1, "symbols": 1},
    ])
    assert len(figure["data"]) == 1
    assert isinstance(figure["data"][0]["marker"]["color"], str)


def test_reason_bars_are_ordered_worst_last_so_the_chart_reads_downward():
    figure = C.reason_figure([
        {"reason": "SMALL", "rows_affected": 1, "symbols": 1},
        {"reason": "BIG", "rows_affected": 9, "symbols": 1},
    ])
    assert figure["data"][0]["y"] == ["SMALL", "BIG"]


def test_reason_figure_of_nothing_is_none():
    assert C.reason_figure([]) is None
    assert C.reason_figure([{"reason": "X", "rows_affected": 0}]) is None


def test_metric_history_keeps_the_runs_in_the_order_they_happened():
    rows = [
        {"run_id": "r1", "symbol": "A.NS", "value": 1.0},
        {"run_id": "r2", "symbol": "A.NS", "value": 2.0},
        {"run_id": "r3", "symbol": "A.NS", "value": 3.0},
    ]
    figure = C.metric_history_figure(rows, "Return", "pct")
    assert figure["data"][0]["x"] == ["r1", "r2", "r3"]
    assert figure["data"][0]["y"] == [1.0, 2.0, 3.0]


def test_a_run_that_did_not_compute_a_measure_leaves_a_gap():
    """A missing measure is not a value of zero, and connecting across it
    would draw a movement that never happened."""
    rows = [
        {"run_id": "r1", "symbol": "A.NS", "value": 1.0},
        {"run_id": "r2", "symbol": "B.NS", "value": 5.0},
        {"run_id": "r3", "symbol": "A.NS", "value": 3.0},
    ]
    figure = C.metric_history_figure(rows, "Return", "pct")
    trace = next(t for t in figure["data"] if t["name"] == "A.NS")
    assert trace["y"] == [1.0, None, 3.0]
    assert trace["connectgaps"] is False


def test_metric_history_of_nothing_is_none():
    assert C.metric_history_figure([], "Return") is None
