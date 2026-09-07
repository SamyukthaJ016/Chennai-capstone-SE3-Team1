from __future__ import annotations

from dataclasses import dataclass, field

MIN_SYMBOLS = 20

MIN_QUARTERS = 3

FULL_HISTORY_SHARE = 0.95


@dataclass(frozen=True)
class Measure:

    label: str
    value: float | None
    unit: str


@dataclass(frozen=True)
class Finding:

    id: str
    title: str
    available: bool = True
    reason: str = ""
    headline: str = ""
    period: str = ""
    supported_by: str = ""
    decision: str = ""
    for_developers: str = ""
    falsified_if: str = ""
    measures: list = field(default_factory=list)
    table: list = field(default_factory=list)


_UNIVERSE = r"""
    WITH main_interval AS (
        SELECT "interval" FROM daily_price
         GROUP BY "interval" ORDER BY count(*) DESC LIMIT 1),
    listings AS (
        SELECT symbol,
               regexp_replace(symbol, '\.(NS|BO)$', '') AS root,
               count(*) AS observed
          FROM daily_price
         WHERE "interval" = (SELECT "interval" FROM main_interval)
           AND NOT synthetic
         GROUP BY symbol, root),
    span AS (SELECT max(observed) AS full_span FROM listings),
    primary_listing AS (
        SELECT symbol FROM (
            SELECT symbol, observed,
                   row_number() OVER (PARTITION BY root
                                      ORDER BY observed DESC, symbol) AS rank
              FROM listings)
         WHERE rank = 1),
    universe AS (
        SELECT l.symbol
          FROM listings l
          JOIN primary_listing p USING (symbol), span
         WHERE l.observed >= span.full_span * {share})
"""

_OBSERVED = _UNIVERSE + """,
    obs AS (
        SELECT d.symbol, d.trade_date, d."close", d.daily_return_pct
          FROM daily_price d JOIN universe u USING (symbol)
         WHERE NOT d.synthetic)
"""

QUARTER_STATS_SQL = _OBSERVED + """,
    qret AS (
        SELECT CAST(year(trade_date) AS VARCHAR) || ' Q'
               || CAST(quarter(trade_date) AS VARCHAR) AS quarter,
               symbol,
               100.0 * (last("close" ORDER BY trade_date)
                        - first("close" ORDER BY trade_date))
                     / first("close" ORDER BY trade_date) AS ret
          FROM obs GROUP BY quarter, symbol),
    qvol AS (
        SELECT CAST(year(trade_date) AS VARCHAR) || ' Q'
               || CAST(quarter(trade_date) AS VARCHAR) AS quarter,
               symbol, stddev_samp(daily_return_pct) AS vol
          FROM obs WHERE daily_return_pct IS NOT NULL
         GROUP BY quarter, symbol)
    SELECT r.quarter,
           count(*)                                         AS symbols,
           round(median(r.ret), 2)                          AS median_return_pct,
           round(100.0 * sum(CASE WHEN r.ret > 0 THEN 1 ELSE 0 END)
                 / count(*), 1)                             AS advancing_pct,
           round(quantile_cont(r.ret, 0.9), 2)              AS top_decile_pct,
           round(quantile_cont(r.ret, 0.1), 2)              AS bottom_decile_pct,
           round(quantile_cont(r.ret, 0.9)
                 - quantile_cont(r.ret, 0.1), 2)            AS spread_pts,
           round(median(v.vol), 3)                          AS median_volatility_pct
      FROM qret r JOIN qvol v ON v.quarter = r.quarter AND v.symbol = r.symbol
     GROUP BY r.quarter
     ORDER BY r.quarter
"""

RECOVERY_SQL = _OBSERVED + """,
    marks AS (
        SELECT symbol,
               last("close" ORDER BY trade_date)
                 FILTER (WHERE trade_date < DATE '{pivot}')  AS before,
               last("close" ORDER BY trade_date)             AS latest
          FROM obs GROUP BY symbol)
    SELECT count(*)                                          AS symbols,
           round(median(100.0 * (latest - before) / before), 2)
                                                             AS median_vs_before_pct,
           sum(CASE WHEN latest >= before THEN 1 ELSE 0 END)  AS recovered,
           round(100.0 * sum(CASE WHEN latest >= before THEN 1 ELSE 0 END)
                 / count(*), 1)                              AS recovered_pct
      FROM marks WHERE before IS NOT NULL
"""

REGIME_SQL = _OBSERVED + """,
    v AS (
        SELECT symbol,
               stddev_samp(daily_return_pct)
                 FILTER (WHERE trade_date < DATE '{start}')   AS before,
               stddev_samp(daily_return_pct)
                 FILTER (WHERE trade_date >= DATE '{end}')    AS after
          FROM obs WHERE daily_return_pct IS NOT NULL
         GROUP BY symbol)
    SELECT round(median(before), 3)                           AS before_pct,
           round(median(after), 3)                            AS after_pct,
           round(100.0 * (median(after) - median(before))
                 / median(before), 1)                         AS change_pct
      FROM v WHERE before IS NOT NULL AND after IS NOT NULL
"""

COVERAGE_SQL = _OBSERVED + """
    SELECT count(DISTINCT symbol) AS symbols,
           min(trade_date)        AS date_from,
           max(trade_date)        AS date_to
      FROM obs
"""


def _sql(template: str, **values) -> str:
    return template.format(share=FULL_HISTORY_SHARE, **values)


def market_context(handle) -> dict:
    from . import store as store_module

    quarters = store_module.records(handle, _sql(QUARTER_STATS_SQL))
    coverage = store_module.records(handle, _sql(COVERAGE_SQL))
    coverage = coverage[0] if coverage else {}

    context = {
        "quarters": quarters,
        "symbols": int(coverage.get("symbols") or 0),
        "date_from": coverage.get("date_from"),
        "date_to": coverage.get("date_to"),
        "selloff": None,
        "rebound": None,
    }
    if not quarters:
        return context

    worst = min(quarters, key=lambda q: float(q["median_return_pct"]))
    if float(worst["median_return_pct"]) < 0:
        context["selloff"] = worst
        after = [q for q in quarters if q["quarter"] > worst["quarter"]]
        if after:
            context["rebound"] = max(
                after, key=lambda q: float(q["median_return_pct"]))
    return context


def _quarter_start(quarter: str) -> str:
    year, q = quarter.split(" Q")
    return f"{int(year):04d}-{(int(q) - 1) * 3 + 1:02d}-01"


def _quarter_end_exclusive(quarter: str) -> str:
    year, q = int(quarter.split(" Q")[0]), int(quarter.split(" Q")[1])
    return f"{year + 1:04d}-01-01" if q == 4 else f"{year:04d}-{q * 3 + 1:02d}-01"


def _period_of(context: dict) -> str:
    lo, hi = context.get("date_from"), context.get("date_to")
    if not lo or not hi:
        return "no data"
    return (f"{lo:%d %b %Y} to {hi:%d %b %Y}, "
            f"{context['symbols']} symbols with the full period")


def _too_thin(context: dict) -> str | None:
    if context["symbols"] < MIN_SYMBOLS:
        return (f"Only {context['symbols']} symbol"
                f"{'' if context['symbols'] == 1 else 's'} "
                f"{'has' if context['symbols'] == 1 else 'have'} the full "
                f"period. A claim about the market needs at least "
                f"{MIN_SYMBOLS} for a distribution to mean anything.")
    if len(context["quarters"]) < MIN_QUARTERS:
        return (f"The store spans {len(context['quarters'])} quarter(s). "
                f"Comparing one period against another needs at least "
                f"{MIN_QUARTERS}.")
    return None


def dispersion_claim(handle, context: dict) -> Finding:
    title = "How much stock selection mattered, and when"
    thin = _too_thin(context)
    if thin:
        return Finding(id="dispersion", title=title, available=False,
                       reason=thin)
    selloff, rebound = context["selloff"], context["rebound"]
    if not selloff or not rebound:
        return Finding(
            id="dispersion", title=title, available=False,
            reason=("No quarter in this store has a negative median return "
                    "followed by a recovery quarter, so there is no crash and "
                    "rebound to compare."))

    fell = round(100.0 - float(selloff["advancing_pct"]), 1)
    widest = max(context["quarters"], key=lambda q: float(q["spread_pts"]))
    wider = float(rebound["spread_pts"]) > float(selloff["spread_pts"])

    headline = (
        f"The {selloff['quarter']} selloff moved the market as a block: "
        f"{fell:.0f}% of names fell, and even the best decile managed only "
        f"{float(selloff['top_decile_pct']):+.2f}%. The {rebound['quarter']} "
        f"rebound did not simply reverse it -- it spread the market out to "
        f"{float(rebound['spread_pts']):.2f} points between the top and bottom "
        f"decile, against {float(selloff['spread_pts']):.2f} in the selloff"
        + (f", the widest of the {len(context['quarters'])} quarters on record."
           if widest["quarter"] == rebound["quarter"] else ".")
        + " Which names you held mattered far more on the way back up than on "
          "the way down.")

    if not wider:
        headline = (
            f"The {selloff['quarter']} selloff took the median name down "
            f"{float(selloff['median_return_pct']):.2f}%, and the "
            f"{rebound['quarter']} rebound was no more selective: the "
            f"top-to-bottom decile spread was {float(rebound['spread_pts']):.2f} "
            f"points against {float(selloff['spread_pts']):.2f} in the selloff. "
            f"Both regimes moved names together.")

    return Finding(
        id="dispersion", title=title,
        headline=headline,
        period=_period_of(context),
        supported_by="Claims tab, 'How far apart the winners and losers finished'",
        decision=(
            f"Budget risk differently for the two regimes. In "
            f"{selloff['quarter']} the bottom decile fell "
            f"{float(selloff['bottom_decile_pct']):.2f}% while the top decile "
            f"managed {float(selloff['top_decile_pct']):+.2f}%, so "
            f"diversification bought little and hedging the market was the "
            f"defence that worked. In {rebound['quarter']} the gap between a "
            f"good pick and a bad one was {float(rebound['spread_pts']):.2f} "
            f"points, which is where selection rather than exposure decided "
            f"the quarter."),
        for_developers=(
            "Deciles need the whole distribution, not a summary: this measure "
            "is impossible against a pre-aggregated index feed and is one "
            "`quantile_cont` away against one row per symbol per day, which is "
            "why the store keeps the grain it does. The quarters are keyed on "
            "year AND quarter -- this store spans more than one calendar year, "
            "and bucketing on the quarter alone would average two regimes into "
            "one number."),
        falsified_if=(
            f"The {selloff['quarter']} spread were as wide as "
            f"{rebound['quarter']}'s, which would mean the selloff "
            f"discriminated between names as much as the recovery did. It "
            f"would also weaken if the deciles were set by a handful of "
            f"illiquid names rather than the body of the universe -- a decile "
            f"of {context['symbols']} symbols is about "
            f"{max(1, context['symbols'] // 10)} names."),
        measures=[
            Measure(f"Top-minus-bottom decile spread, {selloff['quarter']}",
                    float(selloff["spread_pts"]), "pts"),
            Measure(f"Top-minus-bottom decile spread, {rebound['quarter']}",
                    float(rebound["spread_pts"]), "pts"),
            Measure(f"Best decile, {selloff['quarter']}",
                    float(selloff["top_decile_pct"]), "pct"),
            Measure(f"Worst decile, {selloff['quarter']}",
                    float(selloff["bottom_decile_pct"]), "pct"),
            Measure(f"Best decile, {rebound['quarter']}",
                    float(rebound["top_decile_pct"]), "pct"),
        ],
        table=context["quarters"],
    )


def breadth_claim(handle, context: dict) -> Finding:
    from . import store as store_module

    title = "How far the recovery actually reached"
    thin = _too_thin(context)
    if thin:
        return Finding(id="breadth", title=title, available=False, reason=thin)
    selloff = context["selloff"]
    if not selloff:
        return Finding(
            id="breadth", title=title, available=False,
            reason=("No quarter in this store has a negative median return, "
                    "so there is no drawdown to measure a recovery from."))

    pivot = _quarter_start(selloff["quarter"])
    rows = store_module.records(handle, _sql(RECOVERY_SQL, pivot=pivot))
    if not rows or rows[0]["median_vs_before_pct"] is None:
        return Finding(
            id="breadth", title=title, available=False,
            reason=(f"No symbol has closes both before and after "
                    f"{selloff['quarter']}, so there is nothing to compare."))

    r = rows[0]
    recovered_pct = float(r["recovered_pct"])
    median_now = float(r["median_vs_before_pct"])
    fell = round(100.0 - float(selloff["advancing_pct"]), 1)
    narrow = recovered_pct < 50

    headline = (
        f"The median name fell "
        f"{abs(float(selloff['median_return_pct'])):.2f}% through "
        f"{selloff['quarter']}, with {fell:.0f}% of the universe falling. It "
        f"now sits {median_now:+.2f}% against its pre-selloff close -- but "
        f"only {int(r['recovered'])} of {int(r['symbols'])} names "
        f"({recovered_pct:.1f}%) are actually back above it. "
        + ("The typical stock looks repaired; most stocks are not."
           if narrow else
           "The median and the breadth agree, so the recovery is broad."))

    return Finding(
        id="breadth", title=title,
        headline=headline,
        period=(f"Selloff measured over {selloff['quarter']}; recovery "
                f"measured to {context['date_to']:%d %b %Y} against each "
                f"name's own close before it"),
        supported_by="Claims tab, 'How far the recovery actually reached'",
        decision=(
            f"Do not read the median's round trip as the market having healed: "
            f"{100 - recovered_pct:.1f}% of names are still below where they "
            f"started. A book built to match a benchmark is carrying them, so "
            f"the recovery is concentrated and what reverses it would be too. "
            f"Check holdings individually against their pre-selloff close "
            f"before treating the drawdown as closed."
            if narrow else
            f"The recovery is broad -- {recovered_pct:.1f}% of names are back "
            f"above their pre-selloff close -- so the median is a fair summary "
            f"of it and position-level checks are less urgent than they would "
            f"be in a narrow recovery."),
        for_developers=(
            "A median is not a market. This claim exists only because the "
            "store keeps one row per symbol per day rather than a "
            "pre-aggregated index, so breadth -- how many names, not how much "
            "-- is a GROUP BY away. The universe is pinned to symbols with the "
            "full period for the same reason: pooling in symbols that appear "
            "late would change what 'the market' meant between one quarter and "
            "the next."),
        falsified_if=(
            f"The count of recovered names moved towards the median's own "
            f"recovery. Roughly half the universe back above its pre-selloff "
            f"close would make the median representative again. It also "
            f"assumes these {int(r['symbols'])} names stand in fairly for the "
            f"market, which a wider pull would settle."),
        measures=[
            Measure(f"Median return through {selloff['quarter']}",
                    float(selloff["median_return_pct"]), "pct"),
            Measure(f"Share of names advancing in {selloff['quarter']}",
                    float(selloff["advancing_pct"]), "pct"),
            Measure("Median name now, against its pre-selloff close",
                    median_now, "pct"),
            Measure("Share of names back at or above that close",
                    recovered_pct, "pct"),
        ],
        table=context["quarters"],
    )


def volatility_claim(handle, context: dict) -> Finding:
    from . import store as store_module

    title = "Whether the volatility regime came back down"
    thin = _too_thin(context)
    if thin:
        return Finding(id="volatility", title=title, available=False,
                       reason=thin)
    selloff = context["selloff"]
    if not selloff:
        return Finding(
            id="volatility", title=title, available=False,
            reason=("No quarter has a negative median return, so there is no "
                    "event to measure a regime change around."))

    rows = store_module.records(handle, _sql(
        REGIME_SQL,
        start=_quarter_start(selloff["quarter"]),
        end=_quarter_end_exclusive(selloff["quarter"])))
    if not rows or rows[0]["before_pct"] is None or rows[0]["after_pct"] is None:
        return Finding(
            id="volatility", title=title, available=False,
            reason=(f"There is not a full quarter of returns on both sides of "
                    f"{selloff['quarter']} to compare."))

    r = rows[0]
    before, after = float(r["before_pct"]), float(r["after_pct"])
    change = float(r["change_pct"])
    stayed = change > 10

    headline = (
        f"Median daily volatility rose from {before:.3f}% before "
        f"{selloff['quarter']} to {after:.3f}% after it, a {change:+.1f}% "
        f"change that has not come back down "
        f"{len([q for q in context['quarters'] if q['quarter'] > selloff['quarter']])} "
        f"quarter(s) later. A position sized on the earlier data is carrying "
        f"about {abs(change):.0f}% more daily risk than it was sized for."
        if stayed else
        f"Median daily volatility was {before:.3f}% before "
        f"{selloff['quarter']} and {after:.3f}% after it, a {change:+.1f}% "
        f"change. The selloff did not leave a lasting change in how much the "
        f"typical name moves day to day.")

    return Finding(
        id="volatility", title=title,
        headline=headline,
        period=(f"Before: up to {_quarter_start(selloff['quarter'])}. After: "
                f"from {_quarter_end_exclusive(selloff['quarter'])}. The "
                f"selloff quarter itself is excluded from both sides, so the "
                f"comparison is calm against calm rather than being dominated "
                f"by the event"),
        supported_by="Claims tab, 'Volatility by quarter'",
        decision=(
            f"Re-calibrate position sizes and stop distances on the later "
            f"data. A limit set from the earlier window is roughly "
            f"{abs(change):.0f}% too loose, so the same nominal position "
            f"carries materially more daily risk than when it was sized. "
            f"Prices coming back is not the same event as risk coming back."
            if stayed else
            f"No re-calibration is called for on this evidence: daily "
            f"volatility is within {abs(change):.0f}% of where it was before "
            f"the selloff, so limits set on the earlier window still describe "
            f"the current regime."),
        for_developers=(
            "Volatility here is the sample standard deviation of daily "
            "returns, computed in `transform._stdev` and checked against "
            "`statistics.stdev` in the suite, so a wrong formula fails rather "
            "than being confirmed by its own output. It is quoted per day "
            "rather than annualised: annualising a window this short would "
            "invent a precision the data does not support."),
        falsified_if=(
            f"Median daily volatility returned to the {before:.3f}% band of "
            f"the earlier window, which would make this a spike rather than a "
            f"regime change. It would also weaken if the rise were "
            f"concentrated in a few names rather than the median -- the median "
            f"is used precisely because outliers cannot move it."),
        measures=[
            Measure(f"Median daily volatility before {selloff['quarter']}",
                    before, "pct"),
            Measure(f"Median daily volatility after {selloff['quarter']}",
                    after, "pct"),
            Measure("Change", change, "pct"),
        ],
        table=context["quarters"],
    )


GENERATORS = [dispersion_claim, breadth_claim, volatility_claim]


def generate(handle) -> list:
    context = market_context(handle)
    return [generator(handle, context) for generator in GENERATORS]


_DUAL_LISTED = r"""
    WITH t AS (
        SELECT regexp_replace(symbol, '\.(NS|BO)$', '') AS root,
               exchange, trade_date, "close", synthetic
          FROM daily_price),
    pair AS (
        SELECT n.root, n.trade_date,
               n."close" AS ns_close, b."close" AS bo_close,
               b.synthetic AS bo_synthetic
          FROM t n
          JOIN t b ON n.root = b.root AND n.trade_date = b.trade_date
         WHERE n.exchange = 'NSE' AND b.exchange = 'BSE')
"""

VENUE_DISAGREEMENT_SQL = _DUAL_LISTED + """
    SELECT CASE WHEN bo_synthetic THEN 'Vendor interpolated the BSE candle'
                ELSE 'Both venues traded' END        AS day_type,
           count(*)                                  AS days,
           round(100.0 * median(abs(bo_close - ns_close) / ns_close), 3)
                                                     AS median_gap_pct,
           round(100.0 * avg(abs(bo_close - ns_close) / ns_close), 3)
                                                     AS mean_gap_pct,
           round(100.0 * max(abs(bo_close - ns_close) / ns_close), 3)
                                                     AS worst_gap_pct
      FROM pair
     GROUP BY day_type
     ORDER BY median_gap_pct
"""

DUAL_LISTED_RETURNS_SQL = r"""
    WITH t AS (
        SELECT regexp_replace(symbol, '\.(NS|BO)$', '') AS root,
               exchange, trade_date, "close"
          FROM daily_price),
    ret AS (
        SELECT root, exchange, count(*) AS days,
               100.0 * (last("close" ORDER BY trade_date)
                        - first("close" ORDER BY trade_date))
                     / first("close" ORDER BY trade_date) AS r
          FROM t GROUP BY root, exchange)
    SELECT n.root                          AS company,
           round(n.r, 2)                   AS nse_return_pct,
           round(b.r, 2)                   AS bse_return_pct,
           round(abs(n.r - b.r), 2)        AS disagreement_pts
      FROM ret n JOIN ret b ON n.root = b.root
     WHERE n.exchange = 'NSE' AND b.exchange = 'BSE'
       AND n.days >= 250 AND b.days >= 250
     ORDER BY disagreement_pts DESC
"""


INTERPOLATION_BY_QUARTER_SQL = """
    SELECT CAST(year(trade_date) AS VARCHAR) || ' Q'
           || CAST(quarter(trade_date) AS VARCHAR) AS quarter,
           exchange,
           count(*)                                AS rows_loaded,
           round(100.0 * sum(CASE WHEN synthetic THEN 1 ELSE 0 END)
                 / count(*), 2)                    AS interpolated_pct
      FROM daily_price
     GROUP BY quarter, exchange
     ORDER BY quarter, exchange
"""


DEFAULT_CLAIMS_PATH = "ETL_Analysis/claims.md"


def _format(value, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "pct":
        return f"{value:+.2f}%"
    if unit == "pts":
        return f"{value:.2f} pts"
    return f"{value:,.2f}"


def _quarter_table(rows: list) -> str:
    if not rows:
        return ""
    header = ("| Quarter | Median | Advancing | Bottom decile | Top decile "
              "| Spread | Daily volatility |\n"
              "|---|---:|---:|---:|---:|---:|---:|\n")
    body = "".join(
        f"| {r['quarter']} "
        f"| {float(r['median_return_pct']):+.2f}% "
        f"| {float(r['advancing_pct']):.1f}% "
        f"| {float(r['bottom_decile_pct']):+.2f}% "
        f"| {float(r['top_decile_pct']):+.2f}% "
        f"| {float(r['spread_pts']):.2f} "
        f"| {float(r['median_volatility_pct']):.3f}% |\n"
        for r in rows)
    return header + body


def render_markdown(findings: list, db_path: str, generated_at) -> str:
    supported = [f for f in findings if f.available]
    missing = [f for f in findings if not f.available]

    out = [
        "# Business claims",
        "",
        "**GENERATED FILE - do not edit by hand.** Every figure below is "
        "computed from the store. Regenerate it with "
        "`python -m ETL_Analysis.claims`, or as part of a run with "
        "`python -m ETL_Analysis.pipeline --claims`.",
        "",
        f"Generated {generated_at:%d %B %Y, %H:%M} from `{db_path}`.",
        "",
        "Each claim below names a subject, a magnitude, a direction and a "
        "period, and each can be checked -- and disagreed with -- against the "
        "store it came from. None of the numbers is typed: the questions are "
        "fixed, the answers are computed, so this document and the "
        "dashboard's Claims tab cannot drift apart.",
        "",
        "**What every claim excludes.** Observed rows only -- `NOT "
        "synthetic` -- so no claim is argued from a candle the vendor "
        "interpolated. One listing per company, so a dual-listed name is not "
        "weighted twice. And only symbols with the full period, so a symbol "
        "that joined the universe late cannot tilt a quarter it was absent "
        "for. The interpolation rate itself is a data-quality fact and lives "
        "on the dashboard's Data quality tab.",
        "",
        "Prices come from the Fauxnance API, are invented by the vendor, and "
        "are not for investment use. The reasoning is what generalises.",
        "",
        "---",
        "",
    ]

    for index, finding in enumerate(supported, start=1):
        out += [
            f"## Claim {index} -- {finding.title}",
            "",
            "> " + finding.headline.replace(" -- ", " — "),
            "",
            f"**Period.** {finding.period}.",
            "",
            f"**Chart that supports it.** {finding.supported_by}.",
            "",
        ]
        if finding.measures:
            out += ["| Measure | Figure |", "|---|---:|"]
            out += [f"| {m.label} | {_format(m.value, m.unit)} |"
                    for m in finding.measures]
            out += [""]
        if finding.table:
            out += ["Every quarter in the store, on the same basis:", "",
                    _quarter_table(finding.table)]
        out += [
            f"**The decision it drives.** {finding.decision}",
            "",
            f"**Why a developer should care.** {finding.for_developers}",
            "",
            "**What would have to be true for this to be wrong.** "
            + finding.falsified_if,
            "",
            "---",
            "",
        ]

    if missing:
        out += ["## Claims this store cannot support", "",
                "Reported rather than omitted, so a thin store is visibly "
                "thin instead of looking like there was nothing to say:", ""]
        out += [f"- **{f.title}** -- {f.reason}" for f in missing]
        out += ["", "---", ""]

    out += [
        "## Note on the entry point",
        "",
        "The pipeline is a **module with a `__main__` block**, not a console "
        "script:",
        "",
        "```bash",
        "python -m ETL_Analysis.pipeline               # extract -> transform -> load",
        "python -m ETL_Analysis.pipeline --claims      # ...and regenerate this file",
        "python -m ETL_Analysis.pipeline --dashboard   # ...and open the dashboard",
        "python -m ETL_Analysis.dashboard              # open the dashboard on its own",
        "python -m ETL_Analysis.claims                 # regenerate this file alone",
        "```",
        "",
        "`ETL_Analysis/__init__.py` makes the folder a package so `python -m` "
        "resolves; `pipeline.py` ends in "
        "`if __name__ == \"__main__\": sys.exit(main())`. There is no "
        "`pyproject.toml` yet, so there is no installed console script to "
        "declare -- that is the remaining packaging item in `README.md`.",
        "",
    ]
    return "\n".join(out)


def write_markdown(handle, path: str, db_path: str,
                   generated_at=None) -> str:
    from datetime import datetime
    from pathlib import Path

    document = render_markdown(generate(handle), db_path,
                               generated_at or datetime.now())
    destination = Path(path)
    if destination.parent != Path(""):
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return str(destination)


def main(argv: list | None = None) -> int:
    import argparse

    from . import store as store_module

    parser = argparse.ArgumentParser(
        description="Generate claims.md from the analytical store")
    parser.add_argument("--db", default=store_module.DEFAULT_DB_PATH,
                        help="DuckDB file to read (default: %(default)s)")
    parser.add_argument("--out", default=DEFAULT_CLAIMS_PATH,
                        help="where to write (default: %(default)s)")
    args = parser.parse_args(argv)

    try:
        handle = store_module.connect(args.db)
    except store_module.StoreUnavailable as exc:
        print(exc)
        return 1
    with handle:
        written = write_markdown(handle, args.out, args.db)
        findings = generate(handle)

    supported = sum(1 for f in findings if f.available)
    print(f"wrote {written}: {supported} of {len(findings)} claims supported "
          f"by {args.db}")
    for finding in findings:
        if not finding.available:
            print(f"  unsupported - {finding.title}: {finding.reason}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
