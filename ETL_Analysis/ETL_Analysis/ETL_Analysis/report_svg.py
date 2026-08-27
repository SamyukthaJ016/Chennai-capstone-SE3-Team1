"""Report: one self-contained HTML file per run.

Writes `report.html` with the run's charts and metrics. Not part of the ETL
core -- extract, transform and load are the pipeline; this renders what the
pipeline produced.

NO DEPENDENCIES, AND WHY
    The sprint requires chart artefacts that "open without a network", which
    rules out anything fetching JavaScript from a CDN at render time. plotly
    can inline its own JS and would satisfy that. This module instead emits
    hand-built inline SVG, which satisfies it more strongly: there is no
    JavaScript at all, no library version to pin, and the file renders in any
    browser, in an email, or in a PDF export.

    The trade-off is that the charts are static rather than interactive. If
    the review wants hover tooltips and zoom, swap this module for a plotly
    implementation writing to the same path -- `write_report()` is the only
    entry point the pipeline calls.

CHART READABILITY
    The sprint is explicit that a non-technical reader must be able to read a
    chart unaided: both axes labelled with units, a title that states the
    finding rather than naming the variables, no bare ticker without the
    company, no unexplained abbreviation. The helpers below take a title and
    axis labels as required arguments for that reason.
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

# Colour-blind-safe qualitative palette (Okabe-Ito). Distinguishable for the
# most common forms of colour vision deficiency, which a default red/green
# palette is not.
SERIES_COLOURS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00"]
COLOUR_GOOD = "#009E73"
COLOUR_REPAIRED = "#E69F00"
COLOUR_BAD = "#D55E00"
COLOUR_AXIS = "#5b6470"
COLOUR_GRID = "#e6e9ee"


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
    """Escape for HTML/SVG text nodes."""
    return html.escape(str(text), quote=True)


def _nice_ceiling(value: float) -> float:
    """Round an axis maximum up to something a reader can hold in their head."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** (len(str(int(value))) - 1)
    for step in (1, 2, 2.5, 5, 10):
        candidate = magnitude * step
        if candidate >= value:
            return candidate
    return magnitude * 10


# ---------------------------------------------------------------------------
# SVG chart builders
# ---------------------------------------------------------------------------

def line_chart(
    series: list[dict],
    title: str,
    x_label: str,
    y_label: str,
    categories: list[str] | None = None,
    width: int = 720,
    height: int = 320,
    y_from_zero: bool = False,
) -> str:
    """Multi-series line chart.

    series: [{"name": str, "points": [(label, value), ...]}]

    `categories` is the shared x axis. Series are aligned to it BY LABEL, not
    by position, so two instruments with different trading days land on the
    right dates: a symbol that did not trade on a given day leaves a gap there
    rather than shifting its whole line leftwards. Passing no categories means
    the union of every series' labels, in first-seen order.
    """
    left, right, top, bottom = 78, 24, 46, 62
    plot_w = width - left - right
    plot_h = height - top - bottom

    all_values = [v for s in series for _, v in s["points"] if v is not None]
    if not all_values:
        return f'<p class="empty">No data for {_e(title)}</p>'

    y_min = 0.0 if y_from_zero else min(all_values)
    y_max = max(all_values)
    if y_max == y_min:
        y_max = y_min + 1
    pad = (y_max - y_min) * 0.12
    y_min, y_max = y_min - pad, y_max + pad

    if categories is None:
        categories = []
        for entry in series:
            for label, _ in entry["points"]:
                if label not in categories:
                    categories.append(label)
    labels = categories
    n = max(len(labels), 2)
    index_of = {label: i for i, label in enumerate(labels)}

    def x_at(i):
        return left + (plot_w * i / (n - 1)) if n > 1 else left + plot_w / 2

    def y_at(v):
        return top + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_e(title)}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{width/2}" y="24" class="chart-title" '
        f'text-anchor="middle">{_e(title)}</text>',
    ]

    # Horizontal gridlines with value labels.
    for i in range(5):
        value = y_min + (y_max - y_min) * i / 4
        y = y_at(value)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{COLOUR_GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" class="tick" '
            f'text-anchor="end">{value:,.1f}</text>'
        )

    # X tick labels, thinned so they never overlap.
    every = max(1, len(labels) // 8)
    for i, label in enumerate(labels):
        if i % every and i != len(labels) - 1:
            continue
        parts.append(
            f'<text x="{x_at(i):.1f}" y="{top + plot_h + 20}" class="tick" '
            f'text-anchor="middle" transform="rotate(-35 {x_at(i):.1f} '
            f'{top + plot_h + 20})">{_e(label)}</text>'
        )

    # Series, positioned by category label rather than by list index.
    for index, entry in enumerate(series):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        placed = [
            (index_of[label], value)
            for label, value in entry["points"]
            if value is not None and label in index_of
        ]
        if placed:
            points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in placed)
            parts.append(
                f'<polyline fill="none" stroke="{colour}" stroke-width="2.5" '
                f'stroke-linejoin="round" points="{points}"/>'
            )
        for i, value in placed:
            parts.append(
                f'<circle cx="{x_at(i):.1f}" cy="{y_at(value):.1f}" r="3" '
                f'fill="{colour}"/>'
            )

    # Axes.
    parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="{COLOUR_AXIS}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" stroke="{COLOUR_AXIS}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="{left + plot_w/2}" y="{height - 6}" class="axis" '
        f'text-anchor="middle">{_e(x_label)}</text>'
    )
    parts.append(
        f'<text x="16" y="{top + plot_h/2}" class="axis" text-anchor="middle" '
        f'transform="rotate(-90 16 {top + plot_h/2})">{_e(y_label)}</text>'
    )

    if len(series) > 1:
        for index, entry in enumerate(series):
            colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
            x = left + index * 165
            parts.append(
                f'<rect x="{x}" y="{top - 18}" width="11" height="11" '
                f'rx="2" fill="{colour}"/>'
            )
            parts.append(
                f'<text x="{x + 17}" y="{top - 8}" class="legend">'
                f'{_e(entry["name"])}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def bar_chart(
    bars: list[tuple],
    title: str,
    x_label: str,
    y_label: str,
    width: int = 720,
    height: int = 300,
    colour: str = SERIES_COLOURS[0],
) -> str:
    """Vertical bar chart. bars: [(label, value), ...]"""
    left, right, top, bottom = 84, 24, 46, 62
    plot_w = width - left - right
    plot_h = height - top - bottom

    values = [v for _, v in bars if v is not None]
    if not values:
        return f'<p class="empty">No data for {_e(title)}</p>'

    y_max = _nice_ceiling(max(values))
    slot = plot_w / max(len(bars), 1)
    bar_w = min(slot * 0.62, 46)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_e(title)}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{width/2}" y="24" class="chart-title" '
        f'text-anchor="middle">{_e(title)}</text>',
    ]

    for i in range(5):
        value = y_max * i / 4
        y = top + plot_h - (value / y_max) * plot_h
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
            f'y2="{y:.1f}" stroke="{COLOUR_GRID}" stroke-width="1"/>'
        )
        shown = (f"{value/1_000_000:,.1f}m" if y_max >= 1_000_000
                 else f"{value:,.0f}")
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" class="tick" '
            f'text-anchor="end">{shown}</text>'
        )

    every = max(1, len(bars) // 10)
    for i, (label, value) in enumerate(bars):
        cx = left + slot * i + slot / 2
        if value is not None:
            h = (value / y_max) * plot_h
            parts.append(
                f'<rect x="{cx - bar_w/2:.1f}" y="{top + plot_h - h:.1f}" '
                f'width="{bar_w:.1f}" height="{h:.1f}" rx="2" fill="{colour}"/>'
            )
        else:
            parts.append(
                f'<rect x="{cx - bar_w/2:.1f}" y="{top + plot_h - 6}" '
                f'width="{bar_w:.1f}" height="6" rx="2" fill="{COLOUR_GRID}"/>'
            )
            parts.append(
                f'<text x="{cx:.1f}" y="{top + plot_h - 12}" class="tick" '
                f'text-anchor="middle">n/a</text>'
            )
        if i % every == 0 or i == len(bars) - 1:
            parts.append(
                f'<text x="{cx:.1f}" y="{top + plot_h + 20}" class="tick" '
                f'text-anchor="middle" transform="rotate(-35 {cx:.1f} '
                f'{top + plot_h + 20})">{_e(label)}</text>'
            )

    parts.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" stroke="{COLOUR_AXIS}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="{left + plot_w/2}" y="{height - 6}" class="axis" '
        f'text-anchor="middle">{_e(x_label)}</text>'
    )
    parts.append(
        f'<text x="16" y="{top + plot_h/2}" class="axis" text-anchor="middle" '
        f'transform="rotate(-90 16 {top + plot_h/2})">{_e(y_label)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def quality_chart(results: list[dict], width: int = 720, height: int = 260) -> str:
    """Stacked horizontal bar: how each symbol's candles were dispositioned."""
    left, right, top, bottom = 130, 24, 52, 54
    plot_w = width - left - right
    row_h = 30
    gap = 14

    max_in = max((r["summary"]["candles_in"] for r in results), default=0)
    if not max_in:
        return '<p class="empty">Nothing was extracted.</p>'

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Data quality by symbol" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{width/2}" y="24" class="chart-title" text-anchor="middle">'
        f'Every candle received is either loaded or quarantined</text>',
    ]

    legend = [("Loaded clean", COLOUR_GOOD), ("Loaded after repair", COLOUR_REPAIRED),
              ("Quarantined", COLOUR_BAD)]
    for index, (name, colour) in enumerate(legend):
        x = left + index * 190
        parts.append(f'<rect x="{x}" y="{top - 20}" width="11" height="11" '
                     f'rx="2" fill="{colour}"/>')
        parts.append(f'<text x="{x + 17}" y="{top - 10}" class="legend">'
                     f'{_e(name)}</text>')

    for i, result in enumerate(results):
        s = result["summary"]
        y = top + i * (row_h + gap)
        clean = s["rows_kept"] - s.get("rows_repaired", 0)
        segments = [
            (clean, COLOUR_GOOD),
            (s.get("rows_repaired", 0), COLOUR_REPAIRED),
            (s["rows_quarantined"], COLOUR_BAD),
        ]
        parts.append(
            f'<text x="{left - 12}" y="{y + 20}" class="tick" '
            f'text-anchor="end">{_e(s["symbol"])}</text>'
        )
        x = left
        for count, colour in segments:
            if not count:
                continue
            w = plot_w * count / max_in
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{row_h}" '
                f'fill="{colour}"/>'
            )
            if w > 22:
                parts.append(
                    f'<text x="{x + w/2:.1f}" y="{y + 20}" class="bar-label" '
                    f'text-anchor="middle">{count}</text>'
                )
            x += w

    parts.append(
        f'<text x="{width/2}" y="{height - 8}" class="axis" '
        f'text-anchor="middle">Candles received from the API</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

CSS = """
:root { --ink:#1a1f26; --muted:#5b6470; --line:#e6e9ee; --bg:#f7f8fa; }
* { box-sizing: border-box; }
body { margin:0; padding:32px 20px 64px; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
main { max-width: 860px; margin: 0 auto; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
h2 { font-size:19px; margin:36px 0 10px; padding-top:20px; border-top:1px solid var(--line); }
h3 { font-size:15px; margin:22px 0 8px; color:var(--muted); text-transform:uppercase;
  letter-spacing:.07em; font-weight:600; }
.sub { color:var(--muted); margin:0 0 22px; font-size:13.5px; }
.card { background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:18px; margin:16px 0; }
svg { width:100%; height:auto; display:block; }
.chart-title { font-size:14px; font-weight:600; fill:var(--ink); }
.tick { font-size:10.5px; fill:var(--muted); }
.axis { font-size:11.5px; fill:var(--muted); font-weight:600; }
.legend { font-size:11.5px; fill:var(--muted); }
.bar-label { font-size:11px; fill:#fff; font-weight:700; }
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
            f'<span class="value">{_e(format_value(m["value"], m["unit"]))}</span></div>'
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
    return (
        '<table><thead><tr><th>Date as received</th><th>Reason</th>'
        f'<th>Detail</th></tr></thead><tbody>{rows}</tbody></table>'
    )


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
    return (
        '<h3>Repaired and loaded</h3>'
        '<table><thead><tr><th>Date</th><th>Repair</th><th>What changed</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '<p class="note">These rows are loaded but flagged. A claim that must '
        'rest only on observed data should exclude them.</p>'
    )


def _leaderboard(results: list[dict]) -> str:
    """Ranked table of every symbol. The entry point for a wide pull."""
    scored = [r for r in results if r["rows"]]
    if not scored:
        return ""
    scored.sort(key=lambda r: r["summary"]["period_return_pct"], reverse=True)
    rows = []
    for result in scored:
        s = result["summary"]
        ret = s["period_return_pct"]
        pill = "ok" if ret >= 0 else "bad"
        vol = s.get("volatility_pct")
        rows.append(
            f'<tr><td>{_e(s["symbol"])}</td>'
            f'<td class="num"><span class="pill {pill}">'
            f'{format_value(ret, "pct")}</span></td>'
            f'<td class="num">{format_value(vol, "pct") if vol is not None else "-"}</td>'
            f'<td class="num">{format_value(s.get("max_drawdown_pct"), "pct")}</td>'
            f'<td class="num">{format_value(s["close_last"], "price")}</td>'
            f'<td class="num">{s["rows_kept"]}</td>'
            f'<td class="num">{s["rows_quarantined"]}</td></tr>'
        )
    return (
        '<table><thead><tr><th>Symbol</th><th>Return</th><th>Volatility</th>'
        '<th>Max drawdown</th><th>Last close</th><th>Loaded</th>'
        f'<th>Quarantined</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def build_report(results: list[dict], run_id: str, metric_fn,
                 generated_at: datetime | None = None) -> str:
    """Return the complete HTML document as a string.

    `metric_fn` is `transform.metrics`, injected rather than imported so this
    module stays testable in isolation.
    """
    generated_at = generated_at or datetime.now()
    loaded = sum(r["summary"]["rows_kept"] for r in results)
    quarantined = sum(r["summary"]["rows_quarantined"] for r in results)
    repaired = sum(r["summary"].get("rows_repaired", 0) for r in results)
    received = sum(r["summary"]["candles_in"] for r in results)
    reconciled = received == loaded + quarantined

    body = [
        "<main>",
        "<h1>Market data pipeline report</h1>",
        f'<p class="sub">Run <code>{_e(run_id)}</code> &middot; generated '
        f'{generated_at:%Y-%m-%d %H:%M} &middot; {len(results)} symbol(s) '
        f'&middot; {loaded:,} rows loaded, {quarantined:,} quarantined</p>',
    ]

    # --- Overview -------------------------------------------------------
    body.append("<h2>Overview</h2>")

    charted = [r for r in results if len(r["rows"]) >= 2]
    # With many symbols, chart the extremes: the biggest risers and fallers
    # are what a reader looks for, and a chart of 200 lines shows nothing.
    trimmed = len(charted) > MAX_COMPARISON_SERIES
    if trimmed:
        charted = sorted(
            charted, key=lambda r: abs(r["summary"]["period_return_pct"]),
            reverse=True,
        )[:MAX_COMPARISON_SERIES]

    rebased = []
    for result in charted:
        rows = result["rows"]
        base = rows[0]["close"]
        rebased.append({
            "name": result["summary"]["symbol"],
            "points": [(r["date"].strftime("%d %b"), r["close"] / base * 100)
                       for r in rows],
        })
    if rebased:
        # The shared date axis: every trading day any symbol traded on, in
        # order. Without this, symbols with different coverage would be drawn
        # against each other's dates.
        all_dates = sorted({r["date"] for result in results
                            for r in result["rows"]})
        categories = [d.strftime("%d %b") for d in all_dates]
        body.append('<div class="card">')
        body.append(line_chart(
            rebased,
            title="Each instrument's price movement over the period, "
                  "rebased so they can be compared",
            x_label="Trading day",
            y_label="Price, indexed to 100 at the first day",
            categories=categories,
        ))
        note = ('Each line starts at 100 on its own first trading day, so a '
                'line at 104 has risen 4% since then. Rebasing lets '
                'instruments at very different price levels be compared on '
                'one axis.')
        if trimmed:
            note += (f' Showing the {MAX_COMPARISON_SERIES} largest movers of '
                     f'{len([r for r in results if len(r["rows"]) >= 2])} '
                     f'symbols; every symbol is in the table below.')
        body.append(f'<p class="note">{note}</p>')
        body.append("</div>")

    body.append('<div class="card">')
    body.append(quality_chart(results))
    body.append(
        f'<p class="note">{received:,} candles received; {loaded - repaired:,} '
        f'loaded clean, {repaired:,} loaded after repair, {quarantined:,} '
        f'quarantined. '
        + (f'<span class="pill ok">Reconciled</span>' if reconciled
           else f'<span class="pill bad">Reconciliation failed</span>')
        + '</p>'
    )
    body.append("</div>")

    if len(results) > 1:
        body.append("<h2>Every symbol, ranked by return</h2>")
        body.append('<div class="card">')
        body.append(_leaderboard(results))
        body.append("</div>")

    # --- Per symbol -----------------------------------------------------
    detail = results
    if len(results) > MAX_DETAIL_SECTIONS:
        # Detail the extremes rather than everything: the table above already
        # covers all of them, and 200 chart pairs is not a document anyone
        # reads.
        ranked = sorted(
            [r for r in results if r["rows"]],
            key=lambda r: r["summary"]["period_return_pct"],
        )
        half = MAX_DETAIL_SECTIONS // 2
        detail = ranked[-half:][::-1] + ranked[:half]
        body.append(
            f'<p class="note">Charting the {len(detail)} most extreme of '
            f'{len(results)} symbols in detail. The ranked table above covers '
            f'every symbol, and every symbol is loaded to the store '
            f'regardless.</p>'
        )

    for result in detail:
        summary = result["summary"]
        symbol = summary["symbol"]
        rows = result["rows"]
        body.append(f"<h2>{_e(symbol)}</h2>")

        if rows:
            direction = "rose" if summary["period_return_pct"] >= 0 else "fell"
            body.append('<div class="card">')
            body.append(line_chart(
                [{"name": symbol,
                  "points": [(r["date"].strftime("%d %b"), r["close"])
                             for r in rows]}],
                title=f"{symbol} {direction} "
                      f"{abs(summary['period_return_pct']):.2f}% between "
                      f"{summary['date_from']:%d %b} and "
                      f"{summary['date_to']:%d %b %Y}",
                x_label="Trading day",
                y_label=f"Closing price ({summary.get('currency') or 'currency'})",
            ))
            body.append("</div>")

            body.append('<div class="card">')
            body.append(bar_chart(
                [(r["date"].strftime("%d %b"), r["volume"]) for r in rows],
                title=f"Shares traded each day in {symbol}",
                x_label="Trading day",
                y_label="Shares traded",
                colour=SERIES_COLOURS[1],
            ))
            body.append('<p class="note">A bar marked n/a is a day the data '
                        'provider reported no volume figure. It is not a day '
                        'with no trading.</p>')
            body.append("</div>")

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
        'and delayed; not for investment use. Charts are inline SVG, so this '
        'file opens with no network connection.</footer>'
    )
    body.append("</main>")

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Pipeline report {_e(run_id)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        + "".join(body)
        + "\n</body>\n</html>\n"
    )


def write_report(results: list[dict], run_id: str, metric_fn,
                 path: str = DEFAULT_REPORT_PATH) -> str:
    """Write the report and return the path written."""
    document = build_report(results, run_id, metric_fn)
    destination = Path(path)
    if destination.parent != Path(""):
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return str(destination)
