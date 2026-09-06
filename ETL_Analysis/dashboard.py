from __future__ import annotations

import argparse
import html as html_module
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ETL_Analysis import charts, claims as claims_module, store
from ETL_Analysis import report as report_module
from ETL_Analysis import transform as transform_module

APP_TITLE = "Market data pipeline"
DEFAULT_DB_PATH = store.DEFAULT_DB_PATH

MAX_DISPOSITION_BARS = 40
MAX_NAMED_FAILURES = 5

SLICE_CACHE_ENTRIES = 4
LIGHT_CACHE_ENTRIES = 32
CACHE_TTL_SECONDS = 300

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

def format_value(value, unit: str) -> str:
    return report_module.format_value(value, unit)

def compact(value, unit: str = "") -> str:
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
    if not lo or not hi:
        return "-"
    if lo.year == hi.year:
        return f"{lo:%d %b} - {hi:%d %b %Y}"
    return f"{lo:%d %b %Y} - {hi:%d %b %Y}"

def totals_for(results: list[dict]) -> dict:
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
    return [{
        "Symbol": row["symbol"],
        "Date": row["date"],
        "Repair": entry.get("code"),
        "What changed": entry.get("detail"),
    } for result in results for row in result["rows"] if row["repaired"]
        for entry in row["repairs"]]

def quarantine_table_rows(results: list[dict]) -> list[dict]:
    return [{
        "Symbol": bad["symbol"],
        "Date as received": (bad["candle"].get("date")
                             if isinstance(bad["candle"], dict) else None),
        "Reason": bad["reason"],
        "Detail": bad["detail"],
    } for result in results for bad in result["quarantined"]]

def measure_cards(result: dict) -> list[dict]:
    return [{"metric": m["metric"],
             "label": m["label"],
             "value": format_value(m["value"], m["unit"])}
            for m in transform_module.metrics(result)
            if m["unit"] != "rows"]

def plotly_available() -> bool:
    try:
        import plotly.tools
        return True
    except Exception:
        return False

PLOTLY_MISSING_NOTE = (
    "Charts need plotly, which is not installed: `pip install plotly`. "
    "Every table on this page carries the same numbers in the meantime."
)

def summarise_run(requested: list, failures: list, loaded: int,
                  interval: str | None, rows: int | None = None) -> str:
    asked = f" at {interval}" if interval else ""
    total = len(requested)
    counted = f"{loaded} of {total} symbol(s)" if failures else \
        f"{loaded} symbol(s)"
    rowsay = f", {rows} row(s)" if rows else ""
    message = f"Loaded {counted}{asked}{rowsay}."

    if failures:
        names = ", ".join(symbol for symbol, _ in failures[:MAX_NAMED_FAILURES])
        more = len(failures) - MAX_NAMED_FAILURES
        if more > 0:
            names += f" and {more} more"
        reason = failures[0][1] if failures else ""
        message += f" {len(failures)} failed: {names}."
        if reason:
            message += f" First error: {reason}"
    else:
        message += " The page is showing the new data."
    return message


def run_pipeline_from_app(db_path: str, symbols: list, interval: str | None,
                          live: bool = False, progress=None) -> dict:
    from ETL_Analysis import pipeline as pipeline_module

    symbols = [s.strip() for s in symbols if s.strip()]
    if not symbols:
        return {"ok": False, "message": "Name at least one symbol to pull."}

    extract_fn = None
    if live:
        try:
            from ETL_Analysis.extract_live import extract as extract_fn
        except ImportError as exc:
            return {"ok": False,
                    "message": f"The live client is unavailable: {exc}"}

    outcome = {"failures": [], "loaded": 0, "rows": 0}

    def collect(event):
        if event.get("stage") == "finished":
            outcome["failures"] = list(event.get("failures") or [])
            outcome["loaded"] = event.get("extracted", 0)
            outcome["rows"] = event.get("rows_loaded", 0)
        if progress is not None:
            progress(event)

    try:
        code = pipeline_module.run(symbols, extract_fn=extract_fn,
                                   db_path=db_path, interval=interval,
                                   progress=collect)
    except Exception as exc:
        return {"ok": False, "message": f"The run failed: {exc}"}

    failures = outcome["failures"]

    if code != 0:
        if failures:
            names = ", ".join(s for s, _ in failures[:MAX_NAMED_FAILURES])
            more = len(failures) - MAX_NAMED_FAILURES
            if more > 0:
                names += f" and {more} more"
            return {"ok": False, "failures": failures,
                    "message": (f"Nothing loaded. All {len(failures)} symbol(s) "
                                f"failed: {names}. "
                                f"First error: {failures[0][1]}")}
        return {"ok": False, "failures": failures,
                "message": ("The run finished with errors and may have loaded "
                            "nothing. Check the terminal for the log.")}

    return {"ok": not failures,
            "failures": failures,
            "loaded": outcome["loaded"],
            "message": summarise_run(symbols, failures, outcome["loaded"],
                                     interval, outcome["rows"])}

def default_run_symbols() -> list:
    from ETL_Analysis import pipeline as pipeline_module
    return list(pipeline_module.DEFAULT_SYMBOLS)

def _escape(text) -> str:
    return html_module.escape(str(text), quote=True)

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

  .masthead { border-bottom: 1px solid var(--line); padding-bottom: 13px; }
  .masthead h1 { font-size: 21px; font-weight: 620; letter-spacing: -0.012em;
                 margin: 0 0 6px; }
  .meta { font-size: 12.5px; color: var(--ink-2); }
  .meta code, .lede code, .foot code { background: #f0efec; border: 1px solid var(--line);
      padding: 1px 6px; border-radius: 3px; font-size: 11.5px; font-family: var(--mono); }
  .sep { color: #c3c2b7; padding: 0 9px; }

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

  .sec { font-size: 10.5px; font-weight: 650; letter-spacing: .1em;
         text-transform: uppercase; color: var(--muted);
         border-bottom: 1px solid var(--line); padding-bottom: 6px;
         margin: 28px 0 2px; }
  .lede { font-size: 13px; color: var(--ink-2); margin: 10px 0 2px;
          max-width: 80ch; line-height: 1.55; }
  .foot { font-size: 11.5px; color: var(--muted); margin: 6px 0 0;
          max-width: 92ch; line-height: 1.5; }

  .measures { display: grid; gap: 1px; background: var(--line);
              border: 1px solid var(--line); border-radius: 5px; overflow: hidden;
              grid-template-columns: repeat(auto-fill, minmax(172px, 1fr)); }
  .measure { background: var(--surface); padding: 10px 13px; }
  .measure .k { font-size: 10.5px; color: var(--muted); display: block;
                margin-bottom: 3px; line-height: 1.35; }
  .measure .v { font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }

  .pill { display: inline-block; padding: 2px 9px; border-radius: 3px;
          font-size: 11px; font-weight: 600; }
  .pill.ok { background: #e6f5e6; color: #0a6b0a; border: 1px solid #c6e8c6; }
  .pill.bad { background: #fbe9e9; color: #9c1f1f; border: 1px solid #f2cccc; }

  .stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--line); }
  .stTabs [data-baseweb="tab"] { height: 40px; padding: 0 16px; font-size: 13.5px;
      font-weight: 550; color: var(--ink-2); background: transparent; }
  .stTabs [aria-selected="true"] { color: var(--ink); box-shadow: inset 0 -2px 0 var(--ink); }

  section[data-testid="stSidebar"] { background: var(--surface);
      border-right: 1px solid var(--line); }
  .railhead { font-size: 10.5px; font-weight: 650; letter-spacing: .1em;
              text-transform: uppercase; color: var(--muted);
              border-bottom: 1px solid var(--line); padding-bottom: 6px;
              margin: 18px 0 10px; }

  [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 5px; }
  .schema { font-family: var(--mono); font-size: 11.5px; line-height: 1.7;
            color: var(--ink-2); }
  .schema b { color: var(--ink); font-weight: 600; }
  .schema .t { color: var(--muted); }
</style>
"""

def stat_tile(key: str, value: str, sub: str = "", tone: str = "",
              small: bool = False) -> str:
    classes = " ".join(filter(None, ["v", "sm" if small else "", tone]))
    sub_html = f'<div class="sub">{_escape(sub)}</div>' if sub else ""
    return (f'<div class="stat"><span class="k">{_escape(key)}</span>'
            f'<div class="{classes}">{_escape(value)}</div>{sub_html}</div>')

def stat_strip(tiles: list[str]) -> str:
    return f'<div class="stats">{"".join(tiles)}</div>'

def masthead(path: str, run_id: str | None, loaded_at, note: str = "") -> str:
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

def run_app(db_path: str = DEFAULT_DB_PATH) -> None:
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    can_chart = plotly_available()

    def chart(figure, empty: str = "Nothing to chart in the current scope."):
        if figure is None:
            st.info(empty)
        elif not can_chart:
            st.warning(PLOTLY_MISSING_NOTE)
        else:
            st.plotly_chart(figure, use_container_width=True,
                            config=charts.PLOTLY_CONFIG)

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
        for reader in readers:
            reader.clear()

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
            wanted = run_symbols.split()
            with st.status(f"Running {len(wanted)} symbol(s)",
                           expanded=True) as status:
                bar = st.progress(0.0)
                line = st.empty()
                done = {"ok": 0, "failed": 0}

                def show(event):
                    stage = event.get("stage")
                    total = max(1, event.get("total", len(wanted)))
                    if stage == "extract":
                        symbol = event.get("symbol", "")
                        index = event.get("index", 0)
                        state = event.get("state")
                        if state == "start":
                            line.markdown(
                                f"**{index}/{total}** &middot; pulling "
                                f"`{_escape(symbol)}`")
                            return
                        if state == "failed":
                            done["failed"] += 1
                            line.markdown(
                                f"**{index}/{total}** &middot; "
                                f"`{_escape(symbol)}` failed &mdash; "
                                f"{_escape(event.get('error', ''))}")
                        else:
                            done["ok"] += 1
                            line.markdown(
                                f"**{index}/{total}** &middot; "
                                f"`{_escape(symbol)}` ok")
                        bar.progress(min(1.0, index / total))
                    elif stage == "transform":
                        line.markdown(
                            f"cleaning {event.get('count', 0)} payload(s)")
                    elif stage == "load":
                        line.markdown(
                            f"writing {event.get('count', 0)} result(s) "
                            f"to the store")
                    elif stage == "finished":
                        bar.progress(1.0)
                        line.markdown(
                            f"{done['ok']} pulled &middot; "
                            f"{done['failed']} failed")

                outcome = run_pipeline_from_app(
                    path, wanted, requested_interval.strip() or None,
                    live=go_live, progress=show)
                status.update(
                    label=("Run finished" if outcome["ok"]
                           else "Run finished with problems"),
                    state="complete" if outcome["ok"] else "error",
                    expanded=False)

            refresh()
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
                except Exception as exc:
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

CHILD_ENV_VAR = "ETL_ANALYSIS_DASHBOARD_CHILD"

def under_streamlit() -> bool:
    try:
        from streamlit.runtime import exists
        if exists():
            return True
    except Exception:
        pass

    for module_path in (
        "streamlit.runtime.scriptrunner",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
    ):
        try:
            module = __import__(module_path, fromlist=["get_script_run_ctx"])
            if module.get_script_run_ctx(suppress_warning=True) is not None:
                return True
        except Exception:
            continue
    return False

def launch_command(db_path: str = DEFAULT_DB_PATH, port: int | None = None,
                   headless: bool = False) -> list[str]:
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
    args = parse_args(argv)
    if under_streamlit():
        run_app(args.db)
        return 0
    return launch(args.db, port=args.port, headless=args.headless)

if __name__ == "__main__":
    _code = main()
    if not under_streamlit():
        sys.exit(_code)
