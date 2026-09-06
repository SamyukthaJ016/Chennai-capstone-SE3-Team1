# Business claims

<!-- GENERATED FILE. Do not edit by hand: every figure below is
     computed from the store. Regenerate with
         python -m ETL_Analysis.claims
     or as part of a run with
         python -m ETL_Analysis.pipeline --claims -->

Generated 06 September 2026, 14:03 from `warehouse.duckdb`.

Each claim below names a subject, a magnitude, a direction and a period, and each can be checked -- and disagreed with -- against the store it came from. None of the numbers is typed: the questions are fixed, the answers are computed, so this document and the dashboard's Claims tab cannot drift apart.

**What every claim excludes.** Observed rows only -- `NOT synthetic` -- so no claim is argued from a candle the vendor interpolated. One listing per company, so a dual-listed name is not weighted twice. And only symbols with the full period, so a symbol that joined the universe late cannot tilt a quarter it was absent for. The interpolation rate itself is a data-quality fact and lives on the dashboard's Data quality tab.

Prices come from the Fauxnance API, are invented by the vendor, and are not for investment use. The reasoning is what generalises.

---

## Claim 1 -- How much stock selection mattered, and when

> The 2026 Q1 selloff moved the market as a block: 83% of names fell, and even the best decile managed only +5.38%. The 2026 Q2 rebound did not simply reverse it — it spread the market out to 35.58 points between the top and bottom decile, against 32.24 in the selloff, the widest of the 5 quarters on record. Which names you held mattered far more on the way back up than on the way down.

**Period.** 26 Aug 2025 to 27 Aug 2026, 122 symbols with the full period.

**Chart that supports it.** Claims tab, 'How far apart the winners and losers finished'.

| Measure | Figure |
|---|---:|
| Top-minus-bottom decile spread, 2026 Q1 | 32.24 pts |
| Top-minus-bottom decile spread, 2026 Q2 | 35.58 pts |
| Best decile, 2026 Q1 | +5.38% |
| Worst decile, 2026 Q1 | -26.85% |
| Best decile, 2026 Q2 | +29.23% |

Every quarter in the store, on the same basis:

| Quarter | Median | Advancing | Bottom decile | Top decile | Spread | Daily volatility |
|---|---:|---:|---:|---:|---:|---:|
| 2025 Q3 | +0.58% | 56.6% | -5.58% | +11.00% | 16.58 | 1.228% |
| 2025 Q4 | +3.80% | 64.8% | -8.60% | +19.60% | 28.21 | 1.272% |
| 2026 Q1 | -14.52% | 17.2% | -26.85% | +5.38% | 32.24 | 2.002% |
| 2026 Q2 | +7.65% | 73.8% | -6.36% | +29.23% | 35.58 | 1.814% |
| 2026 Q3 | +2.51% | 58.2% | -10.11% | +16.09% | 26.20 | 1.484% |

**The decision it drives.** Budget risk differently for the two regimes. In 2026 Q1 the bottom decile fell -26.85% while the top decile managed +5.38%, so diversification bought little and hedging the market was the defence that worked. In 2026 Q2 the gap between a good pick and a bad one was 35.58 points, which is where selection rather than exposure decided the quarter.

**Why a developer should care.** Deciles need the whole distribution, not a summary: this measure is impossible against a pre-aggregated index feed and is one `quantile_cont` away against one row per symbol per day, which is why the store keeps the grain it does. The quarters are keyed on year AND quarter -- this store spans more than one calendar year, and bucketing on the quarter alone would average two regimes into one number.

**What would have to be true for this to be wrong.** The 2026 Q1 spread were as wide as 2026 Q2's, which would mean the selloff discriminated between names as much as the recovery did. It would also weaken if the deciles were set by a handful of illiquid names rather than the body of the universe -- a decile of 122 symbols is about 12 names.

---

## Claim 2 -- How far the recovery actually reached

> The median name fell 14.52% through 2026 Q1, with 83% of the universe falling. It now sits -0.59% against its pre-selloff close — but only 55 of 122 names (45.1%) are actually back above it. The typical stock looks repaired; most stocks are not.

**Period.** Selloff measured over 2026 Q1; recovery measured to 27 Aug 2026 against each name's own close before it.

**Chart that supports it.** Claims tab, 'How far the recovery actually reached'.

| Measure | Figure |
|---|---:|
| Median return through 2026 Q1 | -14.52% |
| Share of names advancing in 2026 Q1 | +17.20% |
| Median name now, against its pre-selloff close | -0.59% |
| Share of names back at or above that close | +45.10% |

Every quarter in the store, on the same basis:

| Quarter | Median | Advancing | Bottom decile | Top decile | Spread | Daily volatility |
|---|---:|---:|---:|---:|---:|---:|
| 2025 Q3 | +0.58% | 56.6% | -5.58% | +11.00% | 16.58 | 1.228% |
| 2025 Q4 | +3.80% | 64.8% | -8.60% | +19.60% | 28.21 | 1.272% |
| 2026 Q1 | -14.52% | 17.2% | -26.85% | +5.38% | 32.24 | 2.002% |
| 2026 Q2 | +7.65% | 73.8% | -6.36% | +29.23% | 35.58 | 1.814% |
| 2026 Q3 | +2.51% | 58.2% | -10.11% | +16.09% | 26.20 | 1.484% |

**The decision it drives.** Do not read the median's round trip as the market having healed: 54.9% of names are still below where they started. A book built to match a benchmark is carrying them, so the recovery is concentrated and what reverses it would be too. Check holdings individually against their pre-selloff close before treating the drawdown as closed.

**Why a developer should care.** A median is not a market. This claim exists only because the store keeps one row per symbol per day rather than a pre-aggregated index, so breadth -- how many names, not how much -- is a GROUP BY away. The universe is pinned to symbols with the full period for the same reason: pooling in symbols that appear late would change what 'the market' meant between one quarter and the next.

**What would have to be true for this to be wrong.** The count of recovered names moved towards the median's own recovery. Roughly half the universe back above its pre-selloff close would make the median representative again. It also assumes these 122 names stand in fairly for the market, which a wider pull would settle.

---

## Claim 3 -- Whether the volatility regime came back down

> Median daily volatility rose from 1.291% before 2026 Q1 to 1.685% after it, a +30.5% change that has not come back down 2 quarter(s) later. A position sized on the earlier data is carrying about 30% more daily risk than it was sized for.

**Period.** Before: up to 2026-01-01. After: from 2026-04-01. The selloff quarter itself is excluded from both sides, so the comparison is calm against calm rather than being dominated by the event.

**Chart that supports it.** Claims tab, 'Volatility by quarter'.

| Measure | Figure |
|---|---:|
| Median daily volatility before 2026 Q1 | +1.29% |
| Median daily volatility after 2026 Q1 | +1.69% |
| Change | +30.50% |

Every quarter in the store, on the same basis:

| Quarter | Median | Advancing | Bottom decile | Top decile | Spread | Daily volatility |
|---|---:|---:|---:|---:|---:|---:|
| 2025 Q3 | +0.58% | 56.6% | -5.58% | +11.00% | 16.58 | 1.228% |
| 2025 Q4 | +3.80% | 64.8% | -8.60% | +19.60% | 28.21 | 1.272% |
| 2026 Q1 | -14.52% | 17.2% | -26.85% | +5.38% | 32.24 | 2.002% |
| 2026 Q2 | +7.65% | 73.8% | -6.36% | +29.23% | 35.58 | 1.814% |
| 2026 Q3 | +2.51% | 58.2% | -10.11% | +16.09% | 26.20 | 1.484% |

**The decision it drives.** Re-calibrate position sizes and stop distances on the later data. A limit set from the earlier window is roughly 30% too loose, so the same nominal position carries materially more daily risk than when it was sized. Prices coming back is not the same event as risk coming back.

**Why a developer should care.** Volatility here is the sample standard deviation of daily returns, computed in `transform._stdev` and checked against `statistics.stdev` in the suite, so a wrong formula fails rather than being confirmed by its own output. It is quoted per day rather than annualised: annualising a window this short would invent a precision the data does not support.

**What would have to be true for this to be wrong.** Median daily volatility returned to the 1.291% band of the earlier window, which would make this a spike rather than a regime change. It would also weaken if the rise were concentrated in a few names rather than the median -- the median is used precisely because outliers cannot move it.

---

## Note on the entry point

The pipeline is a **module with a `__main__` block**, not a console script:

```bash
python -m ETL_Analysis.pipeline               # extract -> transform -> load
python -m ETL_Analysis.pipeline --claims      # ...and regenerate this file
python -m ETL_Analysis.pipeline --dashboard   # ...and open the dashboard
python -m ETL_Analysis.dashboard              # open the dashboard on its own
python -m ETL_Analysis.claims                 # regenerate this file alone
```

`ETL_Analysis/__init__.py` makes the folder a package so `python -m` resolves; `pipeline.py` ends in `if __name__ == "__main__": sys.exit(main())`. There is no `pyproject.toml` yet, so there is no installed console script to declare -- that is the remaining packaging item in `README.md`.
