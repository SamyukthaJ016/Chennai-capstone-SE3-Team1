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
├── analytics_schema.sql    DDL for the analytical store
├── pipeline.py             the fourth module - wiring only
├── fixtures/               three canned API responses, one corrupted
└── tests/                  pytest over the transform
```

## Running it

From the **repository root**, not from inside this folder:

```bash
pip install duckdb

python -m ETL_Analysis.pipeline                       # all three -> warehouse.duckdb
python -m ETL_Analysis.pipeline --db my.duckdb        # a different store
python -m ETL_Analysis.pipeline --print               # console instead of DuckDB
python -m ETL_Analysis.pipeline --symbols RELIANCE.NS # one symbol
python -m ETL_Analysis.pipeline --strict              # quarantine everything
python -m ETL_Analysis.pipeline -v                    # verbose logging
python -m ETL_Analysis.pipeline --live                # once a real key exists
```

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

### Accesing DuckDb

run 
pip install duckdb
winget install duckdb.cli
duckdb -ui warehouse.duckdb

## Testing

```bash
pip install pytest
pytest ETL_Analysis/tests -v
```

65 tests. `test_load.py` runs the **real** DDL and the **real** SQL statements
against an in-memory SQLite mirror — DuckDB and SQLite share the `?` placeholder
style and accept the same ANSI DDL here, so statement correctness, column-order
alignment and delete-then-insert idempotency are all covered without requiring
`duckdb` to be installed to run the suite.

What that does **not** prove: DuckDB-specific type behaviour (`DECIMAL`
precision, `TIMESTAMP` handling) and the `duckdb.connect` call itself. Run the
pipeline against a real DuckDB file once and check a few rows to close that gap.

## Still to do

- `claims.md` — three business claims, each naming the chart that supports it
- Chart artefacts (plotly, inlined JS so they open with no network)
- `pyproject.toml` so `pip install -e 'ETL_Analysis[dev]'` works from a clean
  machine (`tests/conftest.py` handles imports until then)
