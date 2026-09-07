# Sprint 4: Analytics and the Ingestion Pipeline

Three steps, three modules, wired by a fourth that does nothing else.

## Layout

```
ETL_Analysis/
├── __init__.py             makes this a package (needed for `python -m`)
├── extract_fixtures.py     EXTRACT (offline) - reads fixtures/, no network
├── extract_live.py         EXTRACT (live)    - real API, key from env, cached
├── transform.py            TRANSFORM         - pure: data in, data out
├── load.py                 LOAD              - writes to DuckDB
├── load_print.py           LOAD (console)    - the earlier print-only loader
├── pipeline.py             the fourth module - wiring only
│
├── store.py                READ side of the store - read-only, + the SQL guard
├── charts.py               the dashboard's figures, as pure dicts
├── dashboard.py            the live dashboard (streamlit)
├── claims.py               the claim GENERATORS - questions fixed, answers computed
├── claims.md               THE DELIVERABLE - generated from the store, never edited
│
├── report.py               LEGACY: the one-shot HTML report, still supported
├── report_svg.py           earlier dependency-free renderer, not wired up
│
├── symbols.py              symbol universe, validation and quota planning
├── symbols_nse_bse.txt     150 NSE/BSE candidate symbols, editable
├── analytics_schema.sql    DDL for the analytical store
├── requirements.txt        the dependency set
├── fixtures/               three canned API responses, one corrupted
└── tests/                  438 tests: transform, load, store, charts,
                            claims, dashboard, report and the wiring
```

The pipeline writes the store; the dashboard reads it. Those are the only two
directions, and `store.py` is the only module on the read side -- it opens
DuckDB **read-only**, so nothing a reader does can change what was loaded.

## Running it

From the **repository root** (`Team1/`), not from inside this folder:

```bash
pip install -r ETL_Analysis/requirements.txt

python -m ETL_Analysis.pipeline               # load -> warehouse.duckdb
python -m ETL_Analysis.dashboard              # open the dashboard on it
python -m ETL_Analysis.pipeline --dashboard   # do both, in one command
```

That is the whole loop. **The dashboard reads the store, so it is up to date
the moment a run finishes** -- there is no artefact to regenerate and no step
to remember. Starting the dashboard is covered on its own below.

```bash
python -m ETL_Analysis.pipeline --db my.duckdb        # a different store
python -m ETL_Analysis.pipeline --print               # console instead of DuckDB
python -m ETL_Analysis.pipeline --symbols RELIANCE.NS # one symbol
python -m ETL_Analysis.pipeline --strict              # quarantine everything
python -m ETL_Analysis.pipeline -v                    # verbose logging
python -m ETL_Analysis.pipeline --live                # once a real key exists

# the legacy self-contained HTML report (see "The legacy report" below)
python -m ETL_Analysis.pipeline --legacy-report               # -> report.html
python -m ETL_Analysis.pipeline --legacy-report out/run.html  # somewhere else

# the bundled NSE/BSE universe (needs --live)
python -m ETL_Analysis.pipeline --list-symbols            # look first, free
python -m ETL_Analysis.pipeline --live                    # all 150
python -m ETL_Analysis.pipeline --live --exchanges NSE BSE
python -m ETL_Analysis.pipeline --live --limit 25
python -m ETL_Analysis.pipeline --live --symbol-file mine.txt
```

A **live** run with no `--symbols` pulls the bundled NSE/BSE universe. An
**offline** run with no `--symbols` still uses the three fixture symbols,
because fixtures are all it has.

`duckdb` is the only dependency for the default load path, and `--print` needs
none at all. The dashboard needs `streamlit`, `plotly` and `pandas`;
`extract_live.py` needs `requests`.

Tests, also from the repository root:

```bash
pip install pytest
pytest ETL_Analysis/tests -v
```

## Starting the dashboard

The dashboard is a [streamlit](https://streamlit.io) app. It reads the DuckDB
store, so **load the store once before starting it** — a dashboard over an
empty store has nothing to draw.

```bash
cd Team1                                    # the repository root
pip install -r ETL_Analysis/requirements.txt

python -m ETL_Analysis.pipeline             # 1. load  -> warehouse.duckdb
python -m ETL_Analysis.dashboard            # 2. serve -> http://localhost:8501
```

Streamlit prints the URL and opens your browser at it. Leave it running: the
page reads the store live, so you can run the pipeline again in another
terminal and press **Reload from disk** in the left rail rather than
restarting.

To do both in one command:

```bash
python -m ETL_Analysis.pipeline --dashboard   # load, then serve
```

**Stop it** with `Ctrl+C` in the terminal it is running in.

### Options

```bash
python -m ETL_Analysis.dashboard --db my.duckdb   # a store somewhere else
python -m ETL_Analysis.dashboard --port 8600      # a different port
python -m ETL_Analysis.dashboard --headless       # do not open a browser
```

| Flag | Default | What it does |
|---|---|---|
| `--db PATH` | `warehouse.duckdb` | Which store to read. Relative to the directory you started from. |
| `--port N` | 8501 | Port to serve on. Streamlit's own default when not given. |
| `--headless` | off | Serve without opening a browser — what you want over SSH, or in a container. |

The store can also be switched from inside the app: the **Store** box at the
top of the rail takes a path, and **Reload from disk** re-reads it.

### Running `streamlit run` directly

This works too, and is worth knowing if you want to pass streamlit's own
flags:

```bash
python -m streamlit run ETL_Analysis/dashboard.py -- --db warehouse.duckdb
```

Note the bare `--`: everything after it goes to the app rather than to
streamlit. `dashboard.py` puts the project root on `sys.path` when it is run
as a script, so this resolves whether it is imported as a module or executed
as a file.

**Prefer `python -m ETL_Analysis.dashboard` anyway.** It is the same app, but
it also passes the theme on the command line — surface colours, ink, and the
accent — so the dashboard looks the same whatever directory you start it from
and whatever your own streamlit settings say. Started through bare
`streamlit run`, you get streamlit's stock red accent instead of the palette
in `charts.py`.

### When it does not start

| What you see | What it means |
|---|---|
| `No store at warehouse.duckdb. Run the pipeline first` | The app started but has nothing to read. Run `python -m ETL_Analysis.pipeline`, then reload the page. |
| `Port 8501 is already in use` | A dashboard is already running. Open the URL it printed, or start this one with `--port 8600`. |
| `Charts need plotly, which is not installed` | The page renders and the tables are all there, only the charts are missing. `pip install plotly`. |
| `A pipeline run is holding the store open` | DuckDB allows many readers or one writer, and a load is in progress. It retries by itself; reload once the run finishes. |
| `Already inside a dashboard process; refusing to start another` | You ran the launcher from inside the app's own process. Open the URL streamlit already printed. |

### A note on who can reach it

Streamlit binds to all interfaces by default, so it prints a **Network URL**
and an **External URL** alongside the local one. Those reach the app from your
LAN and, if anything forwards the port, from outside it — and there is no
authentication in front of the SQL console. On a shared or untrusted network,
bind it to your own machine only:

```bash
python -m streamlit run ETL_Analysis/dashboard.py \
    --server.address 127.0.0.1 -- --db warehouse.duckdb
```

The data here is invented and the store is local, so this is a habit rather
than an emergency — but the console does run arbitrary SQL against whatever
store it is pointed at.

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

The dashboard's SQL console runs all of these, with the schema beside it. If
you would rather have a terminal:

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

## The dashboard

`python -m ETL_Analysis.dashboard` opens a six-tab streamlit app over
`warehouse.duckdb`. It replaces the HTML report as the thing you actually look
at after a run.

| Tab | What is on it |
|---|---|
| **Overview** | Stat strip, every symbol rebased to 100 on one axis, a ranked table of all of them, and the disposition of every candle received |
| **Claims** | The three business claims, each with its supporting chart and every figure re-checked against the store |
| **Instrument** | One symbol: price with repaired points marked, daily volume, the spread of its daily returns, all 28 measures, and the rows they were computed from |
| **Data quality** | Reconciliation, why rows were rejected, every quarantined candle, every repair and what it changed |
| **Runs** | The append-only load ledger, one run inspected in detail, and one measure tracked across runs |
| **SQL console** | A read-only query box over the store, with the schema beside it and eight worked examples |

Every table has a CSV download. Every chart has the table it was drawn from
next to it.

### Why a dashboard and not a report

The report described **the run that wrote it**: the objects transform had just
produced, for the symbols that run happened to pull. The dashboard describes
**the store**: everything ever loaded, filtered however you like, including
runs from last week.

That difference is why it updates on every run without anything regenerating a
file. Reads are cached against `store.store_stamp` — the store's path, mtime
and size — so a pipeline run changes the file, the next page render misses the
cache and re-reads, and nothing else invalidates anything. No polling, no
build step.

### What the cache key does not solve

The key also includes the filter selection, and there are 2^144 symbol
selections. Unbounded, every distinct one would retain its own copy of the rows
for the life of the process — a full-universe slice pickles to **6.4 MB**, so a
few filter changes is tens of megabytes held for good. The slice cache is
therefore capped at four entries: re-reading the store takes about a second,
and holding twenty of them does not.

The stamp is also only `(path, mtime, size)`. A write that changes neither —
same size, inside one filesystem timestamp tick — would go unnoticed until
somebody pressed Reload. A five-minute TTL bounds how long that can last
without anyone having to know it is a possibility.

**Reload from disk** clears this app's readers by name rather than calling
`st.cache_data.clear()`, which would empty every cached function in the
process. The same `refresh()` runs after a pipeline started from the rail, so
the page is showing the rows that run just wrote.

### The SQL console

The panels answer the questions we thought of. The console is for the rest.

It opens the store **read-only**, so nothing typed into it can change what the
pipeline loaded, and `store.check_query` rejects anything that is not a single
read statement before the engine ever sees it. That second check is not
redundant: read-only stops a write, but it does not stop `ATTACH`, `INSTALL`,
`COPY ... TO` or `EXPORT`, which reach outside the file. It also turns a driver
exception into a sentence naming what was wrong.

```sql
-- the reconciliation invariant, checkable by hand
SELECT run_id, symbol, candles_in, rows_kept, rows_quarantined
  FROM load_run
 WHERE candles_in <> rows_kept + rows_quarantined;

-- observed rows only: neither repaired by us nor interpolated by the vendor
SELECT symbol, trade_date, "close", volume
  FROM daily_price
 WHERE NOT synthetic AND NOT repaired;
```

Results are capped at 2000 rows, and the page says when it truncated rather
than quietly showing you a prefix.

### The filter rail, and why the measures are recomputed

The rail on the left scopes every tab at once: venue, symbols, date window, and
two provenance switches -- *exclude repaired rows* and *exclude
vendor-interpolated rows*.

Those switches matter for `claims.md`. A claim resting on repaired or synthetic
rows is a claim resting on numbers nobody observed, and the flags exist so a
chart can exclude them.

When they are on, **the measures are recomputed over what is left** rather than
read back from `run_metric`. A stored metric describes the whole symbol as it
was loaded, and showing it beside a filtered chart would put two different
periods on one screen and label them the same. The recomputation goes through
`transform.summarise_rows`, which is the same code path `transform()` itself
uses -- so a number on the dashboard is one the transform tests already cover,
and `test_store.py` asserts the round trip symbol by symbol.

### DuckDB is one writer or many readers

Not both. A dashboard that held the file open would block the next pipeline run
from writing to it, which would make "updates on every run" false in the most
annoying possible way. So connections are opened per read and closed
immediately, never held across a page render.

If the store is locked anyway -- you refreshed while a run was mid-load --
`store.connect` copies the file and reads the copy, saying so on the page. On
Windows, where the OS refuses to read a file DuckDB holds open at all, it
retries briefly and then tells you a run is probably in progress. What it never
does is show a traceback or hang.

### The charts

`charts.py` builds every figure as a plain `{"data": [...], "layout": {...}}`
dict, with no plotting library imported. Those are unit-tested directly: trace
counts, x/y values, date handling, axis titles, JSON-serialisability. Plotly is
touched only where the app hands a figure to `st.plotly_chart`. So a chart
showing the wrong number is a bug in a tested pure function.

**Both axes are titled on every chart** -- `charts.axis()` takes the title as a
required argument, not an optional one -- and titles state a finding rather than
naming the variables.

**No chart has two y-axes.** Price and volume are separate figures. Two scales
on one plot invent a correlation by choosing where to align them, and the reader
cannot see that choice. This is asserted, not merely intended.

**A missing volume is null, not zero.** A day the provider reported no volume
leaves a gap, and an annotation on the chart says so. A zero bar would claim a
day with no trading.

**Repaired points are open diamonds.** The shape carries it, not the colour, so
it survives a greyscale print.

#### The palette is validated, not chosen

Okabe-Ito, which stays distinguishable under the common forms of colour vision
deficiency. The **order** is the part that does the work: colours are assigned
to series in order, so adjacent slots are the pair a reader most often has to
tell apart.

The previous order put reddish-purple next to bluish-green, whose separation
under deuteranopia is dE 7.6 -- inside the band that is only defensible with a
second, non-colour encoding. Moving orange between them lifts the worst adjacent
pair to dE 9.6 deuteran and 20.0 normal-vision, clear of the 8 target, using the
same six hexes.

Three of the six sit below 3:1 contrast against the page. That is inherent to
these hues, and it is met the way the rule allows: every chart has a table
beside it carrying the same numbers, and series are named in a legend rather
than identified by colour alone. `test_charts.py` pins the order and the
specific pair that must not be adjacent, so a tidy-up cannot quietly undo it.

Loaded clean / loaded after repair / quarantined are **states**, not identities,
so they take a reserved status palette rather than three series slots -- and
each one always carries its label.

## Candle interval

The pipeline requests a granularity, and the store keeps it as part of the
grain.

```bash
python -m ETL_Analysis.pipeline --interval 1wk           # ask for weekly
python -m ETL_Analysis.pipeline --interval 1mo --live
```

The dashboard's rail carries the same control: **Load more data** takes an
interval, a symbol list and a live/offline switch, and runs the pipeline
without leaving the page. When the store holds more than one granularity, a
**Candle interval** selector appears above the filters and every tab shows one
interval at a time.

### It is part of the primary key, and that matters

`daily_price` is keyed on `(symbol, trade_date, interval)`. Keying on
`(symbol, trade_date)` alone cannot hold two granularities: a weekly candle and
a daily candle can carry the same symbol and the same date and are **not the
same fact**, so a weekly pull would either collide with the daily rows or
silently replace them — and a chart would then draw two granularities as one
series.

Stores written before the interval existed are migrated on the next run.
`CREATE TABLE IF NOT EXISTS` cannot add a column and no dialect can extend a
primary key in place, so `load.migrate_interval_into_the_grain` rebuilds the
table inside a transaction and stamps the existing rows `1d` — which is all the
pipeline could produce until now. It is idempotent, and it logs what it did.

### The rows say what arrived, not what was asked for

The transform reads the granularity off the response rather than off the
request. Asking the offline client for `1wk` gets you the fixtures, which are
daily, and the rows say `1d` — the request is recorded in `meta` and the data
is labelled honestly. A live API that declines an interval is visible in the
store for the same reason, rather than being relabelled to match the ask.

## The claims

`claims.md` is the sprint deliverable, and it is **generated, not written**.
Every figure in it is computed from the store; nothing is typed in. The
dashboard's **Claims** tab renders the same claims from the same functions, so
the document and the page cannot describe different data.

```bash
python -m ETL_Analysis.claims                  # regenerate claims.md
python -m ETL_Analysis.pipeline --claims       # ...as part of a run
python -m ETL_Analysis.claims --db my.duckdb --out somewhere/claims.md
```

### What is fixed, and what is computed

The **question** is fixed, because choosing what is worth asking is judgement:

| # | The question | Answered by |
|---|---|---|
| 1 | How much did stock selection matter, and when? | decile spread per quarter |
| 2 | How far did the recovery actually reach? | median return against breadth |
| 3 | Did the volatility regime come back down? | daily volatility either side of the selloff |

Everything else is derived from the data:

- **The period** — read off the store's own date bounds.
- **The universe** — one listing per company, with the full period, at the
  store's main interval. No exchange, symbol count or interval is named.
- **The pivot** — the selloff is *found*: the quarter with the worst median
  return. The rebound is the best quarter after it. Move the crash in the data
  and the claims move with it, which `test_claims.py` asserts by generating
  over two stores whose crash sits in different quarters and requiring the
  sentences to differ.
- **Every number in the sentence**, including the direction words: a store
  where volatility fell back produces "the selloff did not leave a lasting
  change" rather than the opposite.

### A claim the data cannot support is reported, not invented

A three-symbol fixture store cannot support a claim about a market. Generators
return `available = False` with the reason instead of emitting a confident
sentence about twelve rows:

```
unsupported - How far the recovery actually reached: Only 1 symbol has the
full period. A claim about the market needs at least 20 for a distribution to
mean anything.
```

`claims.md` prints those under *Claims this store cannot support*, and the
dashboard warns on the tab. A thin store looks visibly thin rather than looking
like there was nothing worth saying.

### No claim rests on a number nobody traded at

**Every** generator reads observed rows only — `NOT synthetic` — so none is
argued from a candle the vendor interpolated. About 4% of NSE rows and 12% of
BSE rows are interpolated, and on a dual-listed name those rows sit a median
3.8% from the other venue's print for the same day.

The universe also keeps **one listing per company**. `RELIANCE.NS` and
`RELIANCE.BO` are one business, and counting both would weight it twice in
every median and decile. The listing with more observed rows wins — which is
the one with less of the vendor's filler in it.

Both rules are asserted on every query rather than remembered:

```python
def test_no_claim_query_reads_a_vendor_interpolated_row():
    for name in CLAIM_QUERIES:
        assert "NOT d.synthetic" in getattr(C, name)
```

The interpolation rate is still measured — it is the evidence for the exclusion
— and lives on the **Data quality** tab under *Why every claim excludes
vendor-interpolated rows*.

### Quarters are year-aware, and that was a bug

The per-quarter figures key on **year and quarter**, not quarter alone. Keying
on the quarter alone is fine for a single year and silently wrong past it: this
store runs 26 Aug 2025 to 27 Aug 2026, so September 2025 and September 2026
were being drawn as one line called "Q3" — joining two points a year apart and
inventing the move between them.

`charts.split_by_quarter` buckets on `(year, quarter)` and returns them
chronologically, printing the year only when the rows actually span more than
one. A single-year pull still reads "Q1", not "2026 Q1".

## The legacy report

`report.py` still works and is still supported. It writes one self-contained
HTML file with the plotly bundle embedded, which opens on a machine with no
network:

```bash
python -m ETL_Analysis.pipeline --legacy-report
python -m ETL_Analysis.pipeline --legacy-report out/run.html
python -m ETL_Analysis.pipeline --legacy-report --cdn-js   # smaller, needs a network
```

It is kept because **a served dashboard is not a committed artefact**. The
sprint asks for chart artefacts that open with no network and can be pointed at
from `claims.md`; a streamlit app cannot be committed, and cannot be assessed
when nobody is running it. The dashboard is what you work with; the report is
what you hand in.

It is no longer written by default. The dashboard needs no artefact, and writing
a 3.6MB file on every run to render something nobody opened is waste.

## Testing

```bash
pip install pytest
pytest ETL_Analysis/tests -v
```

**438 tests**, across nine modules:

| File | Covers |
|---|---|
| `test_transform.py` | the six defects, both modes, and that nothing is dropped |
| `test_report.py` | the measures against independent computations, and the legacy report |
| `test_symbols.py` | the universe file, the quota arithmetic, and a wide pull |
| `test_load.py` | the real DDL and the real SQL, against an in-memory SQLite mirror |
| `test_store.py` | the SQL guard, the record shaping, and the DuckDB round trip |
| `test_charts.py` | every figure builder, and the readability rules |
| `test_claims.py` | that claims are derived from the data, refuse to overreach, and render `claims.md` |
| `test_dashboard.py` | the page helpers, and the real app driven end to end |
| `test_pipeline.py` | the wiring: injection, failure handling, flags, exit codes |

Nothing touches the network.

### It runs on a machine with none of the optional dependencies

318 of the 438 pass with `duckdb`, `streamlit`, `plotly` and `pandas` all
absent. The tests that genuinely need a database **skip**, and they skip from a
fixture rather than at module level, so the pure half of each file keeps
running:

```
pytest ETL_Analysis/tests            # 438 passed
# without plotly                     # 438 passed  -- the page degrades
# without duckdb                     # 318 passed, 92 skipped
# without streamlit                  # 410 passed, 28 skipped
```

Note the plotly row. The dashboard does not *fail* without plotly, it loses its
charts: `st.plotly_chart` reaches for `plotly.tools`, so a missing plotly used
to surface as a traceback in the middle of the page. The page now checks first,
says what to install, and renders everything else -- which is worth having,
because every chart on it has a table beside it carrying the same numbers.

### What the SQLite mirror proves, and what it does not

`test_load.py` runs the real DDL and the real INSERT/DELETE statements against
an in-memory SQLite database — DuckDB and SQLite share the `?` placeholder
style and accept the same ANSI DDL here — so statement correctness, column-order
alignment and delete-then-insert idempotency are covered without needing DuckDB
installed.

It cannot prove DuckDB-specific type behaviour. That gap is now closed by
`test_store.py`, which loads a **real** DuckDB file with the real loader and
reads it back: `DECIMAL` arriving as `Decimal` rather than `float` is a bug the
mirror cannot see and a chart cannot survive, and it is asserted directly.

### The round trip is the load-bearing test

`test_the_store_gives_back_the_measures_the_pipeline_put_in` runs the pipeline,
reads the store back through `store.build_results`, and compares measure by
measure and row by row against what `transform` produced in memory.

If that ever drifts, a chart drawn from the store disagrees with the run that
produced it and neither one is obviously the wrong one. It is the reason the
dashboard can be trusted to be showing the pipeline's numbers rather than its
own.

### The suite used to hang, and why

Before this sprint's fixes, `pytest ETL_Analysis/tests` never finished on a
machine with plotly installed. Three separate causes, all worth knowing:

1. **`assert "cdn.plot.ly" not in document`.** Plotly's embedded bundle names
   its own CDN in a licence comment, so the assertion was false in a file that
   fetches nothing. The question has to be asked of the script tags, not of the
   text: `HtmlDoc.script_srcs()` returns the URLs the page would actually
   fetch, and an offline artefact returns an empty list.

2. **A failing `in` assertion over a 3.6MB string.** pytest builds that failure
   message by running difflib over the whole document. Measured on this suite:
   **3 hours 57 minutes** to report six failures, essentially all of it inside
   the failure-message machinery rather than in the tests. So a stale assertion
   presented as a hung suite rather than as a red test. Every assertion against
   a rendered report now goes through the `html` fixture, which asserts on
   short derived values — the same suite now runs in 25 seconds.

3. **Tests written against the stub, not the library.** `conftest.py` stubs
   plotly when it is absent, and the stub used to emit a marker only it
   produced. Assertions on that marker passed without plotly and failed with
   it. The stub now imitates plotly's own output shape — the bundle banner, a
   `src=`-bearing script tag in CDN mode — so an assertion means the same thing
   either way.

Three more tests were reading `data[0]` from the per-symbol figures, which
became a stale assumption when those charts were split into one trace per
calendar quarter: `data[0]` is Q1, and the fixtures are all July. They now
aggregate across the four buckets, and a new test pins the four-bucket
structure so the same regression cannot recur silently.

## Still to do

- `pyproject.toml` so `pip install -e 'ETL_Analysis[dev]'` works from a clean
  machine (`tests/conftest.py` handles imports until then)
