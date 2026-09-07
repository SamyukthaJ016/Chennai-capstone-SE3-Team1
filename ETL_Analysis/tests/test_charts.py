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


def test_the_palette_order_is_the_validated_one():
    assert C.SERIES_COLOURS == ["#0072B2", "#D55E00", "#009E73",
                                "#E69F00", "#CC79A7", "#56B4E9"]


def test_reddish_purple_is_not_next_to_bluish_green():
    pairs = list(zip(C.SERIES_COLOURS, C.SERIES_COLOURS[1:]))
    assert ("#CC79A7", "#009E73") not in pairs
    assert ("#009E73", "#CC79A7") not in pairs


def test_status_colours_are_not_series_colours():
    for status in (C.STATUS_GOOD, C.STATUS_WARNING, C.STATUS_CRITICAL):
        assert status not in C.SERIES_COLOURS


def test_colour_follows_the_entity_not_the_rank():
    assert C.colour_for(0) == C.SERIES_COLOURS[0]
    assert C.colour_for(2) == C.SERIES_COLOURS[2]
    assert C.colour_for(len(C.SERIES_COLOURS)) == C.SERIES_COLOURS[0]


def test_every_axis_on_every_figure_is_titled(results):
    for figure in _all_figures(results):
        for name in ("xaxis", "yaxis"):
            assert name in figure["layout"]
            title = figure["layout"][name].get("title", {}).get("text", "")
            assert title.strip(), (name, figure["layout"].get("title"))


def test_a_stacked_legend_reads_in_the_same_order_as_its_bars(results):
    figure = C.disposition_figure(results)
    assert figure["layout"]["legend"]["traceorder"] == "normal"


def test_no_figure_has_a_second_y_axis(results):
    for figure in _all_figures(results):
        assert "yaxis2" not in figure["layout"]
        for trace in figure["data"]:
            assert trace.get("yaxis") in (None, "y")


def test_every_figure_is_json_serialisable(results):
    for figure in _all_figures(results):
        json.dumps(figure)


def test_a_count_axis_never_offers_a_fraction_of_a_row(results):
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
    spec = C.count_axis("Rows", 400)
    assert "dtick" not in spec
    assert spec["tickformat"] == ",d"


def test_the_reason_axis_title_is_short_enough_to_render(results):
    figure = C.reason_figure([{"reason": "X", "rows_affected": 1, "symbols": 1}])
    assert len(figure["layout"]["yaxis"]["title"]["text"]) <= 20


def test_gridlines_are_solid(results):
    for figure in _all_figures(results):
        for name in ("xaxis", "yaxis"):
            assert "dash" not in figure["layout"][name]


def test_stagger_leaves_well_separated_labels_alone():
    assert C.stagger([100.0, 50.0, 10.0], min_gap=5.0) == [100.0, 50.0, 10.0]


def test_stagger_pushes_colliding_labels_apart():
    placed = C.stagger([100.0, 99.5, 99.0], min_gap=5.0)
    assert placed[0] == 100.0
    assert placed[0] - placed[1] >= 5.0
    assert placed[1] - placed[2] >= 5.0


def test_stagger_keeps_the_original_ordering():
    values = [10.0, 30.0, 29.0, 5.0]
    placed = C.stagger(values, min_gap=8.0)
    by_value = sorted(range(len(values)), key=lambda i: values[i])
    by_placed = sorted(range(len(placed)), key=lambda i: placed[i])
    assert by_value == by_placed


def test_stagger_of_nothing_is_nothing():
    assert C.stagger([], min_gap=1.0) == []


def test_a_few_series_are_directly_labelled(results):
    figure, _ = C.comparison_figure(results)
    labels = {a["text"].strip() for a in figure["layout"]["annotations"]}
    assert labels == {"RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"}


def test_many_series_fall_back_to_the_legend_alone():
    many = [_synthetic(f"SYM{i}.NS", i / 500) for i in range(6)]
    figure, _ = C.comparison_figure(many)
    assert "annotations" not in figure["layout"]
    assert figure["layout"]["showlegend"] is not False


def test_a_legend_is_present_whenever_there_are_two_series(results):
    figure, _ = C.comparison_figure(results)
    assert figure["layout"]["legend"]
    assert figure["layout"]["showlegend"] is True


def test_a_lone_series_needs_no_legend_box(results):
    figure, _ = C.comparison_figure(results[:1])
    assert figure["layout"]["showlegend"] is False


def test_every_series_is_rebased_to_100_at_its_own_first_day(results):
    figure, _ = C.comparison_figure(results)
    for trace in figure["data"]:
        assert trace["y"][0] == 100.0


def test_each_series_carries_its_own_dates(results):
    figure, _ = C.comparison_figure(results)
    for result in results:
        trace = next(t for t in figure["data"]
                     if t["name"] == result["summary"]["symbol"])
        assert trace["x"] == [r["date"].isoformat() for r in result["rows"]]


def test_the_comparison_x_axis_is_a_real_date_axis(results):
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
    assert "SYM39.NS" in charted
    assert "SYM00.NS" in charted


def test_a_narrow_set_is_not_trimmed(results):
    figure, trimmed = C.comparison_figure(results)
    assert trimmed is False
    assert len(figure["data"]) == 3


def test_a_series_of_one_day_cannot_be_rebased(results):
    single = dict(results[0])
    single["rows"] = results[0]["rows"][:1]
    assert C.comparison_figure([single]) == (None, False)


def test_comparison_of_nothing_is_none():
    assert C.comparison_figure([]) == (None, False)


def test_disposition_bars_stack_to_the_candles_received(results):
    figure = C.disposition_figure(results)
    assert figure["layout"]["barmode"] == "stack"
    for index, result in enumerate(results):
        total = sum(trace["x"][index] for trace in figure["data"])
        assert total == result["summary"]["candles_in"]


def test_disposition_uses_the_status_palette_not_series_colours(results):
    colours = [t["marker"]["color"] for t in C.disposition_figure(results)["data"]]
    assert colours == [C.STATUS_GOOD, C.STATUS_WARNING, C.STATUS_CRITICAL]


def test_disposition_segments_are_separated_by_a_surface_gap(results):
    for trace in C.disposition_figure(results)["data"]:
        assert trace["marker"]["line"]["color"] == C.SURFACE


def test_every_disposition_segment_carries_its_own_name(results):
    names = [t["name"] for t in C.disposition_figure(results)["data"]]
    assert names == ["Loaded clean", "Loaded after repair", "Quarantined"]


def test_disposition_of_nothing_is_none():
    assert C.disposition_figure([]) is None


def test_repaired_points_are_drawn_as_open_diamonds(malformed):
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
    assert C.price_figure(reliance)["layout"]["showlegend"] is False


def test_quarter_mode_charts_only_the_quarters_present(reliance):
    figure = C.price_figure(reliance, by_quarter=True)
    assert [trace["name"] for trace in figure["data"]] == ["Q3"]
    assert figure["layout"]["showlegend"] is True


def test_quarter_mode_puts_july_in_q3(reliance):
    figure = C.price_figure(reliance, by_quarter=True)
    assert len(figure["data"][0]["x"]) == len(reliance["rows"])


def test_the_same_quarter_in_two_years_is_two_buckets():
    rows = [{"date": date(2025, 9, 15)}, {"date": date(2026, 9, 15)}]
    assert [label for label, _ in C.split_by_quarter(rows)] == [
        "2025 Q3", "2026 Q3"]


def test_quarters_come_back_in_chronological_order():
    rows = [{"date": date(2026, 3, 2)}, {"date": date(2025, 9, 15)},
            {"date": date(2025, 12, 1)}]
    assert [label for label, _ in C.split_by_quarter(rows)] == [
        "2025 Q3", "2025 Q4", "2026 Q1"]


def test_a_single_year_of_data_does_not_print_the_year():
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


def test_a_missing_volume_stays_null_rather_than_becoming_zero(results):
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
    assert C.volume_figure(reliance)["layout"]["yaxis"]["rangemode"] == "tozero"


def test_volume_figure_of_no_rows_is_none():
    assert C.volume_figure({"symbol": "X.NS", "rows": [], "quarantined": [],
                            "summary": {"symbol": "X.NS"}}) is None


def test_the_histogram_covers_every_return_the_measures_used(reliance):
    returns = [r["daily_return_pct"] for r in reliance["rows"]
               if r["daily_return_pct"] is not None]
    assert C.return_histogram(reliance)["data"][0]["x"] == returns


def test_the_histogram_marks_zero(reliance):
    assert C.return_histogram(reliance)["layout"]["shapes"][0]["x0"] == 0


def test_a_series_too_short_to_have_a_distribution_is_none(reliance):
    single = dict(reliance)
    single["rows"] = reliance["rows"][:1]
    assert C.return_histogram(single) is None


def test_reason_bars_are_one_colour_because_reasons_are_nominal():
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
