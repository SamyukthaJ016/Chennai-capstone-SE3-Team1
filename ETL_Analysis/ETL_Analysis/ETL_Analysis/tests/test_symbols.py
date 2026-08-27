"""Tests over the symbol universe and the report's behaviour on a wide pull.

Nothing here touches the network, and nothing needs to: the universe is a
file, so it is read and checked directly. The rest covers the quota
arithmetic and what the report does when a pull returns far more symbols than
a chart can usefully show.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from ETL_Analysis import report as R
from ETL_Analysis import symbols as S
from ETL_Analysis import transform as T


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

UNIVERSE = ["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO", "AAPL", "MSFT",
            "FX:EUR/USD", "X:BTCUSD"]


def test_filtering_by_venue_uses_the_contract_symbol_scheme():
    assert S.filter_symbols(UNIVERSE, exchanges=["NSE", "BSE"]) == [
        "RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"]


def test_filtering_is_case_insensitive_on_the_venue():
    assert S.filter_symbols(UNIVERSE, exchanges=["nse"]) == [
        "RELIANCE.NS", "INFY.NS"]


def test_a_limit_caps_the_pull():
    assert len(S.filter_symbols(UNIVERSE, limit=3)) == 3


def test_no_filter_returns_everything():
    assert S.filter_symbols(UNIVERSE) == UNIVERSE


def test_symbols_are_grouped_by_venue():
    assert S.group_by_exchange(UNIVERSE) == {
        "NSE": 2, "US": 2, "BSE": 1, "FX": 1, "CRYPTO": 1}


# ---------------------------------------------------------------------------
# Quota arithmetic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ({"remaining": 1900}, 1900),
    ({"requestsRemaining": 1850}, 1850),
    ({"requests_remaining": 10}, 10),
    ({"limit": 2000, "used": 150}, 1850),
    ({"data": {"limit": 2000, "requestsToday": 300}}, 1700),
    ({"blah": 1}, None),
    (None, None),
])
def test_remaining_quota_is_read_from_any_reasonable_usage_shape(payload, expected):
    assert S._remaining_from_usage(payload) == expected


def test_a_pull_that_fits_the_quota_is_allowed():
    plan = S.plan_pull(["A", "B"], check_quota=False)
    assert plan["needed"] == 2
    assert plan["ok"]


def test_cached_symbols_do_not_count_against_the_quota():
    assert S.plan_pull(["A", "B", "C"], cached=2,
                       check_quota=False)["needed"] == 1


def test_a_pull_larger_than_the_quota_is_refused(monkeypatch):
    """Refusing before the pull beats a half-finished dataset that looks whole."""
    monkeypatch.setattr(S, "remaining_quota", lambda: 5)
    with pytest.raises(S.QuotaTooLow) as exc:
        S.plan_pull([f"SYM{i}" for i in range(50)])
    assert "50 symbol" in str(exc.value)


def test_an_unreadable_usage_response_does_not_block_the_pull(monkeypatch):
    """/usage is advisory. If it cannot be read, proceed rather than refuse."""
    monkeypatch.setattr(S, "remaining_quota", lambda: None)
    assert S.plan_pull(["A", "B"])["ok"]


# ---------------------------------------------------------------------------
# The report on a wide pull
# ---------------------------------------------------------------------------

def _synthetic(symbol: str, drift: float, days: int = 8) -> dict:
    base = 100.0
    rows = []
    for i in range(days):
        base *= 1 + drift
        rows.append({
            "symbol": symbol, "date": date(2026, 7, 1) + timedelta(days=i),
            "open": base * 0.99, "high": base * 1.02, "low": base * 0.98,
            "close": round(base, 2), "adjclose": base, "volume": 10_000 + i,
            "synthetic": False, "currency": "INR", "repaired": False,
            "repairs": [],
        })
    T._derive(rows)
    return {
        "symbol": symbol, "currency": "INR", "interval": "1d",
        "rows": rows, "quarantined": [],
        "summary": T._summarise(symbol, rows, rows, [], True),
    }


@pytest.fixture
def wide():
    """40 symbols with a spread of returns, as a full pull would give."""
    return [_synthetic(f"SYM{i:02d}.NS", (i - 20) / 1000)
            for i in range(40)]


@pytest.fixture
def wide_doc(wide):
    return R.build_report(wide, "WIDE", T.metrics)


def test_the_comparison_chart_is_capped_so_it_stays_readable(wide):
    """A line chart of forty series shows nothing."""
    figure, trimmed = R.comparison_figure(wide)
    assert trimmed is True
    assert len(figure["data"]) == R.MAX_COMPARISON_SERIES


def test_the_capped_chart_keeps_the_biggest_movers(wide):
    """If only six are charted, they should be the six worth looking at."""
    figure, _ = R.comparison_figure(wide)
    charted = {t["name"] for t in figure["data"]}
    assert "SYM39.NS" in charted   # largest riser
    assert "SYM00.NS" in charted   # largest faller


def test_a_trimmed_chart_says_it_was_trimmed(wide_doc):
    """A reader must not think six symbols is all there was."""
    assert "largest movers" in wide_doc


def test_every_symbol_appears_in_the_ranked_table(wide, wide_doc):
    """Charts are capped; the table is not. Nothing is hidden."""
    for result in wide:
        assert result["summary"]["symbol"] in wide_doc


def test_detail_sections_are_capped(wide_doc):
    assert wide_doc.count("<h2>SYM") <= R.MAX_DETAIL_SECTIONS


def test_the_ranked_table_is_ordered_by_return(wide_doc):
    """Best first: the ordering is the point of the table."""
    symbols = re.findall(r"<tr><td>(SYM\d+\.NS)</td>", wide_doc)
    assert symbols[0] == "SYM39.NS"
    assert symbols[-1] == "SYM00.NS"


def test_a_wide_report_still_embeds_the_bundle_only_once(wide_doc):
    """Forty symbols means many charts; the bundle must not repeat."""
    assert wide_doc.count("plotly-bundle") == 1


def test_a_narrow_pull_charts_everything(wide):
    """The caps must not kick in on a small pull."""
    few = wide[:3]
    figure, trimmed = R.comparison_figure(few)
    assert trimmed is False
    assert len(figure["data"]) == 3
    document = R.build_report(few, "NARROW", T.metrics)
    assert "largest movers" not in document
    assert document.count("<h2>SYM") == 3


# ---------------------------------------------------------------------------
# The bundled symbol file
# ---------------------------------------------------------------------------

def test_the_bundled_universe_loads():
    universe = S.load_symbol_file()
    assert len(universe) > 100


def test_no_comment_text_leaks_into_a_symbol():
    """Company names sit beside tickers as comments; they must be stripped."""
    for symbol in S.load_symbol_file():
        assert "#" not in symbol
        assert " " not in symbol
        assert symbol == symbol.strip()


def test_the_universe_has_no_duplicates():
    universe = S.load_symbol_file()
    assert len(universe) == len(set(universe))


def test_the_universe_covers_both_indian_venues():
    """SEC3-103 wants at least two NSE or BSE instruments; this has both."""
    grouped = S.group_by_exchange(S.load_symbol_file())
    assert grouped["NSE"] > 50
    assert grouped["BSE"] > 10


def test_every_symbol_carries_an_indian_venue_suffix():
    for symbol in S.load_symbol_file():
        assert symbol.endswith((".NS", ".BO")), symbol


def test_file_order_is_preserved(tmp_path):
    """A --limit'd pull takes the first N, so order is meaningful."""
    path = tmp_path / "u.txt"
    path.write_text("# header\nZZZ.NS  # last alphabetically\nAAA.NS\n\nBBB.BO\n")
    assert S.load_symbol_file(path) == ["ZZZ.NS", "AAA.NS", "BBB.BO"]


def test_a_repeated_symbol_in_the_file_is_dropped(tmp_path):
    path = tmp_path / "u.txt"
    path.write_text("A.NS\nB.NS\nA.NS\n")
    assert S.load_symbol_file(path) == ["A.NS", "B.NS"]


def test_a_missing_symbol_file_is_reported_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        S.load_symbol_file(tmp_path / "nope.txt")
