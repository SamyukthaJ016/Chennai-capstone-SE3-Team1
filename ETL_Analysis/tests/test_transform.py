"""Tests over the transform.

The suite never touches the network: every payload is read from `fixtures/` or
built inline. The malformed-input tests are named for what they assert, so
`test_rejects_a_high_below_a_low` can be run and read on its own.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ETL_Analysis import transform as T

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def reliance() -> dict:
    return _load("candles-reliance-ns-2026-07.json")


@pytest.fixture
def infy() -> dict:
    return _load("candles-infy-ns-2026-07.json")


@pytest.fixture
def malformed() -> dict:
    return _load("candles-malformed.json")


@pytest.fixture
def malformed_result(malformed) -> dict:
    """Default mode: defects 4, 5 and 6 repaired and flagged."""
    return T.transform(malformed)


@pytest.fixture
def malformed_strict(malformed) -> dict:
    """Strict mode: every defect quarantined, nothing repaired."""
    return T.transform(malformed, repair=False)


def _reasons(result: dict) -> list[str]:
    return [bad["reason"] for bad in result["quarantined"]]


def _quarantined_for(result: dict, raw_date: str) -> dict:
    for bad in result["quarantined"]:
        if bad["candle"].get("date") == raw_date:
            return bad
    raise AssertionError(f"no quarantined row for {raw_date!r}")


# --------------------------------------------------------------------------
# Clean payloads
# --------------------------------------------------------------------------

def test_clean_payload_keeps_every_candle(reliance):
    result = T.transform(reliance)
    assert result["summary"]["rows_kept"] == 9
    assert result["quarantined"] == []


def test_rows_are_sorted_by_date(reliance):
    rows = T.transform(reliance)["rows"]
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)


def test_dates_are_parsed_to_date_objects(reliance):
    rows = T.transform(reliance)["rows"]
    assert rows[0]["date"] == date(2026, 7, 1)
    assert all(isinstance(r["date"], date) for r in rows)


def test_calendar_gap_is_preserved_not_filled(reliance):
    """The exchange was shut on 2026-07-08; the transform must not invent it."""
    dates = {r["date"] for r in T.transform(reliance)["rows"]}
    assert date(2026, 7, 8) not in dates


def test_first_row_has_no_daily_return(reliance):
    """Nothing precedes it in the payload, so a return cannot be computed."""
    assert T.transform(reliance)["rows"][0]["daily_return_pct"] is None


def test_daily_return_is_computed_from_previous_close(reliance):
    rows = T.transform(reliance)["rows"]
    expected = (rows[1]["close"] - rows[0]["close"]) / rows[0]["close"] * 100
    assert rows[1]["daily_return_pct"] == pytest.approx(expected, abs=1e-4)


# --------------------------------------------------------------------------
# Things that look like defects but are not
# --------------------------------------------------------------------------

def test_keeps_a_candle_with_null_volume(infy):
    """The live API emits null volume; it does not make the prices wrong."""
    result = T.transform(infy)
    assert result["summary"]["rows_kept"] == 8
    assert result["quarantined"] == []
    null_volume = [r for r in result["rows"] if r["volume"] is None]
    assert len(null_volume) == 1
    assert null_volume[0]["date"] == date(2026, 7, 6)


def test_null_volume_row_has_no_turnover(infy):
    row = next(r for r in T.transform(infy)["rows"] if r["volume"] is None)
    assert row["turnover"] is None


def test_synthetic_flag_is_carried_through_not_dropped(infy):
    """A vendor-interpolated candle is kept, but a chart must be able to see it."""
    rows = T.transform(infy)["rows"]
    synthetic = [r for r in rows if r["synthetic"]]
    assert len(synthetic) == 1
    assert synthetic[0]["date"] == date(2026, 7, 8)
    assert T.transform(infy)["summary"]["synthetic_rows"] == 1


# --------------------------------------------------------------------------
# The six defects in the malformed fixture, one test each
# --------------------------------------------------------------------------

def test_rejects_a_duplicated_date_keeping_the_first(malformed_result):
    bad = [b for b in malformed_result["quarantined"] if b["reason"] == T.DUPLICATE_DATE]
    assert len(bad) == 1
    # The first 2026-07-01 (close 169.5) survives; the second (168.95) does not.
    kept = [r for r in malformed_result["rows"] if r["date"] == date(2026, 7, 1)]
    assert len(kept) == 1
    assert kept[0]["close"] == 169.5
    assert bad[0]["candle"]["close"] == 168.95


def test_rejects_a_candle_with_no_close_field(malformed_result):
    bad = _quarantined_for(malformed_result, "2026-07-02")
    assert bad["reason"] == T.MISSING_FIELD
    assert "close" in bad["detail"]


def test_rejects_a_string_where_a_number_belongs(malformed_result):
    bad = _quarantined_for(malformed_result, "2026-07-06")
    assert bad["reason"] == T.NOT_A_NUMBER
    assert "n/a" in bad["detail"]


def test_repairs_a_high_below_a_low_by_swapping_and_flags_it(malformed_result):
    """The two values are transposed: swapping puts open and close inside the
    range. Repaired rather than quarantined, but flagged so a chart can drop it."""
    row = next(r for r in malformed_result["rows"] if r["date"] == date(2026, 7, 7))
    assert row["high"] == 175.85
    assert row["low"] == 168.1
    assert row["repaired"] is True
    assert row["repairs"][0]["code"] == T.REPAIR_HIGH_LOW
    # Whatever else happens, no loaded row may have a high below its low.
    assert not any(r["high"] < r["low"] for r in malformed_result["rows"])


def test_repaired_high_low_keeps_open_and_close_inside_the_range(malformed_result):
    row = next(r for r in malformed_result["rows"] if r["date"] == date(2026, 7, 7))
    assert row["low"] <= row["open"] <= row["high"]
    assert row["low"] <= row["close"] <= row["high"]


def test_high_below_low_is_quarantined_in_strict_mode(malformed_strict):
    bad = _quarantined_for(malformed_strict, "2026-07-07")
    assert bad["reason"] == T.HIGH_BELOW_LOW


def test_high_below_low_is_not_repaired_when_swap_does_not_resolve_it():
    """The swap is applied only when it fully resolves the candle. If close
    still falls outside the swapped range, the transposition story does not
    hold and swapping would invent a number."""
    payload = {"data": {"symbol": "BAD.NS", "candles": [
        {"date": "2026-07-01", "open": 100.0, "high": 90.0,
         "low": 110.0, "close": 500.0, "volume": 10},
    ]}}
    result = T.transform(payload, repair=True)
    assert result["rows"] == []
    assert result["quarantined"][0]["reason"] == T.HIGH_BELOW_LOW


def test_repairs_a_negative_volume_to_null_and_flags_it(malformed_result):
    """-1 is a sentinel for unknown, not a count: the same feed uses null
    elsewhere (see the INFY fixture). Prices on the row are valid."""
    row = next(r for r in malformed_result["rows"] if r["date"] == date(2026, 7, 8))
    assert row["volume"] is None
    assert row["repaired"] is True
    assert row["repairs"][0]["code"] == T.REPAIR_VOLUME
    assert all(r["volume"] is None or r["volume"] >= 0 for r in malformed_result["rows"])


def test_repaired_volume_row_keeps_its_prices(malformed_result):
    row = next(r for r in malformed_result["rows"] if r["date"] == date(2026, 7, 8))
    assert (row["open"], row["high"], row["low"], row["close"]) == (
        173.7, 176.25, 172.9, 175.8)


def test_negative_volume_is_quarantined_in_strict_mode(malformed_strict):
    bad = _quarantined_for(malformed_strict, "2026-07-08")
    assert bad["reason"] == T.NEGATIVE_VOLUME


def test_a_genuinely_negative_volume_is_still_quarantined():
    """-1 is a known sentinel. -5000 is not, and must not be normalised away."""
    payload = {"data": {"symbol": "NEG.NS", "candles": [
        {"date": "2026-07-01", "open": 100.0, "high": 105.0,
         "low": 99.0, "close": 103.0, "volume": -5000},
    ]}}
    result = T.transform(payload, repair=True)
    assert result["rows"] == []
    assert result["quarantined"][0]["reason"] == T.NEGATIVE_VOLUME


def test_repairs_a_non_iso_date_as_day_first_and_flags_it(malformed_result):
    """09/07/2026 is ambiguous in isolation. Resolved by context: it follows
    2026-07-08, so 9 July continues the sequence and 7 September would leave a
    two-month hole."""
    row = next(r for r in malformed_result["rows"] if r["repairs"]
               and r["repairs"][0]["code"] == T.REPAIR_DATE)
    assert row["date"] == date(2026, 7, 9)
    assert row["repaired"] is True


def test_the_day_first_assumption_is_explicit(malformed_result):
    """Pin the convention so it cannot drift silently to MM/DD."""
    assert T.DAYFIRST is True
    assert T.NON_ISO_DATE_FORMAT == "%d/%m/%Y"


def test_repaired_date_keeps_the_series_in_order(malformed_result):
    dates = [r["date"] for r in malformed_result["rows"]]
    assert dates == sorted(dates)
    assert date(2026, 7, 9) in dates


def test_non_iso_date_is_quarantined_in_strict_mode(malformed_strict):
    bad = _quarantined_for(malformed_strict, "09/07/2026")
    assert bad["reason"] == T.BAD_DATE_FORMAT


def test_an_unparseable_date_is_quarantined_even_with_repair_on():
    payload = {"data": {"symbol": "BADDATE.NS", "candles": [
        {"date": "not-a-date", "open": 100.0, "high": 105.0,
         "low": 99.0, "close": 103.0, "volume": 10},
    ]}}
    result = T.transform(payload, repair=True)
    assert result["quarantined"][0]["reason"] == T.BAD_DATE_FORMAT


def test_three_defects_repaired_and_three_quarantined(malformed_result):
    s = malformed_result["summary"]
    assert s["rows_kept"] == 4
    assert s["rows_repaired"] == 3
    assert s["rows_quarantined"] == 3
    assert set(_reasons(malformed_result)) == {
        T.DUPLICATE_DATE, T.MISSING_FIELD, T.NOT_A_NUMBER,
    }


def test_all_six_defects_are_quarantined_in_strict_mode(malformed_strict):
    assert malformed_strict["summary"]["rows_quarantined"] == 6
    assert malformed_strict["summary"]["rows_repaired"] == 0
    assert set(_reasons(malformed_strict)) == {
        T.DUPLICATE_DATE,
        T.MISSING_FIELD,
        T.NOT_A_NUMBER,
        T.HIGH_BELOW_LOW,
        T.NEGATIVE_VOLUME,
        T.BAD_DATE_FORMAT,
    }


def test_one_good_row_survives_the_malformed_payload(malformed_strict):
    """A corrupt payload must not cost the rows that are fine."""
    assert malformed_strict["summary"]["rows_kept"] == 1
    assert malformed_strict["rows"][0]["date"] == date(2026, 7, 1)


def test_clean_rows_are_not_marked_repaired(reliance):
    assert all(r["repaired"] is False for r in T.transform(reliance)["rows"])
    assert T.transform(reliance)["summary"]["rows_repaired"] == 0


def test_every_repair_records_a_reason(malformed_result):
    """A silent fix is the thing this design exists to prevent."""
    for row in malformed_result["rows"]:
        if row["repaired"]:
            assert row["repairs"]
            for entry in row["repairs"]:
                assert entry["code"] and entry["detail"]


@pytest.mark.parametrize("repair", [True, False])
def test_nothing_is_dropped_silently(malformed, repair):
    """kept + quarantined always reconciles to what arrived, in both modes."""
    s = T.transform(malformed, repair=repair)["summary"]
    assert s["rows_kept"] + s["rows_quarantined"] == s["candles_in"]


def test_a_bad_row_does_not_raise(malformed):
    """Raising would abandon the good rows in the same payload."""
    T.transform(malformed)  # must not raise


def test_quarantined_row_keeps_the_original_candle(malformed_strict):
    """Quarantine means recoverable: the original payload is attached
    untouched, so a teammate can see exactly what arrived."""
    bad = _quarantined_for(malformed_strict, "2026-07-07")
    assert bad["candle"]["high"] == 168.1
    assert bad["candle"]["low"] == 175.85


# --------------------------------------------------------------------------
# Purity: transform takes data and returns data
# --------------------------------------------------------------------------

def test_transform_does_not_mutate_its_input(malformed):
    """Even a repair must not write back to the caller's payload."""
    before = json.dumps(malformed, sort_keys=True)
    T.transform(malformed, repair=True)
    assert json.dumps(malformed, sort_keys=True) == before


def test_transform_of_an_empty_payload_is_empty_not_an_error():
    result = T.transform({"data": {"symbol": "EMPTY.NS", "candles": []}})
    assert result["rows"] == []
    assert result["quarantined"] == []
    assert result["summary"]["rows_kept"] == 0


def test_rejects_a_non_positive_price():
    payload = {
        "data": {
            "symbol": "ZERO.NS",
            "candles": [
                {"date": "2026-07-01", "open": 0.0, "high": 1.0,
                 "low": 0.0, "close": 0.5, "volume": 10},
            ],
        }
    }
    result = T.transform(payload)
    assert result["quarantined"][0]["reason"] == T.NON_POSITIVE_PRICE


def test_rejects_a_close_outside_the_days_range():
    payload = {
        "data": {
            "symbol": "OUT.NS",
            "candles": [
                {"date": "2026-07-01", "open": 100.0, "high": 105.0,
                 "low": 99.0, "close": 120.0, "volume": 10},
            ],
        }
    }
    result = T.transform(payload)
    assert result["quarantined"][0]["reason"] == T.HIGH_BELOW_LOW
