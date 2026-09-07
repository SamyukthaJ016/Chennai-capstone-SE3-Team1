from __future__ import annotations

SERIES_COLOURS = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#E69F00",
    "#CC79A7",
    "#56B4E9",
]

STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT_STACK = ('system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, '
              'Arial, sans-serif')

MAX_COMPARISON_SERIES = 6

MAX_DIRECT_LABELS = 4

PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

BASE_LAYOUT = {
    "template": "plotly_white",
    "font": {"family": FONT_STACK, "size": 13, "color": INK},
    "margin": {"l": 68, "r": 24, "t": 16, "b": 52},
    "plot_bgcolor": SURFACE,
    "paper_bgcolor": SURFACE,
    "hoverlabel": {
        "bgcolor": "#ffffff",
        "bordercolor": BASELINE,
        "font": {"family": FONT_STACK, "size": 12, "color": INK},
    },
}


def colour_for(index: int) -> str:
    return SERIES_COLOURS[index % len(SERIES_COLOURS)]


def axis(title: str, **extra) -> dict:
    spec = {
        "title": {"text": title, "font": {"size": 12, "color": INK_SECONDARY}},
        "gridcolor": GRIDLINE,
        "linecolor": BASELINE,
        "zeroline": False,
        "ticks": "outside",
        "ticklen": 4,
        "tickcolor": BASELINE,
        "tickfont": {"size": 11, "color": INK_MUTED},
    }
    spec.update(extra)
    return spec


def count_axis(title: str, largest: int | None = None, **extra) -> dict:
    spec = {"rangemode": "tozero", "tickformat": ",d"}
    if largest is not None and largest <= 10:
        spec["dtick"] = 1
    spec.update(extra)
    return axis(title, **spec)


def _layout(**overrides) -> dict:
    layout = {key: dict(value) if isinstance(value, dict) else value
              for key, value in BASE_LAYOUT.items()}
    layout.update(overrides)
    return layout


def _legend(**extra) -> dict:
    spec = {"orientation": "h", "yanchor": "bottom", "y": 1.02,
            "xanchor": "left", "x": 0,
            "font": {"size": 12, "color": INK_SECONDARY},
            "bgcolor": "rgba(0,0,0,0)"}
    spec.update(extra)
    return spec


def stagger(values: list[float], min_gap: float) -> list[float]:
    if not values:
        return []
    ranked = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    placed = list(values)
    for position, index in enumerate(ranked):
        if position == 0:
            continue
        above = placed[ranked[position - 1]]
        if above - placed[index] < min_gap:
            placed[index] = above - min_gap
    return placed


def split_by_quarter(rows: list[dict]) -> list[tuple]:
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["date"].year, (row["date"].month - 1) // 3 + 1)
        buckets.setdefault(key, []).append(row)

    multi_year = len({year for year, _ in buckets}) > 1
    return [
        (f"{year} Q{quarter}" if multi_year else f"Q{quarter}",
         buckets[(year, quarter)])
        for year, quarter in sorted(buckets)
    ]


def _currency_of(result: dict) -> str:
    return (result["summary"].get("currency") or result.get("currency")
            or "currency")


def comparison_figure(results: list[dict],
                      max_series: int = MAX_COMPARISON_SERIES) -> tuple:
    charted = [r for r in results if len(r["rows"]) >= 2]
    if not charted:
        return None, False

    trimmed = len(charted) > max_series
    if trimmed:
        charted = sorted(
            charted,
            key=lambda r: abs(r["summary"].get("period_return_pct") or 0.0),
            reverse=True,
        )[:max_series]

    traces = []
    endpoints = []
    for index, result in enumerate(charted):
        rows = result["rows"]
        symbol = result["summary"]["symbol"]
        base = rows[0]["close"]
        indexed = [round(r["close"] / base * 100, 4) for r in rows]
        traces.append({
            "type": "scatter",
            "mode": "lines",
            "name": symbol,
            "x": [r["date"].isoformat() for r in rows],
            "y": indexed,
            "line": {"color": colour_for(index), "width": 2},
            "hovertemplate": (f"<b>{symbol}</b><br>%{{y:.2f}} "
                              f"(100 = first day)<extra></extra>"),
        })
        endpoints.append((rows[-1]["date"].isoformat(), indexed[-1], symbol,
                          colour_for(index)))

    layout = _layout(
        xaxis=axis("Trading day", type="date"),
        yaxis=axis("Price, indexed to 100 on each instrument's first day"),
        hovermode="x unified",
        legend=_legend(),
        showlegend=len(traces) > 1,
        height=400,
        margin={"l": 68, "r": 24, "t": 44, "b": 52},
    )

    if len(endpoints) <= MAX_DIRECT_LABELS:
        finals = [point[1] for point in endpoints]
        span = (max(finals) - min(finals)) or 1.0
        placed = stagger(finals, span * 0.09)
        layout["annotations"] = [
            {"x": x, "y": y, "text": f" {symbol}", "showarrow": False,
             "xanchor": "left", "yanchor": "middle",
             "font": {"size": 11, "color": INK_SECONDARY},
             "xshift": 4}
            for (x, _, symbol, _), y in zip(endpoints, placed)
        ]
        layout["margin"] = {**layout["margin"], "r": 104}

    return {"data": traces, "layout": layout}, trimmed


def disposition_figure(results: list[dict]) -> dict | None:
    if not results:
        return None

    symbols = [r["summary"]["symbol"] for r in results]
    clean, repaired, quarantined = [], [], []
    for result in results:
        s = result["summary"]
        clean.append(s["rows_kept"] - s.get("rows_repaired", 0))
        repaired.append(s.get("rows_repaired", 0))
        quarantined.append(s["rows_quarantined"])

    def bar(name, values, colour, verb):
        return {
            "type": "bar", "orientation": "h", "name": name,
            "y": symbols, "x": values,
            "marker": {"color": colour,
                       "line": {"color": SURFACE, "width": 1.5}},
            "hovertemplate": f"%{{x:,}} {verb}<extra>%{{y}}</extra>",
        }

    traces = [
        bar("Loaded clean", clean, STATUS_GOOD, "loaded clean"),
        bar("Loaded after repair", repaired, STATUS_WARNING, "repaired"),
        bar("Quarantined", quarantined, STATUS_CRITICAL, "quarantined"),
    ]

    layout = _layout(
        barmode="stack",
        bargap=0.34,
        xaxis=count_axis("Candles received from the API",
                         max((sum(values) for values in
                              zip(clean, repaired, quarantined)), default=0)),
        yaxis=axis("Symbol", automargin=True, autorange="reversed"),
        legend=_legend(traceorder="normal"),
        hovermode="closest",
        height=max(200, 64 + 30 * len(symbols)),
        margin={"l": 68, "r": 24, "t": 44, "b": 52},
    )
    return {"data": traces, "layout": layout}


def reason_figure(reason_rows: list[dict]) -> dict | None:
    rows = [r for r in reason_rows if r.get("rows_affected")]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["rows_affected"])

    trace = {
        "type": "bar", "orientation": "h",
        "name": "Rows quarantined",
        "y": [r["reason"] for r in rows],
        "x": [r["rows_affected"] for r in rows],
        "marker": {"color": STATUS_CRITICAL,
                   "line": {"color": SURFACE, "width": 1.5}},
        "text": [f"{r['rows_affected']:,}" for r in rows],
        "textposition": "outside",
        "textfont": {"size": 11, "color": INK_SECONDARY},
        "cliponaxis": False,
        "hovertemplate": ("%{x:,} row(s) across %{customdata} symbol(s)"
                          "<extra>%{y}</extra>"),
        "customdata": [r.get("symbols", 0) for r in rows],
    }
    layout = _layout(
        xaxis=count_axis("Rows quarantined",
                         max((r["rows_affected"] for r in rows), default=0)),
        yaxis=axis("Reason code", automargin=True),
        showlegend=False,
        bargap=0.4,
        hovermode="closest",
        height=max(200, 60 + 34 * len(rows)),
    )
    return {"data": [trace], "layout": layout}


def price_figure(result: dict, by_quarter: bool = False,
                 colour_index: int = 0) -> dict | None:
    rows = result["rows"]
    if not rows:
        return None
    currency = _currency_of(result)
    symbol = result["summary"]["symbol"]

    def markers(bucket, colour):
        return {
            "size": [9 if r["repaired"] else 6 for r in bucket],
            "symbol": ["diamond-open" if r["repaired"] else "circle"
                       for r in bucket],
            "color": [STATUS_WARNING if r["repaired"] else colour
                      for r in bucket],
            "line": {"width": 1.5, "color": SURFACE},
        }

    def series(bucket, name, colour):
        return {
            "type": "scatter",
            "mode": "lines+markers",
            "name": name,
            "x": [r["date"].isoformat() for r in bucket],
            "y": [r["close"] for r in bucket],
            "line": {"color": colour, "width": 2},
            "marker": markers(bucket, colour),
            "hovertemplate": (f"<b>{symbol}</b><br>%{{y:,.2f}} {currency}"
                              f"<extra></extra>"),
        }

    if by_quarter:
        traces = [series(bucket, label, colour_for(index))
                  for index, (label, bucket)
                  in enumerate(split_by_quarter(rows))]
        show_legend = True
    else:
        traces = [series(rows, symbol, colour_for(colour_index))]
        show_legend = False

    layout = _layout(
        xaxis=axis("Trading day", type="date"),
        yaxis=axis(f"Closing price ({currency})"),
        hovermode="x unified",
        showlegend=show_legend,
        legend=_legend(),
        height=360,
        margin={"l": 68, "r": 24, "t": 44 if show_legend else 16, "b": 52},
    )

    repaired = [r for r in rows if r["repaired"]]
    if repaired:
        layout["annotations"] = [{
            "text": (f"{len(repaired)} point(s) drawn as open diamonds were "
                     f"repaired by the transform, not observed"),
            "showarrow": False, "xref": "paper", "yref": "paper",
            "x": 0, "y": 1.06, "xanchor": "left",
            "font": {"size": 11, "color": INK_MUTED},
        }]
        layout["margin"] = {**layout["margin"], "t": 52}
    return {"data": traces, "layout": layout}


def volume_figure(result: dict, colour_index: int = 0) -> dict | None:
    rows = result["rows"]
    if not rows:
        return None
    symbol = result["summary"]["symbol"]

    trace = {
        "type": "bar",
        "name": "Shares traded",
        "x": [r["date"].isoformat() for r in rows],
        "y": [r["volume"] for r in rows],
        "marker": {"color": colour_for(colour_index)},
        "hovertemplate": (f"<b>{symbol}</b><br>%{{y:,.0f}} shares"
                          f"<extra></extra>"),
    }
    layout = _layout(
        xaxis=axis("Trading day", type="date"),
        yaxis=axis("Shares traded", rangemode="tozero"),
        showlegend=False,
        hovermode="x unified",
        bargap=0.2,
        height=240,
    )

    missing = [r for r in rows if r["volume"] is None]
    if missing:
        layout["annotations"] = [{
            "text": (f"{len(missing)} day(s) with no volume reported are left "
                     f"blank, not drawn as zero"),
            "showarrow": False, "xref": "paper", "yref": "paper",
            "x": 0, "y": 1.1, "xanchor": "left",
            "font": {"size": 11, "color": INK_MUTED},
        }]
        layout["margin"] = {**layout["margin"], "t": 40}
    return {"data": [trace], "layout": layout}


def return_histogram(result: dict, colour_index: int = 0) -> dict | None:
    returns = [r["daily_return_pct"] for r in result["rows"]
               if r["daily_return_pct"] is not None]
    if len(returns) < 2:
        return None

    trace = {
        "type": "histogram",
        "x": returns,
        "name": "Trading days",
        "marker": {"color": colour_for(colour_index),
                   "line": {"color": SURFACE, "width": 1}},
        "hovertemplate": "%{y} day(s) returned %{x}<extra></extra>",
        "nbinsx": min(30, max(8, len(returns) // 6)),
    }
    layout = _layout(
        xaxis=axis("Daily return (%)"),
        yaxis=count_axis("Number of trading days", len(returns)),
        showlegend=False,
        hovermode="closest",
        height=240,
        shapes=[{
            "type": "line", "x0": 0, "x1": 0, "y0": 0, "y1": 1,
            "yref": "paper", "line": {"color": BASELINE, "width": 1},
        }],
    )
    return {"data": [trace], "layout": layout}


def metric_history_figure(rows: list[dict], label: str,
                          unit: str = "") -> dict | None:
    if not rows:
        return None

    order: list[str] = []
    for row in rows:
        if row["run_id"] not in order:
            order.append(row["run_id"])

    by_symbol: dict[str, dict[str, float]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], {})[row["run_id"]] = (
            float(row["value"]))

    traces = []
    for index, symbol in enumerate(sorted(by_symbol)):
        points = by_symbol[symbol]
        traces.append({
            "type": "scatter",
            "mode": "lines+markers",
            "name": symbol,
            "x": order,
            "y": [points.get(run_id) for run_id in order],
            "line": {"color": colour_for(index), "width": 2},
            "marker": {"size": 8, "line": {"width": 1.5, "color": SURFACE}},
            "connectgaps": False,
            "hovertemplate": f"<b>{symbol}</b><br>%{{y:,.4g}}<extra></extra>",
        })

    layout = _layout(
        xaxis=axis("Pipeline run", type="category"),
        yaxis=axis(f"{label}{f' ({unit})' if unit else ''}"),
        hovermode="x unified",
        legend=_legend(),
        showlegend=len(traces) > 1,
        height=340,
        margin={"l": 68, "r": 24, "t": 44, "b": 92},
    )
    return {"data": traces, "layout": layout}


def venue_gap_figure(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    labels = [r["day_type"] for r in rows]
    values = [float(r["median_gap_pct"]) for r in rows]
    colours = [STATUS_CRITICAL if "interpolated" in label.lower() else STATUS_GOOD
               for label in labels]

    trace = {
        "type": "bar", "orientation": "h", "name": "Median gap",
        "y": labels, "x": values,
        "marker": {"color": colours, "line": {"color": SURFACE, "width": 1.5}},
        "text": [f"{value:.3f}%" for value in values],
        "textposition": "outside",
        "textfont": {"size": 12, "color": INK_SECONDARY},
        "cliponaxis": False,
        "customdata": [r["days"] for r in rows],
        "hovertemplate": ("median %{x:.3f}% apart across %{customdata:,} day(s)"
                          "<extra>%{y}</extra>"),
    }
    layout = _layout(
        xaxis=axis("Median gap between the NSE and BSE close, same company and "
                   "day (%, log scale)", type="log", dtick=1),
        yaxis=axis("", automargin=True, showticklabels=True),
        showlegend=False,
        bargap=0.45,
        hovermode="closest",
        height=240,
        margin={"l": 68, "r": 90, "t": 16, "b": 62},
    )
    return {"data": [trace], "layout": layout}


def quarterly_figure(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    quarters = [r["quarter"] for r in rows]
    returns = [float(r["median_return_pct"]) for r in rows]
    advancing = [float(r["advancing_pct"]) for r in rows]

    traces = [
        {"type": "bar", "name": "Median return over the quarter",
         "x": quarters, "y": returns,
         "marker": {"color": [STATUS_CRITICAL if value < 0 else STATUS_GOOD
                              for value in returns],
                    "line": {"color": SURFACE, "width": 1.5}},
         "hovertemplate": "median %{y:+.2f}%<extra>%{x}</extra>"},
        {"type": "scatter", "mode": "lines+markers",
         "name": "Share of names advancing",
         "x": quarters, "y": advancing,
         "line": {"color": colour_for(0), "width": 2},
         "marker": {"size": 9, "line": {"width": 1.5, "color": SURFACE}},
         "hovertemplate": "%{y:.1f}% of names rose<extra>%{x}</extra>"},
    ]
    layout = _layout(
        xaxis=axis("Quarter", type="category"),
        yaxis=axis("Percent - median return, and share of names advancing"),
        hovermode="x unified",
        legend=_legend(),
        showlegend=True,
        bargap=0.45,
        height=360,
        margin={"l": 68, "r": 24, "t": 44, "b": 56},
        shapes=[{"type": "line", "x0": 0, "x1": 1, "xref": "paper",
                 "y0": 0, "y1": 0, "line": {"color": BASELINE, "width": 1}}],
    )
    return {"data": traces, "layout": layout}


def volatility_figure(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    quarters = [r["quarter"] for r in rows]
    values = [float(r["median_volatility_pct"]) for r in rows]

    trace = {
        "type": "scatter", "mode": "lines+markers",
        "name": "Median daily volatility",
        "x": quarters, "y": values,
        "line": {"color": colour_for(1), "width": 2},
        "marker": {"size": 9, "line": {"width": 1.5, "color": SURFACE}},
        "hovertemplate": "%{y:.3f}% per day<extra>%{x}</extra>",
    }
    layout = _layout(
        xaxis=axis("Quarter", type="category"),
        yaxis=axis("Median daily volatility (%), standard deviation of daily "
                   "returns", rangemode="tozero"),
        showlegend=False,
        hovermode="x unified",
        height=300,
        margin={"l": 68, "r": 24, "t": 16, "b": 56},
    )
    return {"data": [trace], "layout": layout}


def interpolation_figure(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    quarters = []
    for row in rows:
        if row["quarter"] not in quarters:
            quarters.append(row["quarter"])

    by_venue: dict[str, dict[str, float]] = {}
    for row in rows:
        by_venue.setdefault(row["exchange"], {})[row["quarter"]] = float(
            row["interpolated_pct"])

    traces = []
    for index, venue in enumerate(sorted(by_venue)):
        points = by_venue[venue]
        traces.append({
            "type": "scatter", "mode": "lines+markers", "name": venue,
            "x": quarters, "y": [points.get(q) for q in quarters],
            "line": {"color": colour_for(index), "width": 2},
            "marker": {"size": 9, "line": {"width": 1.5, "color": SURFACE}},
            "connectgaps": False,
            "hovertemplate": f"<b>{venue}</b><br>%{{y:.2f}}% interpolated"
                             f"<extra></extra>",
        })
    layout = _layout(
        xaxis=axis("Quarter", type="category"),
        yaxis=axis("Share of loaded rows the vendor interpolated (%)",
                   rangemode="tozero"),
        hovermode="x unified",
        legend=_legend(),
        showlegend=len(traces) > 1,
        height=300,
        margin={"l": 68, "r": 24, "t": 44, "b": 56},
    )
    return {"data": traces, "layout": layout}


def dispersion_figure(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    quarters = [r["quarter"] for r in rows]
    bottoms = [float(r["bottom_decile_pct"]) for r in rows]
    tops = [float(r["top_decile_pct"]) for r in rows]
    medians = [float(r["median_return_pct"]) for r in rows]

    traces = [
        {"type": "bar", "x": quarters, "y": bottoms,
         "marker": {"color": "rgba(0,0,0,0)"}, "hoverinfo": "skip",
         "showlegend": False, "name": ""},
        {"type": "bar", "name": "Bottom decile to top decile",
         "x": quarters, "y": [top - bottom
                              for top, bottom in zip(tops, bottoms)],
         "marker": {"color": colour_for(0),
                    "line": {"color": SURFACE, "width": 1.5}},
         "customdata": [[bottom, top] for bottom, top in zip(bottoms, tops)],
         "hovertemplate": ("bottom decile %{customdata[0]:+.2f}%<br>"
                           "top decile %{customdata[1]:+.2f}%"
                           "<extra>%{x}</extra>")},
        {"type": "scatter", "mode": "markers", "name": "Median name",
         "x": quarters, "y": medians,
         "marker": {"color": INK, "size": 11, "symbol": "line-ew-open",
                    "line": {"width": 2.5, "color": INK}},
         "hovertemplate": "median %{y:+.2f}%<extra>%{x}</extra>"},
    ]

    layout = _layout(
        barmode="stack",
        xaxis=axis("Quarter", type="category"),
        yaxis=axis("Return over the quarter (%)"),
        hovermode="x unified",
        legend=_legend(),
        showlegend=True,
        bargap=0.5,
        height=380,
        margin={"l": 68, "r": 24, "t": 44, "b": 56},
        shapes=[{"type": "line", "x0": 0, "x1": 1, "xref": "paper",
                 "y0": 0, "y1": 0, "line": {"color": BASELINE, "width": 1}}],
    )
    return {"data": traces, "layout": layout}
