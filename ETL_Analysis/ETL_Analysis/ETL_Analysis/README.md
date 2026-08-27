# Sprint 4: Analytics and the Ingestion Pipeline

Three steps, three modules, wired by a fourth that does nothing else.

## Layout

```
ETL_Analysis/
├── __init__.py             makes this a package (needed for `python -m`)
├── Extract.py              the original scratch client, kept as-is
├── extract_fixtures.py     EXTRACT (offline) - reads fixtures/, no network
├── extract_live.py         EXTRACT (live)    - real API, key from env, cached
├── transform.py            TRANSFORM         - pure: data in, data out
├── load.py                 LOAD              - writes to DuckDB
├── load_print.py           LOAD (console)    - the earlier print-only loader
├── symbols.py              symbol universe, validation and quota planning
├── symbols_nse_bse.txt     150 NSE/BSE candidate symbols, editable
├── report.py               the HTML dashboard, charted with Plotly
├── report_svg.py           earlier dependency-free renderer, not wired up
├── analytics_schema.sql    DDL for the analytical store
├── pipeline.py             the fourth module - wiring only
├── fixtures/               three canned API responses, one corrupted
└── tests/                  pytest over the transform
```

## Running it

From the **repository root**, not from inside this folder:

```bash
pip install -r requirements.txt      # plotly, duckdb, requests

python -m ETL_Analysis.pipeline                       # all three -> warehouse.duckdb
python -m ETL_Analysis.pipeline --db my.duckdb        # a different store
python -m ETL_Analysis.pipeline --print               # console instead of DuckDB
python -m ETL_Analysis.pipeline --symbols RELIANCE.NS # one symbol
python -m ETL_Analysis.pipeline --strict              # quarantine everything
python -m ETL_Analysis.pipeline -v                    # verbose logging
python -m ETL_Analysis.pipeline --report out/run.html # where to write the report
python -m ETL_Analysis.pipeline --no-report           # skip the report
python -m ETL_Analysis.pipeline --live                # once a real key exists

# pulling everything the API serves (needs --live)
python -m ETL_Analysis.pipeline --live --list-symbols            # look first
python -m ETL_Analysis.pipeline --live --all-symbols             # pull them all
python -m ETL_Analysis.pipeline --live --all-symbols --exchanges NSE BSE
python -m ETL_Analysis.pipeline --live --all-symbols --limit 25

# the bundled NSE/BSE universe
python -m ETL_Analysis.pipeline --live                    # all 150, no --symbols needed
python -m ETL_Analysis.pipeline --live --validate-symbols # check which ones resolve
python -m ETL_Analysis.pipeline --live --symbol-file mine.txt
```

A **live** run with no `--symbols` pulls the bundled NSE/BSE universe. An
**offline** run with no `--symbols` still uses the three fixture symbols,
because fixtures are all it has.

Every run writes `report.html` (or wherever `--report` points).

`duckdb` is the only dependency for the default path, and `--print` needs none
at all. `extract_live.py` needs `requests`.

Tests, also from the repository root:

```bash
pip install pytest
pytest ETL_Analysis/tests -v
```

## Why extract is split in two

`extract_fixtures.py` and `extract_live.py` expose the same callable:

```python
extract(symbol, start=None, end=None) -> dict
```

so `--live` swaps which one `pipeline.py` binds and **transform and load are
untouched**. The offline one exists because the key currently in circulation is
a dummy; the live one is written to the sprint's requirements so it works the
day a real key lands.

`extract_live.py` reads the key from `FAUXNANCE_API_KEY` and nowhere else,
sends it in the `X-Api-Key` header, never logs it, and caches raw responses to
`.cache/` keyed by symbol and range so re-runs cost nothing against the 2000/day
quota. It caches the **raw** response, not the cleaned frame, because changing
the transform is what you do most and it must not need a fresh pull.

### The four error cases, told apart

| What happened | How you know | What the client does |
|---|---|---|
| Daily quota exhausted | HTTP 429 + `Retry-After` | Stop and say so. Sleeping to midnight is not recovery |
| The request is wrong | Other 4xx (401/404/400) | Fail that symbol, carry on with the rest |
| Nothing reached the service | Connection error / timeout | Retry with growing backoff, give up after 3 |
| Response arrived and is wrong | HTTP 200, bad candle | Not an HTTP problem — the transform decides |

The fourth is deliberately absent from extract: a high below a low is not a
network condition, and handling it there would put cleaning logic in the wrong
module.

## The six defects, and what we do with each

The fixtures README lists six defects in `candles-malformed.json`. They are not
equally defensible, so they are not treated alike. **A defect is repaired only
where the true value can be recovered from evidence. Where a repair would mean
inventing a number, the row is quarantined.**

| # | Defect | Decision | Why |
|---|---|---|---|
| 1 | `2026-07-01` twice, different closes | **Quarantine** | Nothing says which close is right. First is arbitrary, last is arbitrary, averaging invents a price that never traded |
| 2 | `2026-07-02` has no `close` | **Quarantine** | Interpolating charts a price nobody traded at. The API declares interpolation itself via `synthetic` — that is the vendor's call, not ours |
| 3 | `2026-07-06` has `open: "n/a"` | **Quarantine** | Same as 2. The value is absent, not malformed; there is nothing to recover |
| 4 | `2026-07-07` high 168.10 < low 175.85 | **Repair + flag** | The values are transposed: swapping puts both open and close inside the range and lines up with neighbours. Applied *only* when the swap fully resolves the candle |
| 5 | `2026-07-08` volume `-1` | **Repair + flag** | `-1` is a sentinel for unknown, not a count. The same feed uses `null` for that (see the INFY fixture), and the prices on the row are valid |
| 6 | Last candle dated `09/07/2026` | **Repair + flag** | Ambiguous alone; resolved by context — it follows `2026-07-08`, so 9 July continues the sequence and 7 September would leave a two-month hole |

Result on the malformed fixture: **4 rows loaded (3 of them repaired), 3
quarantined**, out of 7 candles in. Run `--strict` and it is 1 loaded,
6 quarantined.

### Nothing is fixed silently

Every repaired row carries `repaired: True` and a `repairs` list naming what
changed and why, and the flag appears in the printed output. A chart can
exclude repaired rows; the review can see each decision was deliberate. The
`--strict` flag turns every repair back into a quarantine, so both behaviours
can be demonstrated.

### Note on defect 4: this is not a red candle

Red vs green is **open vs close**. `high` and `low` are the day's maximum and
minimum regardless of direction, so `high < low` is a contradiction either way.
On this row `close` 173.60 > `open` 172.50, so it is green if anything.

The swap is *plausible*, not *provable* — the alternative story is that one
value was corrupted and the other is fine, in which case swapping produces a
confident wrong number. That is why it is flagged rather than quietly fixed,
and why the swap is refused when it does not fully resolve the candle.

## Two things that look like defects and are not

Both appear in the clean INFY fixture, and the fixtures README confirms the
live API emits both:

- **`volume: null`** — kept, volume stays `None`. A missing volume does not make
  the prices wrong. `turnover` is `None` for that row rather than zero.
- **`synthetic: true`** — kept, and the flag is carried through so a chart can
  mark or exclude it. Discarding it would hide that the vendor interpolated the
  number.

## Nothing is dropped

`rows_kept + rows_quarantined == candles_in`, always, in both modes — asserted
in the test suite. A dropped row is invisible, and a chart drawn over silently
dropped rows is wrong in a way nobody can see. Quarantined rows keep the
original candle attached so a teammate can see exactly what arrived.

## Load: the analytical store

DuckDB, one file on disk. Three tables, defined in `analytics_schema.sql`:

| Table | Grain | Holds |
|---|---|---|
| `daily_price` | one row per symbol per trading day | the analysis rows: cleaned, typed, with derived measures |
| `quarantined_candle` | one row per rejected candle | the dead-letter table, original payload attached |
| `load_run` | one row per symbol per run | the ledger: counts, dates, whether repair was on |
| `run_metric` | one row per metric per symbol per run | the analytical results, 28 measures |

### Why candles are not in FACT_TRADES

`contracts/analytics-schema.sql` is binding, and its `FACT_TRADES` is **one row
per order** — it carries `account_key`, `side`, `status` and `quantity`. A
market candle has none of those: there is no account behind an end-of-day price
and no BUY/SELL on a daily bar. Loading candles into `FACT_TRADES` would corrupt
the grain the contract states and break the Sprint 7 load.

So candles get their own table and the contract's tables are left untouched.
These are **additions, not changes** — nothing is renamed or altered, so no
consumer breaks. `contracts/README.md` says a divergence must be raised rather
than built quietly; this is the raising of it, and it is a decision to defend at
the review.

`dim_date`, `dim_instrument`, `dim_account` and `fact_trades` are loaded in
Sprint 7, when the source becomes the platform's own order flow. `daily_price`
already carries `date_key` in `YYYYMMDD` form and an `exchange` derived by the
rule the contract states, so it can join to `dim_date` and `dim_instrument`
the moment they exist.

### The metrics

`run_metric` is **long format** — one row per metric, not one column per
metric. A new measure needs no `ALTER TABLE`, a report renders whatever it
finds without knowing the metric list in advance, and comparing one measure
across runs is a single `WHERE` rather than a column-by-column diff.

Measures computed (all in `transform.py`, since aggregating and deriving are
the transform's job): first/last/min/max/mean close, period return, average
daily return, daily volatility as the sample standard deviation of returns,
maximum drawdown, best and worst day with dates, largest daily move, average
daily range, up/down/flat day counts, average/max/min volume, total turnover,
and the row-disposition counts.

```sql
-- one measure, every symbol, newest run
SELECT symbol, value FROM run_metric
 WHERE metric = 'volatility_pct'
   AND run_id = (SELECT max(run_id) FROM run_metric)
 ORDER BY value DESC;

-- how a measure moved between runs
SELECT run_id, value FROM run_metric
 WHERE symbol = 'RELIANCE.NS' AND metric = 'period_return_pct'
 ORDER BY run_id;
```

Volatility and drawdown are verified in the test suite against
`statistics.stdev` and a brute-force peak-to-trough search respectively, so a
wrong formula fails rather than being confirmed by its own output.

## Which symbols get pulled

Two cases, and no third:

| You ran | It pulls |
|---|---|
| `--symbols RELIANCE.NS INFY.NS` | exactly those |
| nothing, with `--live` | every symbol in `symbols_nse_bse.txt` (150) |
| nothing, offline | the three fixture symbols, which are all the fixtures have |

```bash
python -m ETL_Analysis.pipeline --list-symbols              # read the file, offline, free
python -m ETL_Analysis.pipeline --live                      # all 150
python -m ETL_Analysis.pipeline --live --symbols INFY.NS
python -m ETL_Analysis.pipeline --live --exchanges NSE      # 125 of them
python -m ETL_Analysis.pipeline --live --limit 25
python -m ETL_Analysis.pipeline --live --symbol-file mine.txt
```

**There is no discovery of any kind.** The API documents no catalogue
endpoint, so the file is simply the answer: you can read it, edit it, and know
exactly what a run will fetch before you start it. A symbol Fauxnance does not
serve returns a 404, which fails that symbol and lets the run carry on — the
same handling every other request error gets.

### The universe file

`symbols_nse_bse.txt` — 150 Indian equity symbols, 125 NSE (`.NS`) and 25 BSE
(`.BO`), one per line with company names as trailing comments. Blank lines and
`#` comments are ignored. Edit it freely; it is a starting universe, not a
fixed one.

These are real listed companies, but nothing in the file has been checked
against Fauxnance. Expect some 404s on the first live run, and prune the file
from what you see.

### Quota

One request per symbol against 2000 per day. A 150-symbol pull is 7.5% of a
day's quota. Before pulling, the pipeline reads `GET /usage` and **refuses to
start a pull it cannot finish** — a half-complete dataset that looks complete
is the worse failure. Narrow with `--exchanges` or `--limit`, or
`--no-quota-check` to override. Cached responses cost nothing.

### A note on scope

The sprint README says to take *"the smallest scope that produces three claims
you can stand behind"*, and SEC3-103 asks you to record the symbol universe
**with the reason for each entry**. A 150-symbol pull has no per-entry
reasoning, so it does not by itself satisfy that story. The useful pattern is
`--list-symbols` to see what is there, then a justified subset via
`--exchanges`, `--limit`, or an explicit `--symbols` list.

## The report

`report.html`, rewritten every run and charted with **Plotly**: a rebased
comparison of every symbol, a data-quality bar, then per symbol a closing-price
chart and a daily volume chart, the measures, and tables of exactly what was
quarantined and repaired.

```bash
pip install plotly
```

Plotly is required. There is no fallback renderer — a report that silently
degrades to something else is one you cannot trust to look the same twice. If
plotly is missing the pipeline says so plainly, and **still loads the data**;
only the report is skipped.

### Offline by default

The sprint requires artefacts that open with no network, so Plotly's
JavaScript is **embedded in the document** — on the first figure only, so the
~3MB bundle appears once rather than once per chart. That makes each report
about 3–4MB.

`--cdn-js` loads Plotly from a CDN instead: far smaller files, but they need a
network to render, which fails the sprint's artefact rule. The footer says
which mode produced the file.

### How it is structured

Every chart is built as a plain figure dict — `{"data": [...], "layout": {...}}`
— by a pure function with no plotly import. Those are unit-tested directly:
trace counts, x/y values, date handling, axis titles, JSON-serialisability.
Plotly is touched only in `_render`, which turns a figure dict into an HTML
fragment. So a chart showing the wrong number is a bug in a tested pure
function, not somewhere inside the rendering.

### Readability

Both axes titled on every chart (`_axis()` takes the title as a required
argument, not an optional one), titles that state the finding rather than
naming the variables ("RELIANCE.NS rose 1.08% between 01 Jul and 14 Jul 2026"),
and a colour-blind-safe palette (Okabe-Ito).

Two things Plotly does better than the earlier hand-built SVG:

- **A real date axis.** A two-day gap is drawn as two days. The old
  categorical axis spaced every point evenly however far apart the dates were.
- **Null volume leaves a gap**, natively. A day the provider reported no volume
  is passed as `null`, not `0` — a missing figure is not a day without trading,
  and a zero bar would say it was. An annotation on the chart explains it.

Repaired rows are drawn as open diamonds on the price chart, so a reader can
see at a glance which points were corrected rather than observed.

On a wide pull the report reorganises itself: a ranked table of **every**
symbol by return leads, the comparison chart shows only the six largest movers
(and says so), and detail sections are capped at the twelve most extreme.
Everything still loads to the store — only the rendering is trimmed.

### Idempotency

The contract requires re-running a load not to double-count. `daily_price` is
merged on its natural key `(symbol, trade_date)`: the loader deletes exactly the
dates it is about to write, then inserts. Deleting by date rather than by symbol
means a narrow re-pull does not destroy history from a wider one.
`quarantined_candle` is replaced per symbol. `load_run` is append-only, because
the ledger is the history of loads rather than the current state.

### Reconciliation

`candles_in = rows_kept + rows_quarantined` is an invariant, checked in SQL
after every run and reported by the pipeline. A non-empty result means a row was
lost between arriving and landing — the failure this whole design exists to make
visible.

### Poking at the store

```bash
duckdb warehouse.duckdb
```

```sql
-- what landed
SELECT symbol, count(*), min(trade_date), max(trade_date)
  FROM daily_price GROUP BY symbol;

-- what did not, and why
SELECT symbol, reason, raw_date, detail FROM quarantined_candle;

-- observed data only, excluding vendor-interpolated and repaired rows
SELECT * FROM daily_price WHERE NOT synthetic AND NOT repaired;

-- the load history
SELECT run_id, symbol, candles_in, rows_kept, rows_repaired, rows_quarantined
  FROM load_run ORDER BY loaded_at DESC;
```

That last filter matters for `claims.md`: a claim resting on repaired or
synthetic rows is a claim resting on numbers nobody observed, and the flags are
there so a chart can exclude them.

## Testing

```bash
pip install pytest
pytest ETL_Analysis/tests -v
```

151 tests. `test_load.py` runs the **real** DDL and the **real** SQL statements
against an in-memory SQLite mirror — DuckDB and SQLite share the `?` placeholder
style and accept the same ANSI DDL here, so statement correctness, column-order
alignment and delete-then-insert idempotency are all covered without requiring
`duckdb` to be installed to run the suite.

What that does **not** prove: DuckDB-specific type behaviour (`DECIMAL`
precision, `TIMESTAMP` handling) and the `duckdb.connect` call itself. Run the
pipeline against a real DuckDB file once and check a few rows to close that gap.

## Still to do

- `claims.md` — three business claims, each naming the chart that supports it
  (the report's chart sections are the artefacts to point at)
- `pyproject.toml` so `pip install -e 'ETL_Analysis[dev]'` works from a clean
  machine (`tests/conftest.py` handles imports until then)
