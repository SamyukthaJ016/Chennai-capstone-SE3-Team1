"""Report: one self-contained HTML file per run, charted with Plotly.

Writes `report.html`. Not part of the ETL core -- extract, transform and load
are the pipeline; this renders what the pipeline produced.

PLOTLY IS REQUIRED
    `pip install plotly`. There is no fallback renderer: a report that silently
    degrades to something else is a report you cannot trust to look the same
    twice. If plotly is missing, `build_report` raises and says so.

    (`report_svg.py` still holds the dependency-free renderer, if you ever need
    a report on a machine without plotly. It is not wired to the pipeline.)

OFFLINE BY DEFAULT
    The sprint requires chart artefacts that open with no network. Plotly's
    JavaScript is therefore INLINED into the document -- `include_plotlyjs=True`
    on the first figure only, so the ~3MB bundle appears once rather than once
    per chart. Pass `inline_js=False` to use the CDN instead: much smaller
    files, but they need a network to render, which fails the sprint's bar.

STRUCTURE
    Every chart is built as a plain figure dict -- `{"data": [...],
    "layout": {...}} -- by a pure function with no plotly import. Those are
    fully unit-tested: trace counts, x/y values, date alignment, axis titles.
    Plotly is only touched in `_render`, which turns a figure dict into an
    HTML fragment. So if a chart shows the wrong numbers, the bug is in a
    tested pure function, not in the rendering.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from pathlib import Path

DEFAULT_REPORT_PATH = "report.html"

# A line chart stops being readable somewhere around six series, and a report
# with a section per symbol stops being readable long before a few hundred.
# Above these, the report leads with a ranked table and charts only the
# extremes -- which is what a reader wants from a wide pull anyway.
MAX_COMPARISON_SERIES = 6
MAX_DETAIL_SECTIONS = 12

# Colour-blind-safe qualitative palette (Okabe-Ito). Distinguishable under the
# most common forms of colour vision deficiency, which a default red/green
# palette is not.
SERIES_COLOURS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00",
                  "#56B4E9"]
COLOUR_GOOD = "#009E73"
COLOUR_REPAIRED = "#E69F00"
COLOUR_BAD = "#D55E00"

# Shared layout. Kept in one place so every chart in the report looks alike.
BASE_LAYOUT = {
    "template": "plotly_white",
    "font": {"family": "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, "
                       "Helvetica, Arial, sans-serif", "size": 13,
             "color": "#1a1f26"},
    "margin": {"l": 70, "r": 24, "t": 64, "b": 60},
    "hovermode": "x unified",
    "plot_bgcolor": "#ffffff",
    "paper_bgcolor": "#ffffff",
}

PLOTLY_CONFIG = {"displaylogo": False, "responsive": True}

# Calendar quarters, independent of year -- a report typically covers a
# single year or less, so "Q1" unambiguously means Jan-Mar within it.
QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


class PlotlyMissing(ImportError):
    """plotly is not installed. The report cannot be rendered without it."""


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_value(value: float, unit: str) -> str:
    """Render a metric for display, according to its unit."""
    if value is None:
        return "-"
    if unit == "pct":
        return f"{value:+,.2f}%"
    if unit == "price":
        return f"{value:,.2f}"
    if unit in ("shares", "rows", "days"):
        return f"{value:,.0f}"
    if unit == "currency":
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.2f}bn"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.2f}m"
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _e(text) -> str:
    """Escape for an HTML text node."""
    return html.escape(str(text), quote=True)


def _axis(title: str, **extra) -> dict:
    """An axis with its title always set.

    A required argument rather than an optional one: the sprint is explicit
    that a non-technical reader must be able to read a chart unaided, and an
    unlabelled axis is the usual way that fails.
    """
    axis = {"title": {"text": title}, "gridcolor": "#e6e9ee",
            "linecolor": "#5b6470", "zeroline": False}
    axis.update(extra)
    return axis


# ---------------------------------------------------------------------------
# Quarterly segmentation, shared by the per-symbol time series figures.
# ---------------------------------------------------------------------------

def _quarter_of(day: date) -> int:
    """Calendar quarter (1-4) a date falls in."""
    return (day.month - 1) // 3 + 1


def _split_by_quarter(rows: list[dict]) -> list[list[dict]]:
    """Rows grouped into Q1..Q4 buckets, each kept in date order.

    Always returns four buckets, even when a quarter has no rows, so the
    trace built from bucket `i` always lands at index `i` -- which is what
    lets `_quarter_updatemenu` address traces by a fixed position rather
    than a value that would shift with the data.
    """
    buckets: list[list[dict]] = [[], [], [], []]
    for row in rows:
        buckets[_quarter_of(row["date"]) - 1].append(row)
    return buckets


def _quarter_updatemenu() -> dict:
    """Buttons that isolate one quarter's trace, or show all four.

    Client-side only (plotly's `restyle` runs in the browser), so this works
    in the offline, no-backend HTML file the report already is. Assumes the
    figure's traces are exactly [Q1, Q2, Q3, Q4] in that order.
    """
    buttons = [{
        "label": "All quarters", "method": "restyle",
        "args": [{"visible": [True, True, True, True]}],
    }]
    for index, label in enumerate(QUARTER_LABELS):
        visible = [i == index for i in range(4)]
        buttons.append({"label": label, "method": "restyle",
                        "args": [{"visible": visible}]})
    return {
        "type": "buttons", "direction": "left", "buttons": buttons,
        "x": 0, "xanchor": "left", "y": 1.24, "yanchor": "top",
        "showactive": True, "pad": {"r": 6, "t": 4},
    }


# ---------------------------------------------------------------------------
# Figure builders. Pure: dicts in, dicts out, no plotly import, fully tested.
# ---------------------------------------------------------------------------

def comparison_figure(results: list[dict]) -> tuple[dict | None, bool]:
    """Every symbol rebased to 100, so instruments at different price levels
    are comparable on one axis.

    Returns (figure, trimmed). `trimmed` is True when only the biggest movers
    are charted, so the caller can say so rather than letting a reader think
    six symbols was all there was.

    Series carry their own x values -- real dates -- rather than sharing an
    index. Positioning by index would draw one symbol's fourth point on
    another symbol's fourth date, silently claiming a price moved on a day it
    did not.
    """
    charted = [r for r in results if len(r["rows"]) >= 2]
    if not charted:
        return None, False

    trimmed = len(charted) > MAX_COMPARISON_SERIES
    if trimmed:
        charted = sorted(
            charted,
            key=lambda r: abs(r["summary"]["period_return_pct"]),
            reverse=True,
        )[:MAX_COMPARISON_SERIES]

    traces = []
    for index, result in enumerate(charted):
        rows = result["rows"]
        base = rows[0]["close"]
        traces.append({
            "type": "scatter",
            "mode": "lines+markers",
            "name": result["summary"]["symbol"],
            "x": [r["date"].isoformat() for r in rows],
            "y": [round(r["close"] / base * 100, 4) for r in rows],
            "line": {"color": SERIES_COLOURS[index % len(SERIES_COLOURS)],
                     "width": 2.5},
            "marker": {"size": 6},
            "hovertemplate": "%{y:.2f} (index) on %{x|%d %b %Y}<extra>"
                             f"{result['summary']['symbol']}</extra>",
        })

    layout = dict(BASE_LAYOUT)
    layout.update({
        "title": {"text": "Each instrument's price movement over the period, "
                          "rebased so they can be compared"},
        "xaxis": _axis("Trading day", type="date"),
        "yaxis": _axis("Price, indexed to 100 at each instrument's first day"),
        "legend": {"orientation": "h", "y": -0.22},
        "height": 420,
    })
    return {"data": traces, "layout": layout}, trimmed


def quality_figure(results: list[dict]) -> dict | None:
    """Stacked bars: how each symbol's candles were dispositioned.

    The visual form of the reconciliation invariant -- every candle received is
    either loaded or quarantined, and the bar lengths add up to what arrived.
    """
    if not results:
        return None

    symbols = [r["summary"]["symbol"] for r in results]
    clean, repaired, quarantined = [], [], []
    for result in results:
        s = result["summary"]
        clean.append(s["rows_kept"] - s.get("rows_repaired", 0))
        repaired.append(s.get("rows_repaired", 0))
        quarantined.append(s["rows_quarantined"])

    traces = [
        {"type": "bar", "orientation": "h", "name": "Loaded clean",
         "y": symbols, "x": clean, "marker": {"color": COLOUR_GOOD},
         "hovertemplate": "%{x} loaded clean<extra>%{y}</extra>"},
        {"type": "bar", "orientation": "h", "name": "Loaded after repair",
         "y": symbols, "x": repaired, "marker": {"color": COLOUR_REPAIRED},
         "hovertemplate": "%{x} repaired<extra>%{y}</extra>"},
        {"type": "bar", "orientation": "h", "name": "Quarantined",
         "y": symbols, "x": quarantined, "marker": {"color": COLOUR_BAD},
         "hovertemplate": "%{x} quarantined<extra>%{y}</extra>"},
    ]

    layout = dict(BASE_LAYOUT)
    layout.update({
        "title": {"text": "Every candle received is either loaded or "
                          "quarantined"},
        "barmode": "stack",
        "xaxis": _axis("Candles received from the API"),
        "yaxis": _axis("Symbol", automargin=True),
        "legend": {"orientation": "h", "y": -0.2},
        "height": max(240, 60 + 34 * len(symbols)),
        "hovermode": "closest",
    })
    return {"data": traces, "layout": layout}


def close_figure(result: dict) -> dict | None:
    """One symbol's closing price, with a title that states the finding.

    Split into one trace per calendar quarter (always Q1..Q4, in that
    order) so the buttons above the chart can isolate a single quarter or
    show all of them -- see `_quarter_updatemenu`.
    """
    rows = result["rows"]
    if not rows:
        return None
    s = result["summary"]
    symbol = s["symbol"]
    direction = "rose" if s["period_return_pct"] >= 0 else "fell"
    currency = s.get("currency") or result.get("currency") or "currency"

    traces = []
    for index, quarter_rows in enumerate(_split_by_quarter(rows)):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        traces.append({
            "type": "scatter",
            "mode": "lines+markers",
            "name": QUARTER_LABELS[index],
            "x": [r["date"].isoformat() for r in quarter_rows],
            "y": [r["close"] for r in quarter_rows],
            "line": {"color": colour, "width": 2.5},
            "marker": {
                # Repaired rows are drawn as open diamonds so a reader can
                # see at a glance which points were corrected rather than
                # observed.
                "size": [9 if r["repaired"] else 6 for r in quarter_rows],
                "symbol": ["diamond-open" if r["repaired"] else "circle"
                           for r in quarter_rows],
                "color": [COLOUR_REPAIRED if r["repaired"] else colour
                          for r in quarter_rows],
            },
            "hovertemplate": f"%{{y:,.2f}} {currency} on %{{x|%d %b %Y}}"
                             f"<extra>{symbol} {QUARTER_LABELS[index]}</extra>",
        })

    layout = dict(BASE_LAYOUT)
    layout.update({
        "title": {"text": f"{symbol} {direction} "
                          f"{abs(s['period_return_pct']):.2f}% between "
                          f"{s['date_from']:%d %b} and {s['date_to']:%d %b %Y}"},
        "xaxis": _axis("Trading day", type="date"),
        "yaxis": _axis(f"Closing price ({currency})"),
        "showlegend": True,
        "legend": {"orientation": "h", "y": -0.22},
        "updatemenus": [_quarter_updatemenu()],
        "margin": {**BASE_LAYOUT["margin"], "t": 92},
        "height": 380,
    })
    return {"data": traces, "layout": layout}


def volume_figure(result: dict) -> dict | None:
    """One symbol's daily traded volume.

    A day with no reported volume is passed to plotly as null, which leaves a
    gap rather than drawing a zero bar. A missing figure is not a day without
    trading, and a zero bar would say it was.

    Split into one trace per calendar quarter, same as `close_figure`, so
    the same quarter buttons isolate a single quarter here too.
    """
    rows = result["rows"]
    if not rows:
        return None
    symbol = result["summary"]["symbol"]

    traces = []
    for index, quarter_rows in enumerate(_split_by_quarter(rows)):
        traces.append({
            "type": "bar",
            "name": QUARTER_LABELS[index],
            "x": [r["date"].isoformat() for r in quarter_rows],
            "y": [r["volume"] for r in quarter_rows],
            "marker": {"color": SERIES_COLOURS[index % len(SERIES_COLOURS)]},
            "hovertemplate": "%{y:,.0f} shares on %{x|%d %b %Y}"
                             f"<extra>{symbol} {QUARTER_LABELS[index]}</extra>",
        })

    layout = dict(BASE_LAYOUT)
    layout.update({
        "title": {"text": f"Shares traded each day in {symbol}"},
        "xaxis": _axis("Trading day", type="date"),
        "yaxis": _axis("Shares traded", rangemode="tozero"),
        "showlegend": True,
        "legend": {"orientation": "h", "y": -0.22},
        "updatemenus": [_quarter_updatemenu()],
        "margin": {**BASE_LAYOUT["margin"], "t": 92},
        "height": 340,
    })

    missing = [r["date"] for r in rows if r["volume"] is None]
    if missing:
        layout["annotations"] = [{
            "text": f"{len(missing)} day(s) with no volume reported are left "
                    f"blank, not drawn as zero",
            "showarrow": False, "xref": "paper", "yref": "paper",
            "x": 0, "y": 1.12, "xanchor": "left",
            "font": {"size": 11, "color": "#5b6470"},
        }]
    return {"data": traces, "layout": layout}


# ---------------------------------------------------------------------------
# The plotly boundary. Everything above is pure; this is the only part that
# needs plotly installed.
# ---------------------------------------------------------------------------

def _plotly_io():
    try:
        import plotly.io as pio
    except ImportError as exc:
        raise PlotlyMissing(
            "plotly is required to render the report. Install it with:\n"
            "    pip install plotly"
        ) from exc
    return pio


def _render(figure: dict, include_js: bool, inline_js: bool = True) -> str:
    """Turn a figure dict into an HTML fragment.

    `include_js` must be True for exactly ONE figure in the document -- the
    plotly bundle is ~3MB and repeating it per chart would make the file
    unusable. Every later figure passes False and reuses the loaded library.
    """
    pio = _plotly_io()
    if include_js:
        js = True if inline_js else "cdn"
    else:
        js = False
    return pio.to_html(
        figure,
        include_plotlyjs=js,
        full_html=False,
        config=PLOTLY_CONFIG,
        default_width="100%",
    )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

CSS = """
:root { --ink:#1a1f26; --muted:#5b6470; --line:#e6e9ee; --bg:#f7f8fa; }
* { box-sizing: border-box; }
body { margin:0; padding:32px 20px 64px; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
main { max-width: 900px; margin: 0 auto; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
h2 { font-size:19px; margin:36px 0 10px; padding-top:20px; border-top:1px solid var(--line); }
h3 { font-size:15px; margin:22px 0 8px; color:var(--muted); text-transform:uppercase;
  letter-spacing:.07em; font-weight:600; }
.sub { color:var(--muted); margin:0 0 22px; font-size:13.5px; }
.card { background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:14px; margin:16px 0; }
table { border-collapse:collapse; width:100%; font-size:13.5px; }
th,td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; font-size:11.5px; text-transform:uppercase;
  letter-spacing:.05em; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.metrics { display:grid; grid-template-columns:repeat(auto-fill,minmax(178px,1fr)); gap:10px; }
.metric { background:#fff; border:1px solid var(--line); border-radius:8px; padding:11px 13px; }
.metric .label { font-size:11px; color:var(--muted); display:block; margin-bottom:3px; }
.metric .value { font-size:17px; font-weight:600; font-variant-numeric:tabular-nums; }
.pill { display:inline-block; padding:2px 8px; border-radius:99px; font-size:11px;
  font-weight:600; }
.pill.ok { background:#e2f5ee; color:#00674c; }
.pill.warn { background:#fdf1dd; color:#8a5a00; }
.pill.bad { background:#fce6dc; color:#8f3200; }
.note { font-size:12.5px; color:var(--muted); margin:8px 0 0; }
.empty { color:var(--muted); font-style:italic; }
footer { margin-top:40px; padding-top:16px; border-top:1px solid var(--line);
  font-size:12px; color:var(--muted); }
code { background:#eef0f4; padding:1px 5px; border-radius:4px; font-size:12.5px; }
"""


def _metric_cards(result: dict, metric_fn) -> str:
    cards = []
    for m in metric_fn(result):
        if m["unit"] == "rows":
            continue  # shown in the data-quality section instead
        cards.append(
            f'<div class="metric"><span class="label">{_e(m["label"])}</span>'
            f'<span class="value">{_e(format_value(m["value"], m["unit"]))}'
            f'</span></div>'
        )
    return f'<div class="metrics">{"".join(cards)}</div>' if cards else ""


def _quarantine_table(result: dict) -> str:
    bad = result["quarantined"]
    if not bad:
        return '<p class="note">Nothing was quarantined for this symbol.</p>'
    rows = "".join(
        f'<tr><td>{_e(b["candle"].get("date") if isinstance(b["candle"], dict) else "?")}</td>'
        f'<td><span class="pill bad">{_e(b["reason"])}</span></td>'
        f'<td>{_e(b["detail"])}</td></tr>'
        for b in bad
    )
    return ('<table><thead><tr><th>Date as received</th><th>Reason</th>'
            f'<th>Detail</th></tr></thead><tbody>{rows}</tbody></table>')


def _repair_table(result: dict) -> str:
    repaired = [r for r in result["rows"] if r.get("repaired")]
    if not repaired:
        return ""
    rows = "".join(
        f'<tr><td>{_e(row["date"])}</td>'
        f'<td><span class="pill warn">{_e(entry["code"])}</span></td>'
        f'<td>{_e(entry["detail"])}</td></tr>'
        for row in repaired for entry in row["repairs"]
    )
    return ('<h3>Repaired and loaded</h3>'
            '<table><thead><tr><th>Date</th><th>Repair</th>'
            f'<th>What changed</th></tr></thead><tbody>{rows}</tbody></table>'
            '<p class="note">These rows are loaded but flagged, and drawn as '
            'open diamonds on the price chart. A claim that must rest only on '
            'observed data should exclude them.</p>')


def _leaderboard(results: list[dict]) -> str:
    """Ranked table of every symbol. The entry point for a wide pull."""
    scored = [r for r in results if r["rows"]]
    if not scored:
        return ""
    scored = sorted(scored, key=lambda r: r["summary"]["period_return_pct"],
                    reverse=True)
    rows = []
    for result in scored:
        s = result["summary"]
        ret = s["period_return_pct"]
        vol = s.get("volatility_pct")
        rows.append(
            f'<tr><td>{_e(s["symbol"])}</td>'
            f'<td class="num"><span class="pill {"ok" if ret >= 0 else "bad"}">'
            f'{format_value(ret, "pct")}</span></td>'
            f'<td class="num">{format_value(vol, "pct") if vol is not None else "-"}</td>'
            f'<td class="num">{format_value(s.get("max_drawdown_pct"), "pct")}</td>'
            f'<td class="num">{format_value(s["close_last"], "price")}</td>'
            f'<td class="num">{s["rows_kept"]}</td>'
            f'<td class="num">{s["rows_quarantined"]}</td></tr>'
        )
    return ('<table><thead><tr><th>Symbol</th><th>Return</th>'
            '<th>Volatility</th><th>Max drawdown</th><th>Last close</th>'
            f'<th>Loaded</th><th>Quarantined</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def build_report(results: list[dict], run_id: str, metric_fn,
                 generated_at: datetime | None = None,
                 inline_js: bool = True) -> str:
    """Return the complete HTML document as a string.

    `metric_fn` is `transform.metrics`, injected rather than imported so this
    module stays testable in isolation.

    Raises PlotlyMissing if plotly is not installed.
    """
    generated_at = generated_at or datetime.now()
    loaded = sum(r["summary"]["rows_kept"] for r in results)
    quarantined = sum(r["summary"]["rows_quarantined"] for r in results)
    repaired = sum(r["summary"].get("rows_repaired", 0) for r in results)
    received = sum(r["summary"]["candles_in"] for r in results)
    reconciled = received == loaded + quarantined

    # The plotly bundle goes into the first figure rendered and no other.
    state = {"js_done": False}

    def chart(figure) -> str:
        if figure is None:
            return '<p class="empty">No data to chart.</p>'
        fragment = _render(figure, include_js=not state["js_done"],
                           inline_js=inline_js)
        state["js_done"] = True
        return fragment

    body = [
        "<main>",
        "<h1>Market data pipeline report</h1>",
        f'<p class="sub">Run <code>{_e(run_id)}</code> &middot; generated '
        f'{generated_at:%Y-%m-%d %H:%M} &middot; {len(results)} symbol(s) '
        f'&middot; {loaded:,} rows loaded, {quarantined:,} quarantined</p>',
        "<h2>Overview</h2>",
    ]

    figure, trimmed = comparison_figure(results)
    if figure:
        body.append('<div class="card">')
        body.append(chart(figure))
        note = ("Each line starts at 100 on its own first trading day, so a "
                "line at 104 has risen 4% since then. Rebasing lets "
                "instruments at very different price levels be compared on "
                "one axis.")
        if trimmed:
            charted_total = len([r for r in results if len(r["rows"]) >= 2])
            note += (f" Showing the {MAX_COMPARISON_SERIES} largest movers of "
                     f"{charted_total} symbols; every symbol is in the table "
                     f"below.")
        body.append(f'<p class="note">{note}</p>')
        body.append("</div>")

    body.append('<div class="card">')
    body.append(chart(quality_figure(results)))
    body.append(
        f'<p class="note">{received:,} candles received; {loaded - repaired:,} '
        f'loaded clean, {repaired:,} loaded after repair, {quarantined:,} '
        f'quarantined. '
        + ('<span class="pill ok">Reconciled</span>' if reconciled
           else '<span class="pill bad">Reconciliation failed</span>')
        + '</p>'
    )
    body.append("</div>")

    if len(results) > 1:
        body.append("<h2>Every symbol, ranked by return</h2>")
        body.append(f'<div class="card">{_leaderboard(results)}</div>')

    # --- Per symbol -----------------------------------------------------
    detail = results
    if len(results) > MAX_DETAIL_SECTIONS:
        # Detail the extremes rather than everything: the table above already
        # covers all of them, and 200 chart pairs is not a document anyone
        # reads.
        ranked = sorted([r for r in results if r["rows"]],
                        key=lambda r: r["summary"]["period_return_pct"])
        half = MAX_DETAIL_SECTIONS // 2
        detail = ranked[-half:][::-1] + ranked[:half]
        body.append(
            f'<p class="note">Charting the {len(detail)} most extreme of '
            f'{len(results)} symbols in detail. The ranked table above covers '
            f'every symbol, and every symbol is loaded to the store '
            f'regardless.</p>'
        )

    for result in detail:
        symbol = result["summary"]["symbol"]
        body.append(f"<h2>{_e(symbol)}</h2>")
        if result["rows"]:
            body.append(f'<div class="card">{chart(close_figure(result))}</div>')
            body.append(f'<div class="card">{chart(volume_figure(result))}</div>')
            body.append("<h3>Measures</h3>")
            body.append(_metric_cards(result, metric_fn))
        else:
            body.append('<p class="empty">No rows survived cleaning for this '
                        'symbol.</p>')
        body.append("<h3>Data quality</h3>")
        body.append(_quarantine_table(result))
        body.append(_repair_table(result))

    body.append(
        '<footer>Educational data from the Fauxnance API. Prices are invented '
        'and delayed; not for investment use. Charts are rendered with Plotly, '
        + ('whose JavaScript is embedded in this file, so it opens with no '
           'network connection.' if inline_js else
           'loaded from a CDN, so this file needs a network connection to '
           'render.')
        + '</footer>'
    )
    body.append("</main>")

    return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>Pipeline report {_e(run_id)}</title>\n"
            f"<style>{CSS}</style>\n</head>\n<body>\n"
            + "".join(body)
            + "\n</body>\n</html>\n")


def write_report(results: list[dict], run_id: str, metric_fn,
                 path: str = DEFAULT_REPORT_PATH, inline_js: bool = True) -> str:
    """Write the report and return the path written."""
    document = build_report(results, run_id, metric_fn, inline_js=inline_js)
    destination = Path(path)
    if destination.parent != Path(""):
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return str(destination)
