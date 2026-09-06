"""Dashboard: the live view of the analytical store.

Replaces the one-shot HTML report as the pipeline's front end. The difference
that matters is not that it is prettier -- the report described the run that
wrote it, and this describes the STORE, so it is current the moment a run
finishes without anything having to regenerate it. Every panel is a query
against `warehouse.duckdb`, and the SQL console is there for the question the
panels do not answer.

    python -m ETL_Analysis.dashboard                  # launch it
    python -m ETL_Analysis.dashboard --db my.duckdb   # a different store
    python -m ETL_Analysis.pipeline --dashboard       # run, then launch

`report.py` is still there and still works, behind the pipeline's
`--legacy-report` flag: a served page is not a committed artefact, and the
sprint asks for one of those too.

HOW IT STAYS CURRENT
    Reads are cached against `store.store_stamp` -- the store's path, mtime
    and size. A pipeline run changes the file, so the next page render misses
    the cache and re-reads; nothing else does. That is what makes "updates on
    every run" true without polling and without a stale window.

    Connections are opened per read and closed immediately. DuckDB allows many
    readers or one writer, so a dashboard that held the file open would block
    the next run from writing to it.

WHAT IS COMPUTED WHERE
    Nothing is aggregated here. Rows come out of `store`, `transform` computes
    the measures over them, `charts` builds the figures. This module decides
    layout and nothing else, so a number on screen is one the transform tests
    already cover.

DESIGN
    One filter rail on the left, scoping every tab the same way. Figures come
    from `charts.py` and its validated colour-blind-safe palette, every chart
    has the table it was drawn from beside it, and both axes are titled on
    every figure.
"""

from __future__ import annotations

import argparse
import html as html_module
import os
import subprocess
import sys
from pathlib import Path

# `streamlit run` executes this file as a script rather than importing it as
# part of the package, so there is no package context for a relative import to
# resolve against. Absolute imports, with the project root put on the path when
# it is missing, work under `streamlit run`, under `python -m`, and under
# `import ETL_Analysis.dashboard` alike.
if __package__ in (None, ""):  # pragma: no cover - only under `streamlit run`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ETL_Analysis import charts, claims as claims_module, store
from ETL_Analysis import report as report_module
from ETL_Analysis import transform as transform_module

APP_TITLE = "Market data pipeline"
DEFAULT_DB_PATH = store.DEFAULT_DB_PATH

#: Symbols charted in the disposition bar before it stops being one screen.
MAX_DISPOSITION_BARS = 40

# --- Cache policy ----------------------------------------------------------
# Reads are keyed on the store's stamp, so a pipeline run invalidates them.
# Two things that key alone does not solve, and these constants do:
#
# ENTRIES -- the key also includes the filter selection, and there are 2^144
#   symbol selections. Every distinct one would otherwise retain its own copy
#   of the rows forever; a full-universe slice pickles to about 6.4MB, so a
#   handful of filter changes is tens of megabytes held for good. The slice
#   cache is therefore deliberately small: re-reading the store takes about a
#   second, and holding twenty of them does not.
#
# TTL -- the stamp is (path, mtime, size). A write that changes neither -- same
#   size, inside one filesystem timestamp tick -- would go unnoticed until the
#   reader pressed Reload. The TTL bounds how long that can last without
#   anyone having to know it is a possibility.
SLICE_CACHE_ENTRIES = 4
LIGHT_CACHE_ENTRIES = 32
CACHE_TTL_SECONDS = 300

#: Queries offered in the console, as (title, sql). Written to be read as much
#: as run: each one demonstrates a column or an invariant worth knowing about.
EXAMPLE_QUERIES = [
    ("What landed, per symbol", """SELECT symbol,
       count(*)        AS trading_days,
       min(trade_date) AS first_day,
       max(trade_date) AS last_day
  FROM daily_price
 GROUP BY symbol
 ORDER BY trading_days DESC, symbol"""),
    ("Observed rows only", """-- Neither repaired by us nor interpolated by the
-- vendor: the rows a claim can rest on unaided.
SELECT symbol, trade_date, "close", volume
  FROM daily_price
 WHERE NOT synthetic AND NOT repaired
 ORDER BY symbol, trade_date
 LIMIT 200"""),
    ("Biggest movers, latest run", """SELECT symbol, value AS period_return_pct
  FROM run_metric
 WHERE metric = 'period_return_pct'
   AND run_id = (SELECT run_id FROM load_run
                  ORDER BY loaded_at DESC LIMIT 1)
 ORDER BY value DESC"""),
    ("Volatility league table", """SELECT symbol, value AS daily_volatility_pct
  FROM run_metric
 WHERE metric = 'volatility_pct'
   AND run_id = (SELECT max(run_id) FROM run_metric)
 ORDER BY value DESC"""),
    ("What was rejected, and why", """SELECT symbol, reason, raw_date, detail
  FROM quarantined_candle
 ORDER BY symbol, raw_date"""),
    ("Reconciliation check", """-- Empty is the healthy answer: every candle that
-- arrived was either loaded or quarantined.
SELECT run_id, symbol, candles_in, rows_kept, rows_quarantined
  FROM load_run
 WHERE candles_in <> rows_kept + rows_quarantined"""),
    ("How a measure moved between runs", """SELECT run_id, symbol, value
  FROM run_metric
 WHERE metric = 'period_return_pct'
   AND symbol IN ('RELIANCE.NS', 'INFY.NS')
 ORDER BY run_id"""),
    ("The load history", """SELECT run_id, count(*) AS symbols,
       sum(rows_kept)        AS rows_loaded,
       sum(rows_quarantined) AS quarantined,
       max(loaded_at)        AS loaded_at
  FROM load_run
 GROUP BY run_id
 ORDER BY loaded_at DESC"""),
]


# ---------------------------------------------------------------------------
# Presentation helpers. Pure: values in, strings out, no streamlit -- so the
# numbers the page shows can be asserted without rendering a page.
# ---------------------------------------------------------------------------

def format_value(value, unit: str) -> str:
    """Render a measure for display.

    Delegates to the report's formatter, so a number is written the same way
    wherever it appears and there is one place to change it.
    """
    return report_module.format_value(value, unit)


def compact(value, unit: str = "") -> str:
    """A figure for a stat tile: 12,904 stays; 1,290,400 becomes 1.29m."""
    if value is None:
        return "-"
    number = float(value)
    if unit == "pct":
        return f"{number:+,.2f}%"
    for cutoff, suffix in ((1_000_000_000, "bn"), (1_000_000, "m")):
        if abs(number) >= cutoff:
            return f"{number / cutoff:,.2f}{suffix}"
    return f"{number:,.0f}"


def date_span(lo, hi) -> str:
    """A period, written the shortest way that stays unambiguous."""
    if not lo or not hi:
        return "-"
    if lo.year == hi.year:
        return f"{lo:%d %b} - {hi:%d %b %Y}"
    return f"{lo:%d %b %Y} - {hi:%d %b %Y}"


def totals_for(results: list[dict]) -> dict:
    """Roll a set of results up into the figures the stat strip shows."""
    loaded = sum(r["summary"]["rows_kept"] for r in results)
    repaired = sum(r["summary"].get("rows_repaired", 0) for r in results)
    dates = [r["summary"][key] for r in results
             for key in ("date_from", "date_to") if r["summary"].get(key)]
    returns = [r["summary"]["period_return_pct"] for r in results
               if r["summary"].get("period_return_pct") is not None]
    return {
        "symbols": len(results),
        "rows_loaded": loaded,
        "rows_clean": loaded - repaired,
        "rows_repaired": repaired,
        "rows_quarantined": sum(r["summary"]["rows_quarantined"]
                                for r in results),
        "candles_in": sum(r["summary"]["candles_in"] for r in results),
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
        "advancers": sum(1 for value in returns if value > 0),
        "decliners": sum(1 for value in returns if value < 0),
    }


def leaderboard_rows(results: list[dict]) -> list[dict]:
    """Every symbol, ranked by return. Charts are capped; this is not."""
    ranked = sorted(
        [r for r in results if r["rows"]],
        key=lambda r: r["summary"].get("period_return_pct") or 0.0,
        reverse=True,
    )
    return [{
        "Symbol": r["summary"]["symbol"],
        "Return %": r["summary"].get("period_return_pct"),
        "Volatility %": r["summary"].get("volatility_pct"),
        "Max drawdown %": r["summary"].get("max_drawdown_pct"),
        "Last close": r["summary"].get("close_last"),
        "Trading days": r["summary"].get("trading_days"),
        "Avg volume": r["summary"].get("avg_volume"),
        "Repaired": r["summary"].get("rows_repaired", 0),
        "Quarantined": r["summary"].get("rows_quarantined", 0),
    } for r in ranked]


def price_table_rows(result: dict) -> list[dict]:
    """The rows behind a symbol's charts -- the table view every figure needs."""
    return [{
        "Date": row["date"],
        "Open": row["open"],
        "High": row["high"],
        "Low": row["low"],
        "Close": row["close"],
        "Volume": row["volume"],
        "Return %": row.get("daily_return_pct"),
        "Turnover": row.get("turnover"),
        "Synthetic": row["synthetic"],
        "Repaired": row["repaired"],
    } for row in result["rows"]]


def repair_table_rows(results: list[dict]) -> list[dict]:
    """One row per repair, not per repaired row: a row can carry two."""
    return [{
        "Symbol": row["symbol"],
        "Date": row["date"],
        "Repair": entry.get("code"),
        "What changed": entry.get("detail"),
    } for result in results for row in result["rows"] if row["repaired"]
        for entry in row["repairs"]]


def quarantine_table_rows(results: list[dict]) -> list[dict]:
    """Every rejected candle, with the date exactly as it arrived."""
    return [{
        "Symbol": bad["symbol"],
        "Date as received": (bad["candle"].get("date")
                             if isinstance(bad["candle"], dict) else None),
        "Reason": bad["reason"],
        "Detail": bad["detail"],
    } for result in results for bad in result["quarantined"]]


def measure_cards(result: dict) -> list[dict]:
    """The measures for one symbol, as label/value pairs ready to render.

    Row counts are dropped: they are dispositions rather than measures, and
    the data-quality tab is where they belong.
    """
    return [{"metric": m["metric"],
             "label": m["label"],
             "value": format_value(m["value"], m["unit"])}
            for m in transform_module.metrics(result)
            if m["unit"] != "rows"]


def plotly_available() -> bool:
    """Whether charts can be drawn.

    `st.plotly_chart` reaches for `plotly.tools`, so a missing plotly surfaces
    as a traceback in the middle of the page rather than as a message. The
    page checks first and says what to install -- and keeps going, because
    every chart here has a table beside it carrying the same numbers, so a
    dashboard without plotly is degraded rather than useless.
    """
    try:
        import plotly.tools  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - absent, or a stub without the submodule
        return False


PLOTLY_MISSING_NOTE = (
    "Charts need plotly, which is not installed: `pip install plotly`. "
    "Every table on this page carries the same numbers in the meantime."
)


def run_pipeline_from_app(db_path: str, symbols: list, interval: str | None,
                          live: bool = False) -> dict:
    """Run the pipeline into `db_path` and report what happened.

    Kept out of the page so it can be tested without rendering one, and so
    the UI has nothing to do but show the sentence this returns.

    Every failure is caught and described. A run started from a button has no
    console to print a traceback to, and a page that dies mid-render tells the
    reader nothing about whether their data landed.

    `pipeline` is imported here rather than at module scope on purpose: it
    imports this module for its own `--dashboard` flag, and a cycle that
    resolves only because of the order the two happen to be imported in is a
    trap for whoever edits the imports next.
    """
    from ETL_Analysis import pipeline as pipeline_module

    symbols = [s.strip() for s in symbols if s.strip()]
    if not symbols:
        return {"ok": False, "message": "Name at least one symbol to pull."}

    extract_fn = None
    if live:
        try:
            from .extract_live import extract as extract_fn  # noqa: F401
        except ImportError as exc:
            return {"ok": False,
                    "message": f"The live client is unavailable: {exc}"}

    try:
        code = pipeline_module.run(symbols, extract_fn=extract_fn,
                                   db_path=db_path, interval=interval)
    except Exception as exc:  # noqa: BLE001 - a button has no stderr
        return {"ok": False, "message": f"The run failed: {exc}"}

    if code != 0:
        return {"ok": False,
                "message": ("The run finished with errors and may have loaded "
                            "nothing. Check the terminal for the log.")}
    asked = f" at {interval}" if interval else ""
    return {"ok": True,
            "message": (f"Loaded {len(symbols)} symbol(s){asked}. "
                        f"The page is showing the new data.")}


def default_run_symbols() -> list:
    """What to prefill the run form with. Lazy for the same cycle reason."""
    from ETL_Analysis import pipeline as pipeline_module
    return list(pipeline_module.DEFAULT_SYMBOLS)


def _escape(text) -> str:
    return html_module.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------

CSS = """
<style>
  :root {
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --line: #e1e0d9; --surface: #fcfcfb; --page: #f9f9f7;
    --good: #0ca30c; --bad: #d03b3b;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  .stApp { background: var(--page); }
  .block-container { padding-top: 2.1rem; padding-bottom: 4rem; max-width: 1500px; }
  header[data-testid="stHeader"] { background: transparent; }

  html, body, [class*="st-"], .stMarkdown { color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }

  /* Masthead */
  .masthead { border-bottom: 1px solid var(--line); padding-bottom: 13px; }
  .masthead h1 { font-size: 21px; font-weight: 620; letter-spacing: -0.012em;
                 margin: 0 0 6px; }
  .meta { font-size: 12.5px; color: var(--ink-2); }
  .meta code, .lede code, .foot code { background: #f0efec; border: 1px solid var(--line);
      padding: 1px 6px; border-radius: 3px; font-size: 11.5px; font-family: var(--mono); }
  .sep { color: #c3c2b7; padding: 0 9px; }

  /* Stat strip */
  .stats { display: flex; flex-wrap: wrap; gap: 0; border: 1px solid var(--line);
           border-radius: 5px; background: var(--surface); margin: 18px 0 2px; }
  .stat { flex: 1 1 132px; padding: 13px 18px; border-right: 1px solid var(--line); }
  .stat:last-child { border-right: none; }
  .stat .k { font-size: 10.5px; font-weight: 600; letter-spacing: .085em;
             text-transform: uppercase; color: var(--muted); display: block;
             margin-bottom: 6px; white-space: nowrap; }
  .stat .v { font-size: 22px; font-weight: 600; line-height: 1.15;
             letter-spacing: -0.015em; }
  .stat .v.sm { font-size: 15px; font-weight: 600; padding-top: 6px; }
  .stat .v.good { color: var(--good); }
  .stat .v.bad { color: var(--bad); }
  .stat .sub { font-size: 11.5px; color: var(--muted); margin-top: 4px; }

  /* Sections */
  .sec { font-size: 10.5px; font-weight: 650; letter-spacing: .1em;
         text-transform: uppercase; color: var(--muted);
         border-bottom: 1px solid var(--line); padding-bottom: 6px;
         margin: 28px 0 2px; }
  .lede { font-size: 13px; color: var(--ink-2); margin: 10px 0 2px;
          max-width: 80ch; line-height: 1.55; }
  .foot { font-size: 11.5px; color: var(--muted); margin: 6px 0 0;
          max-width: 92ch; line-height: 1.5; }

  /* Measures grid */
  .measures { display: grid; gap: 1px; background: var(--line);
              border: 1px solid var(--line); border-radius: 5px; overflow: hidden;
              grid-template-columns: repeat(auto-fill, minmax(172px, 1fr)); }
  .measure { background: var(--surface); padding: 10px 13px; }
  .measure .k { font-size: 10.5px; color: var(--muted); display: block;
                margin-bottom: 3px; line-height: 1.35; }
  .measure .v { font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }

  /* Pills */
  .pill { display: inline-block; padding: 2px 9px; border-radius: 3px;
          font-size: 11px; font-weight: 600; }
  .pill.ok { background: #e6f5e6; color: #0a6b0a; border: 1px solid #c6e8c6; }
  .pill.bad { background: #fbe9e9; color: #9c1f1f; border: 1px solid #f2cccc; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--line); }
  .stTabs [data-baseweb="tab"] { height: 40px; padding: 0 16px; font-size: 13.5px;
      font-weight: 550; color: var(--ink-2); background: transparent; }
  .stTabs [aria-selected="true"] { color: var(--ink); box-shadow: inset 0 -2px 0 var(--ink); }

  /* Rail */
  section[data-testid="stSidebar"] { background: var(--surface);
      border-right: 1px solid var(--line); }
  .railhead { font-size: 10.5px; font-weight: 650; letter-spacing: .1em;
              text-transform: uppercase; color: var(--muted);
              border-bottom: 1px solid var(--line); padding-bottom: 6px;
              margin: 18px 0 10px; }

  /* Tables & schema */
  [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 5px; }
  .schema { font-family: var(--mono); font-size: 11.5px; line-height: 1.7;
            color: var(--ink-2); }
  .schema b { color: var(--ink); font-weight: 600; }
  .schema .t { color: var(--muted); }
</style>
"""


def stat_tile(key: str, value: str, sub: str = "", tone: str = "",
              small: bool = False) -> str:
    """One cell of the stat strip.

    Values use proportional figures rather than tabular: equal-width digits
    make a large standalone number look loose. Tabular figures are for the
    tables and the measures grid, where digits line up vertically.
    """
    classes = " ".join(filter(None, ["v", "sm" if small else "", tone]))
    sub_html = f'<div class="sub">{_escape(sub)}</div>' if sub else ""
    return (f'<div class="stat"><span class="k">{_escape(key)}</span>'
            f'<div class="{classes}">{_escape(value)}</div>{sub_html}</div>')


def stat_strip(tiles: list[str]) -> str:
    return f'<div class="stats">{"".join(tiles)}</div>'


def masthead(path: str, run_id: str | None, loaded_at, note: str = "") -> str:
    """The one line that says which store, which run, and when."""
    when = f"{loaded_at:%d %b %Y, %H:%M}" if loaded_at else "never"
    parts = [
        f'<code>{_escape(path)}</code>',
        f'latest run <code>{_escape(run_id or "none")}</code>',
        f'loaded {_escape(when)}',
    ]
    body = '<span class="sep">|</span>'.join(parts)
    extra = f'<div class="meta" style="margin-top:5px">{_escape(note)}</div>' if note else ""
    return (f'<div class="masthead"><h1>{_escape(APP_TITLE)}</h1>'
            f'<div class="meta">{body}</div>{extra}</div>')


# ---------------------------------------------------------------------------
# The app. Everything below needs streamlit, which is imported inside the
# function so the helpers above stay importable -- and testable -- without it.
# ---------------------------------------------------------------------------

def run_app(db_path: str = DEFAULT_DB_PATH) -> None:
    """Render the whole dashboard. Called only under `streamlit run`."""
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    can_chart = plotly_available()

    def chart(figure, empty: str = "Nothing to chart in the current scope."):
        """Draw a figure, or say why there is nothing to look at."""
        if figure is None:
            st.info(empty)
        elif not can_chart:
            st.warning(PLOTLY_MISSING_NOTE)
        else:
            st.plotly_chart(figure, use_container_width=True,
                            config=charts.PLOTLY_CONFIG)

    # --- cached reads ---------------------------------------------------
    # Keyed on the store's stamp, so a pipeline run invalidates all of them
    # and nothing else does. `stamp` deliberately has no leading underscore:
    # streamlit excludes underscore-prefixed arguments from the cache key, and
    # this is the argument the whole scheme depends on.
    #
    # Each function opens and closes the store itself. Caching a connection
    # instead would hold DuckDB's single-writer lock and block the next run.

    @st.cache_data(max_entries=LIGHT_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner=False)
    def read_overview(path: str, stamp: tuple, interval: str | None) -> dict:
        with store.connect(path) as handle:
            if not store.has_tables(handle):
                return {"empty": True, "snapshot": handle.used_snapshot}
            lo, hi = store.date_bounds(handle, interval)
            return {
                "empty": False,
                "snapshot": handle.used_snapshot,
                "intervals": store.intervals(handle),
                "universe": store.universe(handle, interval),
                "runs": store.runs(handle),
                "latest_run": store.latest_run_id(handle),
                "reconciliation": store.reconciliation(handle),
                "date_lo": lo, "date_hi": hi,
                "metrics": store.available_metrics(handle),
                "schema": store.schema(handle),
            }

    @st.cache_data(max_entries=SLICE_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner="Reading the store")
    def read_slice(path: str, stamp: tuple, symbols: tuple, lo, hi,
                   no_repaired: bool, no_synthetic: bool,
                   interval: str | None) -> list:
        with store.connect(path) as handle:
            prices = store.price_records(
                handle, symbols=list(symbols), date_from=lo, date_to=hi,
                exclude_repaired=no_repaired, exclude_synthetic=no_synthetic,
                interval=interval)
            bad = store.quarantine_records(handle, symbols=list(symbols))
        # No `candles_in` from the ledger: these rows are a filtered subset,
        # so the honest denominator is what is in hand rather than what some
        # past run received. Reconciliation is checked against the ledger
        # separately, where that comparison does mean something.
        return store.build_results(prices, bad)

    @st.cache_data(max_entries=LIGHT_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner=False)
    def read_reasons(path: str, stamp: tuple, symbols: tuple) -> list:
        with store.connect(path) as handle:
            return store.quarantine_reasons(handle, symbols=list(symbols))

    @st.cache_data(max_entries=LIGHT_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner=False)
    def read_ledger(path: str, stamp: tuple, run_id) -> list:
        with store.connect(path) as handle:
            return store.ledger(handle, run_id=run_id)

    @st.cache_data(max_entries=LIGHT_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner=False)
    def read_metric_history(path: str, stamp: tuple, metric: str,
                            symbols: tuple) -> list:
        with store.connect(path) as handle:
            return store.metric_history(handle, metric, list(symbols))

    @st.cache_data(max_entries=LIGHT_CACHE_ENTRIES, ttl=CACHE_TTL_SECONDS,
                   show_spinner="Working out the claims")
    def read_claims(path: str, stamp: tuple) -> dict:
        """Generate the claims from the store, and fetch the data-quality
        tables that justify what they exclude.

        Keyed on the store stamp like every other read, so a pipeline run
        re-derives the claims rather than leaving the previous run's sentences
        on screen under new data.
        """
        with store.connect(path) as handle:
            return {
                "findings": claims_module.generate(handle),
                "venue_gap": store.records(
                    handle, claims_module.VENUE_DISAGREEMENT_SQL),
                "dual_listed": store.records(
                    handle, claims_module.DUAL_LISTED_RETURNS_SQL),
                "interpolation": store.records(
                    handle, claims_module.INTERPOLATION_BY_QUARTER_SQL),
            }

    readers = (read_overview, read_slice, read_reasons, read_ledger,
               read_metric_history, read_claims)

    def refresh() -> None:
        """Drop this app's cached reads, and nothing else.

        `st.cache_data.clear()` would empty every cached function in the
        process, including any other app sharing it. Clearing the readers by
        name keeps the blast radius to this page, and is what both the Reload
        button and a pipeline run triggered from the app call.
        """
        for reader in readers:
            reader.clear()

    # --- the filter rail, scoping every tab the same way -----------------
    with st.sidebar:
        st.markdown('<div class="railhead">Store</div>', unsafe_allow_html=True)
        path = st.text_input("DuckDB file", value=db_path,
                             label_visibility="collapsed")
        if st.button("Reload from disk", use_container_width=True):
            refresh()

        stamp = store.store_stamp(path)
        try:
            available = read_overview(path, stamp, None)
        except store.StoreUnavailable as exc:
            st.error(str(exc))
            st.stop()

        if available["empty"]:
            st.warning("That store has no pipeline tables yet. Run "
                       "`python -m ETL_Analysis.pipeline` first.")
            st.stop()

        # --- granularity -------------------------------------------------
        # Picked before anything else, because it decides which rows exist.
        # A view that mixed a weekly candle with a daily one would be drawing
        # two different measurements as one series.
        loaded_intervals = available.get("intervals") or []
        if len(loaded_intervals) > 1:
            interval = st.radio(
                "Candle interval", loaded_intervals, horizontal=True,
                help="Granularities the store actually holds. Everything on "
                     "the page is one interval at a time -- mixing them would "
                     "draw a weekly bar beside a daily one as if they were "
                     "the same measurement.")
        else:
            interval = loaded_intervals[0] if loaded_intervals else None

        overview = (read_overview(path, stamp, interval)
                    if len(loaded_intervals) > 1 else available)

        universe = overview["universe"]
        if not universe:
            st.warning("The tables are there but no rows have been loaded.")
            st.stop()

        venues = sorted({row["exchange"] for row in universe if row["exchange"]})
        st.markdown('<div class="railhead">Scope</div>', unsafe_allow_html=True)
        chosen_venues = st.multiselect("Venue", venues, default=venues)
        in_venue = [row["symbol"] for row in universe
                    if row["exchange"] in chosen_venues]
        if not in_venue:
            st.warning("No symbols on the selected venues.")
            st.stop()

        symbols = st.multiselect(
            f"Symbols ({len(in_venue)} available)", in_venue,
            default=in_venue[:6],
            help="Leave this empty to read every symbol on the venues above.")
        selection = tuple(symbols or in_venue)

        lo_bound, hi_bound = overview["date_lo"], overview["date_hi"]
        window = st.date_input("Trading days", value=(lo_bound, hi_bound),
                               min_value=lo_bound, max_value=hi_bound)
        lo, hi = (window if isinstance(window, (list, tuple))
                  and len(window) == 2 else (lo_bound, hi_bound))

        st.markdown('<div class="railhead">Provenance</div>',
                    unsafe_allow_html=True)
        no_repaired = st.checkbox(
            "Exclude repaired rows",
            help="Rows the transform corrected. A claim that must rest only "
                 "on observed data should exclude them.")
        no_synthetic = st.checkbox(
            "Exclude vendor-interpolated rows",
            help="Candles the provider flagged synthetic: interpolated by "
                 "them, not observed.")

        # --- run the pipeline from here ----------------------------------
        st.markdown('<div class="railhead">Load more data</div>',
                    unsafe_allow_html=True)
        with st.form("run_pipeline"):
            requested_interval = st.text_input(
                "Interval to request", value=interval or "1d",
                help="Passed to the API as the candle granularity. Rows are "
                     "stamped with what the response actually carried, not "
                     "what was asked for.")
            run_symbols = st.text_input(
                "Symbols", value=" ".join(default_run_symbols()),
                help="Space-separated. Offline these must be fixture symbols.")
            go_live = st.checkbox(
                "Use the live API", value=False,
                help="Needs FAUXNANCE_API_KEY. Unticked, the run serves the "
                     "bundled fixtures, which are daily whatever interval is "
                     "requested.")
            launched = st.form_submit_button("Run the pipeline",
                                             use_container_width=True)

        if launched:
            outcome = run_pipeline_from_app(
                path, run_symbols.split(), requested_interval.strip() or None,
                live=go_live)
            # The store has changed, so every cached read is now stale. This
            # is the reason `refresh` clears by name rather than globally.
            refresh()
            # Stashed rather than rendered here: `st.rerun` throws the current
            # render away, and a message written before it is never seen. The
            # next run picks it up below.
            st.session_state["run_outcome"] = outcome
            st.rerun()

        outcome = st.session_state.pop("run_outcome", None)
        if outcome:
            (st.success if outcome["ok"] else st.error)(outcome["message"])

        st.markdown(
            f'<p class="foot">{len(universe)} symbols in the store &middot; '
            f'{len(overview["runs"])} runs recorded'
            + (f' &middot; {interval} candles' if interval else '')
            + '</p>', unsafe_allow_html=True)

    if overview["snapshot"]:
        st.warning("A pipeline run is holding the store open, so this page is "
                   "reading a copy taken just now. Reload once the run "
                   "finishes for live numbers.")

    results = read_slice(path, stamp, selection, lo, hi,
                         no_repaired, no_synthetic, interval)
    totals = totals_for(results)
    reconciled = not overview["reconciliation"]
    latest = next((r for r in overview["runs"]
                   if r["run_id"] == overview["latest_run"]), None)

    excluded = [name for name, active in (
        ("repaired rows", no_repaired),
        ("vendor-interpolated rows", no_synthetic)) if active]
    note = (f"Excluding {' and '.join(excluded)}; every measure below is "
            f"recomputed over what is left." if excluded else "")

    st.markdown(masthead(path, overview["latest_run"],
                         latest["loaded_at"] if latest else None, note),
                unsafe_allow_html=True)

    st.markdown(stat_strip([
        stat_tile("Symbols", f"{totals['symbols']:,}",
                  f"{len(universe)} in the store"),
        stat_tile("Rows in scope", compact(totals["rows_loaded"]),
                  date_span(totals["date_from"], totals["date_to"])),
        stat_tile("Advancing", f"{totals['advancers']:,}",
                  f"{totals['decliners']:,} declining",
                  tone="good" if totals["advancers"] >= totals["decliners"]
                  else "bad"),
        stat_tile("Repaired", f"{totals['rows_repaired']:,}",
                  "loaded with a flag",
                  tone="bad" if totals["rows_repaired"] else ""),
        stat_tile("Quarantined", f"{totals['rows_quarantined']:,}",
                  "kept, not loaded",
                  tone="bad" if totals["rows_quarantined"] else ""),
        stat_tile("Reconciliation", "Balanced" if reconciled else "Failed",
                  "candles in = loaded + quarantined" if reconciled
                  else f"{len(overview['reconciliation'])} ledger rows disagree",
                  tone="good" if reconciled else "bad", small=True),
    ]), unsafe_allow_html=True)

    (overview_tab, claims_tab, instrument_tab, quality_tab, runs_tab,
     console_tab) = st.tabs(
        ["Overview", "Claims", "Instrument", "Data quality", "Runs",
         "SQL console"])

    # =====================================================================
    # Overview
    # =====================================================================
    with overview_tab:
        if not results:
            st.info("No rows match the current scope. Widen the date range or "
                    "pick more symbols.")
        else:
            st.markdown('<div class="sec">Relative performance</div>',
                        unsafe_allow_html=True)
            figure, trimmed = charts.comparison_figure(results)
            if figure:
                charted = len([r for r in results if len(r["rows"]) >= 2])
                trim_note = (
                    f" Showing the {charts.MAX_COMPARISON_SERIES} largest "
                    f"movers of {charted} symbols in scope; the table below "
                    f"covers every one of them." if trimmed else "")
                st.markdown(
                    f'<p class="lede">Each line starts at 100 on its own '
                    f'first trading day, so a line at 104 has risen 4% since '
                    f'then. Rebasing is what lets instruments at very '
                    f'different price levels share one axis.{trim_note}</p>',
                    unsafe_allow_html=True)
                chart(figure)
            else:
                st.info("A series needs at least two trading days to chart. "
                        "Widen the date range.")

            st.markdown('<div class="sec">Every symbol in scope, ranked by '
                        'return</div>', unsafe_allow_html=True)
            table = pd.DataFrame(leaderboard_rows(results))
            st.dataframe(
                table, use_container_width=True, hide_index=True,
                column_config={
                    "Return %": st.column_config.NumberColumn(format="%+.2f"),
                    "Volatility %": st.column_config.NumberColumn(format="%.2f"),
                    "Max drawdown %": st.column_config.NumberColumn(format="%.2f"),
                    "Last close": st.column_config.NumberColumn(format="%.2f"),
                    "Avg volume": st.column_config.NumberColumn(format="%.0f"),
                })
            st.download_button(
                "Download this table as CSV",
                table.to_csv(index=False).encode("utf-8"),
                file_name="symbols_ranked_by_return.csv", mime="text/csv")

            st.markdown('<div class="sec">Disposition of every candle '
                        'received</div>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="lede">{totals["candles_in"]:,} candles in scope: '
                f'{totals["rows_clean"]:,} loaded clean, '
                f'{totals["rows_repaired"]:,} loaded after repair, '
                f'{totals["rows_quarantined"]:,} quarantined. Nothing is '
                f'dropped, so the bars add up to what arrived.</p>',
                unsafe_allow_html=True)
            shown = results[:MAX_DISPOSITION_BARS]
            disposition = charts.disposition_figure(shown)
            if disposition:
                if len(shown) < len(results):
                    st.markdown(
                        f'<p class="foot">Charting the {len(shown)} symbols '
                        f'that moved most, of {len(results)} in scope. The '
                        f'counts above cover all of them.</p>',
                        unsafe_allow_html=True)
                chart(disposition)

    # =====================================================================
    # Claims
    # =====================================================================
    with claims_tab:
        checked = read_claims(path, stamp)
        findings = checked["findings"]
        supported = [f for f in findings if f.available]
        unsupported = [f for f in findings if not f.available]

        st.markdown(
            '<p class="lede">Claims about this data, each one a sentence that '
            'could turn out to be wrong. <b>None of the numbers is typed.</b> '
            'The questions are fixed; the answers are computed from the store '
            'each time this tab is opened, so a run over different symbols or '
            'a different window produces different claims rather than the '
            'same sentences with stale figures in them.</p>'
            '<p class="foot"><b>This tab ignores the filters in the rail.</b> '
            'Each claim derives its own period and universe from the store - '
            'that is what makes it a claim rather than a view - so narrowing '
            'the selection on the left would quietly change what the sentence '
            'was about. Every other tab follows the rail.</p>',
            unsafe_allow_html=True)

        context_row = supported[0] if supported else None
        st.markdown(stat_strip([
            stat_tile("Claims", f"{len(supported)} of {len(findings)}",
                      "supported by this store",
                      tone="good" if not unsupported else "bad"),
            stat_tile("Universe",
                      context_row.period.split(",")[-1].strip()
                      if context_row else "-",
                      "one listing per company, observed rows",
                      small=True),
            stat_tile("Period",
                      ", ".join(context_row.period.split(",")[:1])
                      if context_row else "-",
                      "derived from the store", small=True),
            stat_tile("Written", "generated", "no figure is hard-coded",
                      small=True),
        ]), unsafe_allow_html=True)

        if unsupported:
            st.warning(
                "This store cannot support every claim:\n\n"
                + "\n\n".join(f"**{f.title}** - {f.reason}"
                                for f in unsupported))

        def claim_block(index: int, finding, figure, lede: str,
                        table_note: str = "") -> None:
            st.markdown(
                f'<div class="sec">Claim {index} &middot; '
                f'{_escape(finding.title)}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="lede" style="font-size:14.5px;color:var(--ink)">'
                f'{_escape(finding.headline)}</p>'
                f'<p class="foot"><b>Period.</b> {_escape(finding.period)}<br>'
                f'<b>Supported by.</b> {_escape(finding.supported_by)}</p>',
                unsafe_allow_html=True)
            if lede:
                st.markdown(f'<p class="lede">{lede}</p>',
                            unsafe_allow_html=True)
            chart(figure)
            if finding.measures:
                cards = "".join(
                    f'<div class="measure"><span class="k">'
                    f'{_escape(m.label)}</span><span class="v">'
                    f'{_escape(format_value(m.value, m.unit))}</span></div>'
                    for m in finding.measures)
                st.markdown(f'<div class="measures">{cards}</div>',
                            unsafe_allow_html=True)
            if table_note:
                st.markdown(f'<p class="foot">{table_note}</p>',
                            unsafe_allow_html=True)
            left, right = st.columns(2)
            with left:
                st.markdown(
                    f'<p class="foot"><b>The decision it drives.</b><br>'
                    f'{_escape(finding.decision)}</p>',
                    unsafe_allow_html=True)
            with right:
                st.markdown(
                    f'<p class="foot"><b>Why a developer should care.</b><br>'
                    f'{_escape(finding.for_developers)}</p>',
                    unsafe_allow_html=True)
            st.markdown(
                f'<p class="foot"><b>What would have to be true for this to '
                f'be wrong.</b> {_escape(finding.falsified_if)}</p>',
                unsafe_allow_html=True)

        by_id = {f.id: f for f in supported}

        if "dispersion" in by_id:
            claim_block(
                1, by_id["dispersion"],
                charts.dispersion_figure(by_id["dispersion"].table),
                "Each bar spans the bottom decile to the top decile of "
                "quarterly returns, with the median name marked inside it. A "
                "single spread number would hide the part that matters: "
                "whether the band sits above or below zero.")

        if "breadth" in by_id:
            claim_block(
                2, by_id["breadth"],
                charts.quarterly_figure(by_id["breadth"].table),
                "Median return per quarter, with the share of names advancing "
                "over it. Both are percentages, so they share one axis rather "
                "than being given a second scale to invent a relationship "
                "with. The two disagreeing is the claim.")

        if "volatility" in by_id:
            claim_block(
                3, by_id["volatility"],
                charts.volatility_figure(by_id["volatility"].table),
                "The median symbol's daily volatility, quarter by quarter. "
                "The claim is the level after the selloff, not the spike "
                "during it.")

        if supported and supported[0].table:
            st.markdown('<div class="sec">Every quarter, on the same '
                        'basis</div>', unsafe_allow_html=True)
            quarters = pd.DataFrame(supported[0].table)
            st.dataframe(quarters, use_container_width=True, hide_index=True)
            st.download_button(
                "Download the quarterly table as CSV",
                quarters.to_csv(index=False).encode("utf-8"),
                file_name="quarterly_market_summary.csv", mime="text/csv")

        st.markdown(
            '<p class="foot" style="border-top:1px solid var(--line);'
            'padding-top:12px;margin-top:24px">The same generators write '
            '<code>ETL_Analysis/claims.md</code>. Regenerate it with '
            '<code>python -m ETL_Analysis.claims</code>, or as part of a run '
            'with <code>python -m ETL_Analysis.pipeline --claims</code> - the '
            'document and this page are the same code, so they cannot '
            'disagree.</p>', unsafe_allow_html=True)

    # =====================================================================
    # Instrument
    # =====================================================================
    with instrument_tab:
        if not results:
            st.info("No rows match the current scope.")
        else:
            names = [r["summary"]["symbol"] for r in results]
            picker, toggle = st.columns([3, 2])
            with picker:
                picked = st.selectbox("Instrument", names, index=0)
            with toggle:
                by_quarter = st.toggle(
                    "Colour the price line by calendar quarter",
                    help="One trace per quarter, so a legend click isolates "
                         "Q1 to Q4.")
            result = next(r for r in results
                          if r["summary"]["symbol"] == picked)
            slot = names.index(picked)
            s = result["summary"]
            period_return = s.get("period_return_pct") or 0.0

            st.markdown(stat_strip([
                stat_tile("Period return",
                          format_value(s.get("period_return_pct"), "pct"),
                          date_span(s.get("date_from"), s.get("date_to")),
                          tone="good" if period_return >= 0 else "bad"),
                stat_tile("Last close",
                          format_value(s.get("close_last"), "price"),
                          f"opened the period at "
                          f"{format_value(s.get('close_first'), 'price')}"),
                stat_tile("Daily volatility",
                          format_value(s.get("volatility_pct"), "pct").lstrip("+"),
                          "std dev of daily returns"),
                # A drawdown is never positive, so a leading "+" on a flat
                # series reads as a gain that did not happen.
                stat_tile("Max drawdown",
                          format_value(s.get("max_drawdown_pct"),
                                       "pct").lstrip("+"),
                          "worst peak to trough"),
                stat_tile("Trading days", f"{s.get('trading_days', 0):,}",
                          f"{s.get('up_days', 0)} up / "
                          f"{s.get('down_days', 0)} down"),
                stat_tile("Total turnover", compact(s.get("total_turnover")),
                          result.get("currency") or ""),
            ]), unsafe_allow_html=True)

            direction = "rose" if period_return >= 0 else "fell"
            st.markdown(
                f'<div class="sec">{_escape(picked)} {direction} '
                f'{abs(period_return):.2f}% over the period</div>',
                unsafe_allow_html=True)
            chart(charts.price_figure(result, by_quarter=by_quarter,
                                      colour_index=slot))

            volume_col, spread_col = st.columns(2)
            with volume_col:
                st.markdown('<div class="sec">Shares traded each day</div>',
                            unsafe_allow_html=True)
                chart(charts.volume_figure(result, colour_index=slot),
                      "No rows to chart.")
            with spread_col:
                st.markdown('<div class="sec">How its daily returns are '
                            'spread</div>', unsafe_allow_html=True)
                chart(charts.return_histogram(result, colour_index=slot),
                      "At least two trading days are needed to show a "
                      "distribution.")

            st.markdown('<div class="sec">Measures</div>',
                        unsafe_allow_html=True)
            cards = "".join(
                f'<div class="measure"><span class="k">'
                f'{_escape(card["label"])}</span>'
                f'<span class="v">{_escape(card["value"])}</span></div>'
                for card in measure_cards(result))
            st.markdown(f'<div class="measures">{cards}</div>',
                        unsafe_allow_html=True)
            st.markdown(
                '<p class="foot">Computed over the rows in scope by '
                '<code>ETL_Analysis.transform</code>, not read back from '
                '<code>run_metric</code> &mdash; so they describe the '
                'filtered series on screen rather than the whole symbol as it '
                'was loaded.</p>', unsafe_allow_html=True)

            st.markdown('<div class="sec">The rows behind these charts</div>',
                        unsafe_allow_html=True)
            rows_table = pd.DataFrame(price_table_rows(result))
            st.dataframe(rows_table, use_container_width=True,
                         hide_index=True, height=320)
            st.download_button(
                "Download these rows as CSV",
                rows_table.to_csv(index=False).encode("utf-8"),
                file_name=f"{picked.replace('/', '-')}_daily_price.csv",
                mime="text/csv")

    # =====================================================================
    # Data quality
    # =====================================================================
    with quality_tab:
        st.markdown('<div class="sec">Reconciliation</div>',
                    unsafe_allow_html=True)
        if reconciled:
            st.markdown(
                '<p class="lede"><span class="pill ok">Balanced</span> &nbsp;'
                'Every ledger row satisfies <code>candles_in = rows_kept + '
                'rows_quarantined</code>. A row lost between arriving and '
                'landing would appear here, which is the failure this design '
                'exists to make visible.</p>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<p class="lede"><span class="pill bad">Failed</span> &nbsp;'
                'These ledger rows do not add up:</p>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(overview["reconciliation"]),
                         use_container_width=True, hide_index=True)

        st.markdown('<div class="sec">Why rows were rejected</div>',
                    unsafe_allow_html=True)
        reasons = read_reasons(path, stamp, selection)
        reason_fig = charts.reason_figure(reasons)
        if reason_fig:
            chart(reason_fig)
            st.dataframe(pd.DataFrame(reasons), use_container_width=True,
                         hide_index=True)
        else:
            st.markdown(
                '<p class="lede">Nothing in scope was quarantined. The '
                'malformed fixture is the way to see this populated: '
                '<code>python -m ETL_Analysis.pipeline --symbols '
                'TATASTEEL.BO</code></p>', unsafe_allow_html=True)

        st.markdown('<div class="sec">Why every claim excludes '
                    'vendor-interpolated rows</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="lede">The same company, the same trading day, priced on '
            'both venues - split by whether the vendor interpolated the BSE '
            'candle. An interpolated close sits a median 3.8% from the NSE '
            'print; when both venues actually traded, 0.03%. That is roughly '
            'two orders of magnitude, which is why no claim on the Claims tab '
            'is argued from an interpolated row. Note the log scale: on a '
            'linear axis the observed-day bar would be invisible.</p>',
            unsafe_allow_html=True)
        quality_evidence = read_claims(path, stamp)
        chart(charts.venue_gap_figure(quality_evidence["venue_gap"]),
              "No dual-listed pairs in the store to compare.")
        if quality_evidence["venue_gap"]:
            st.dataframe(pd.DataFrame(quality_evidence["venue_gap"]),
                         use_container_width=True, hide_index=True)
        if quality_evidence["dual_listed"]:
            st.markdown(
                '<p class="lede">What that costs over a year, per company. '
                'UltraTech is the extreme; NTPC is the one where the two '
                'venues disagree about the sign.</p>', unsafe_allow_html=True)
            venue = pd.DataFrame(quality_evidence["dual_listed"])
            st.dataframe(
                venue, use_container_width=True, hide_index=True,
                column_config={
                    "nse_return_pct": st.column_config.NumberColumn(
                        "NSE return %", format="%+.2f"),
                    "bse_return_pct": st.column_config.NumberColumn(
                        "BSE return %", format="%+.2f"),
                    "disagreement_pts": st.column_config.NumberColumn(
                        "Disagreement (pts)", format="%.2f"),
                })
            st.download_button(
                "Download the venue comparison as CSV",
                venue.to_csv(index=False).encode("utf-8"),
                file_name="dual_listed_venue_comparison.csv", mime="text/csv")

        st.markdown('<div class="sec">Interpolation rate by quarter and '
                    'venue</div>', unsafe_allow_html=True)
        chart(charts.interpolation_figure(quality_evidence["interpolation"]))

        st.markdown('<div class="sec">Quarantined rows, in full</div>',
                    unsafe_allow_html=True)
        quarantined = quarantine_table_rows(results)
        if quarantined:
            st.markdown(
                '<p class="lede">Quarantine means recoverable, not discarded: '
                'the candle exactly as it arrived is kept alongside the reason '
                'it was refused.</p>', unsafe_allow_html=True)
            frame = pd.DataFrame(quarantined)
            st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button(
                "Download quarantined rows as CSV",
                frame.to_csv(index=False).encode("utf-8"),
                file_name="quarantined_candles.csv", mime="text/csv")
        else:
            st.markdown('<p class="foot">None in scope.</p>',
                        unsafe_allow_html=True)

        st.markdown('<div class="sec">Repaired and loaded</div>',
                    unsafe_allow_html=True)
        repairs = repair_table_rows(results)
        if repairs:
            st.markdown(
                '<p class="lede">These rows are loaded but flagged, and drawn '
                'as open diamonds on the price chart. Nothing is fixed '
                'silently: each repair names what changed and why. Tick '
                '<em>Exclude repaired rows</em> in the rail to see every '
                'chart without them.</p>', unsafe_allow_html=True)
            frame = pd.DataFrame(repairs)
            st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button(
                "Download repairs as CSV",
                frame.to_csv(index=False).encode("utf-8"),
                file_name="repairs.csv", mime="text/csv")
        else:
            st.markdown('<p class="foot">Nothing in scope was repaired.</p>',
                        unsafe_allow_html=True)

    # =====================================================================
    # Runs
    # =====================================================================
    with runs_tab:
        st.markdown('<div class="sec">Every load, newest first</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="lede"><code>load_run</code> is append-only: it is the '
            'history of loads rather than the current state, so a re-pull adds '
            'a row instead of overwriting one.</p>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(overview["runs"]), use_container_width=True,
                     hide_index=True, height=270)

        run_ids = [row["run_id"] for row in overview["runs"]]
        picked_run = st.selectbox("Inspect one run", run_ids, index=0)
        st.dataframe(pd.DataFrame(read_ledger(path, stamp, picked_run)),
                     use_container_width=True, hide_index=True, height=260)

        st.markdown('<div class="sec">One measure, across runs</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="lede">This is what long-format <code>run_metric</code> '
            'buys: comparing a measure across runs is a single '
            '<code>WHERE</code>, not a column-by-column diff.</p>',
            unsafe_allow_html=True)
        metric_options = overview["metrics"]
        if metric_options:
            labels = dict(metric_options)
            chosen = st.selectbox(
                "Measure", [key for key, _ in metric_options],
                format_func=lambda key: labels.get(key, key))
            tracked = st.multiselect(
                "Symbols", list(selection),
                default=list(selection)[:charts.MAX_COMPARISON_SERIES])
            history = read_metric_history(path, stamp, chosen, tuple(tracked))
            figure = charts.metric_history_figure(
                history, labels.get(chosen, chosen))
            if figure:
                chart(figure)
                st.dataframe(pd.DataFrame(history), use_container_width=True,
                             hide_index=True, height=240)
            else:
                st.info("No stored values for that measure and those symbols.")
        else:
            st.info("No metrics stored yet.")

    # =====================================================================
    # SQL console
    # =====================================================================
    with console_tab:
        editor, panel = st.columns([3, 1])

        with panel:
            st.markdown('<div class="sec">Tables</div>', unsafe_allow_html=True)
            for table_name, columns in overview["schema"].items():
                with st.expander(f"{table_name}  ({len(columns)})"):
                    body = "<br>".join(
                        f"<b>{_escape(name)}</b> "
                        f"<span class='t'>{_escape(kind)}</span>"
                        for name, kind in columns)
                    st.markdown(f'<div class="schema">{body}</div>',
                                unsafe_allow_html=True)

        with editor:
            st.markdown('<div class="sec">Query the store</div>',
                        unsafe_allow_html=True)
            st.markdown(
                f'<p class="lede">The store is opened read-only, so nothing '
                f'here can change what the pipeline loaded. One statement at '
                f'a time; results are capped at '
                f'{store.MAX_CONSOLE_ROWS:,} rows.</p>',
                unsafe_allow_html=True)

            if "sql" not in st.session_state:
                st.session_state["sql"] = EXAMPLE_QUERIES[0][1]

            example = st.selectbox("Start from an example",
                                   [title for title, _ in EXAMPLE_QUERIES])
            if st.button("Load this example"):
                st.session_state["sql"] = dict(EXAMPLE_QUERIES)[example]

            sql = st.text_area("SQL", key="sql", height=220,
                               label_visibility="collapsed")

            if st.button("Run query", type="primary"):
                try:
                    with store.connect(path) as handle:
                        outcome = store.run_console_query(handle, sql)
                except (store.UnsafeQuery, store.StoreUnavailable) as exc:
                    st.error(str(exc))
                except Exception as exc:  # noqa: BLE001 - any DuckDB error
                    st.error(f"DuckDB refused that query:\n\n{exc}")
                else:
                    frame = pd.DataFrame(outcome["rows"],
                                         columns=outcome["columns"])
                    note = (f'{len(frame):,} row(s) in '
                            f'{outcome["elapsed_ms"]:.0f} ms')
                    if outcome["truncated"]:
                        note += (f' &middot; truncated at '
                                 f'{store.MAX_CONSOLE_ROWS:,} rows')
                    st.markdown(f'<p class="foot">{note}</p>',
                                unsafe_allow_html=True)
                    st.dataframe(frame, use_container_width=True,
                                 hide_index=True, height=420)
                    if not frame.empty:
                        st.download_button(
                            "Download these results as CSV",
                            frame.to_csv(index=False).encode("utf-8"),
                            file_name="query_results.csv", mime="text/csv")

    st.markdown(
        '<p class="foot" style="border-top:1px solid var(--line);'
        'padding-top:14px;margin-top:36px">Educational data from the Fauxnance '
        'API. Prices are invented and delayed; not for investment use. Every '
        'measure is computed by <code>ETL_Analysis.transform</code> over the '
        'rows in scope, and every chart has the table it was drawn from beside '
        'it.</p>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

#: Set on the child so a misdetection can never spawn a second one. Without
#: it, a `under_streamlit()` that answered False inside streamlit would fork
#: an unbounded chain of servers, each waiting on the next.
CHILD_ENV_VAR = "ETL_ANALYSIS_DASHBOARD_CHILD"


def under_streamlit() -> bool:
    """Whether this process is already running the app.

    Asked two ways because they fail in different situations. A served app has
    a streamlit Runtime; a test harness driving the script directly does not,
    but every script run has a script-run context either way. Answering False
    inside streamlit would make `main` shell out to a second streamlit, so the
    check errs towards True.
    """
    try:
        from streamlit.runtime import exists
        if exists():
            return True
    except Exception:  # noqa: BLE001 - an old streamlit, or none at all
        pass

    for module_path in (
        "streamlit.runtime.scriptrunner",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
    ):
        try:
            module = __import__(module_path, fromlist=["get_script_run_ctx"])
            if module.get_script_run_ctx(suppress_warning=True) is not None:
                return True
        except Exception:  # noqa: BLE001 - the path moved between versions
            continue
    return False


def launch_command(db_path: str = DEFAULT_DB_PATH, port: int | None = None,
                   headless: bool = False) -> list[str]:
    """The `streamlit run` command line this module launches.

    The theme is passed as flags rather than left to a config file, so the
    dashboard looks the same whatever directory it is started from and
    whatever the reader's own streamlit settings say.
    """
    command = [
        sys.executable, "-m", "streamlit", "run",
        str(Path(__file__).resolve()),
        "--theme.base", "light",
        "--theme.backgroundColor", charts.PAGE,
        "--theme.secondaryBackgroundColor", charts.SURFACE,
        "--theme.textColor", charts.INK,
        "--theme.primaryColor", charts.SERIES_COLOURS[0],
        "--browser.gatherUsageStats", "false",
    ]
    if port:
        command += ["--server.port", str(port)]
    if headless:
        command += ["--server.headless", "true"]
    return command + ["--", "--db", str(db_path)]


def launch(db_path: str = DEFAULT_DB_PATH, port: int | None = None,
           headless: bool = False) -> int:
    """Start the dashboard in a child process. Returns its exit code."""
    if os.environ.get(CHILD_ENV_VAR):
        print("Already inside a dashboard process; refusing to start another. "
              "Open the URL streamlit printed instead.", file=sys.stderr)
        return 1
    environment = dict(os.environ, **{CHILD_ENV_VAR: "1"})
    return subprocess.call(launch_command(db_path, port, headless),
                           env=environment)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Live dashboard over the DuckDB analytical store")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help="DuckDB file to read (default: %(default)s)")
    parser.add_argument("--port", type=int, default=None,
                        help="port to serve on")
    parser.add_argument("--headless", action="store_true",
                        help="do not open a browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Render the page if we are inside streamlit, otherwise start streamlit."""
    args = parse_args(argv)
    if under_streamlit():
        run_app(args.db)
        return 0
    return launch(args.db, port=args.port, headless=args.headless)


if __name__ == "__main__":
    # Under `streamlit run` this file IS the page, and the run has to end by
    # returning. `sys.exit` raises SystemExit up through streamlit's script
    # runner, which then never completes the run -- the page renders nothing
    # and the request hangs. An exit code is only meaningful on the CLI path,
    # where this process is a launcher rather than the app.
    _code = main()
    if not under_streamlit():
        sys.exit(_code)
