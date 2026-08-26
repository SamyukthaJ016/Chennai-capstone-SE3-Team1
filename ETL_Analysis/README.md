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
├── load.py                 LOAD              - the only part that writes
├── pipeline.py             the fourth module - wiring only
├── fixtures/               three canned API responses, one corrupted
└── tests/                  pytest over the transform
```

## Running it

From the **repository root**, not from inside this folder:

```bash
python -m ETL_Analysis.pipeline                       # all three symbols
python -m ETL_Analysis.pipeline --symbols RELIANCE.NS # one symbol
python -m ETL_Analysis.pipeline --rows 5              # cap printed rows
python -m ETL_Analysis.pipeline --strict              # quarantine everything
python -m ETL_Analysis.pipeline -v                    # verbose logging
python -m ETL_Analysis.pipeline --live                # once a real key exists
```

No third-party dependencies for the offline path: standard library only.
`extract_live.py` needs `requests`.

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

## Load

Prints to stdout for now. Nothing imports `duckdb`: the print target keeps the
pipeline runnable with no analytical store provisioned. Swapping the destination
is a change to `load.py` only — extract and transform do not know where the data
lands, which is the point of the split.

**On the eventual DuckDB target:** `fact_trades` in
`contracts/analytics-schema.sql` is one row per *order*, keyed on account, side
and status. Candles have no account and no side, so they do **not** belong in
that fact table. Market candles want their own table; `fact_trades` is loaded in
Sprint 7 when the source becomes the platform's own order flow.

## Still to do

- `claims.md` — three business claims, each naming the chart that supports it
- Chart artefacts (plotly, inlined JS so they open with no network)
- `pyproject.toml` so `pip install -e 'ETL_Analysis[dev]'` works from a clean
  machine (`tests/conftest.py` handles imports until then)
