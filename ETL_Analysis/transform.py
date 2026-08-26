"""Transform: data in, data out.

Opens no socket, reads no environment variable, writes nowhere. Everything it
needs arrives as an argument and everything it produces is returned. That is
what makes it the only part of the pipeline testable without a network.

REPAIR OR QUARANTINE
--------------------
The six defects are not equally defensible, so they are not treated alike. A
defect is repaired only where the true value can be RECOVERED from evidence.
Where a repair would mean INVENTING a number, the row is quarantined instead.

Every repaired row carries `repaired: True` and a `repairs` list naming what
was changed and why. Nothing is fixed silently: a chart can exclude repaired
rows, and the review can see each decision was deliberate.

Every rejected row is QUARANTINED, never dropped: it is returned in
`quarantined` with the reason and the original candle attached. A dropped row
is invisible, and a chart drawn over silently-dropped rows is wrong in a way
nobody can see. Counts always reconcile: kept + quarantined = candles in.

Nothing here raises on a bad row. Raising would abandon the good rows in the
same payload, and one corrupt candle in July should not cost you the other
eight.

THE SIX DEFECTS AND THE DECISION ON EACH
----------------------------------------
1. duplicate date, two different closes  -> QUARANTINE (DUPLICATE_DATE)
   Nothing in the payload says which close is right. First is arbitrary, last
   is arbitrary, averaging invents a price that never traded. Needs the vendor.

2. missing `close`                       -> QUARANTINE (MISSING_FIELD)
   Interpolating from neighbours would chart a price nobody traded at. Note
   the API already declares interpolation with `synthetic: true`, which says
   the vendor considers that their call to make, not ours.

3. "n/a" where a number belongs          -> QUARANTINE (NOT_A_NUMBER)
   Same reasoning as 2. The value is absent, not malformed; there is nothing
   to recover.

4. high below low                        -> REPAIR, flagged (repair_high_low)
   Mechanically the two values look transposed: swapping them puts both open
   and close inside the range and lines the row up with its neighbours. But
   plausible is not provable -- the alternative story is that ONE value was
   corrupted and the other is fine, in which case swapping produces a
   confident wrong number. So the swap is applied ONLY when it fully resolves
   the candle, and the row is flagged so downstream can exclude it. If the
   swap does not resolve it, the row is quarantined.

   Note: this is not a red candle. Red vs green is open vs close. `high` and
   `low` are the day's max and min regardless of direction, so high < low is a
   contradiction either way. (On this row close 173.60 > open 172.50, so it is
   green if anything.)

5. negative volume (-1)                  -> REPAIR to None (repair_volume)
   `-1` is a sentinel for "unknown", not a real count. The evidence is inside
   the same feed: the INFY fixture expresses unknown volume as `null`, and
   null-volume rows are already kept. So -1 -> None is consistent with how the
   API behaves elsewhere, and the prices on the row are all valid.

6. `09/07/2026`, not ISO                 -> REPAIR to 2026-07-09 (repair_date)
   Ambiguous in isolation (9 July DD/MM, or 7 September MM/DD). Resolved by
   context: it is a BSE symbol, and the preceding candle is 2026-07-08, so
   9 July continues the sequence while 7 September leaves a two-month hole.
   The assumption is hard-coded as DAYFIRST below and asserted in a test, so
   it cannot drift silently.

TWO THINGS THAT LOOK LIKE DEFECTS AND ARE NOT
---------------------------------------------
  - `volume: null`     -> kept, volume stays None. A missing volume does not
                          make the prices wrong.
  - `synthetic: true`  -> kept, flag carried through so a chart can mark or
                          exclude it. Discarding it would hide that the number
                          was interpolated by the vendor.

Pass `repair=False` to turn every repair back into a quarantine. The strict
mode is what you run if the review prefers it, and the tests cover both.
"""

from __future__ import annotations

from datetime import date, datetime

# Quarantine reason codes. Stable strings, so a test can assert on them.
DUPLICATE_DATE = "DUPLICATE_DATE"
MISSING_FIELD = "MISSING_FIELD"
NOT_A_NUMBER = "NOT_A_NUMBER"
HIGH_BELOW_LOW = "HIGH_BELOW_LOW"
NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
BAD_DATE_FORMAT = "BAD_DATE_FORMAT"
NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"

# Repair codes, recorded on the row in `repairs`.
REPAIR_HIGH_LOW = "repair_high_low"
REPAIR_VOLUME = "repair_volume"
REPAIR_DATE = "repair_date"

REQUIRED_PRICE_FIELDS = ("open", "high", "low", "close")

# Defect 6: the non-ISO date convention this feed is assumed to use.
# BSE symbol, and the row follows 2026-07-08, so DD/MM/YYYY. Asserted in a
# test so the assumption cannot drift silently.
DAYFIRST = True
NON_ISO_DATE_FORMAT = "%d/%m/%Y" if DAYFIRST else "%m/%d/%Y"

# Volume values the feed uses to mean "unknown" rather than a real count.
VOLUME_SENTINELS = (-1,)


def _parse_iso_date(value) -> date | None:
    """Return a date for a strict ISO `YYYY-MM-DD` string, else None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_non_iso_date(value) -> date | None:
    """Defect 6. Parse `09/07/2026` under the DAYFIRST assumption above."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, NON_ISO_DATE_FORMAT).date()
    except ValueError:
        return None


def _as_number(value) -> float | None:
    """Return a float for a genuine number, else None.

    Booleans are rejected: `True` is numerically 1 in Python, and a price of
    True is a defect, not a price.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _quarantine(rows_out, symbol, candle, reason, detail):
    rows_out.append(
        {"symbol": symbol, "reason": reason, "detail": detail, "candle": candle}
    )


def transform(payload: dict, repair: bool = True) -> dict:
    """Clean one raw candles envelope.

    Args:
        payload: a raw `CandlesResponse` envelope, as extract returns it.
        repair:  when True (default), defects 4, 5 and 6 are repaired and
                 flagged. When False, every defect is quarantined instead.

    Returns:
        {
          "symbol", "currency", "interval",
          "rows":        [clean candle dicts, sorted by date],
          "quarantined": [{"symbol", "reason", "detail", "candle"}],
          "summary":     {counts, repair counts, derived aggregates},
        }
    """
    data = payload.get("data") or {}
    meta = payload.get("meta") or {}
    symbol = data.get("symbol") or meta.get("symbol") or "UNKNOWN"
    currency = data.get("currency")
    interval = data.get("interval")
    candles = data.get("candles") or []

    rows: list[dict] = []
    quarantined: list[dict] = []
    seen_dates: set[date] = set()

    for candle in candles:
        if not isinstance(candle, dict):
            _quarantine(quarantined, symbol, candle, MISSING_FIELD,
                        "candle is not an object")
            continue

        repairs: list[dict] = []

        # --- date -------------------------------------------------------
        raw_date = candle.get("date")
        parsed_date = _parse_iso_date(raw_date)

        if parsed_date is None:
            # Defect 6: not ISO. Repairable under a stated convention.
            recovered = _parse_non_iso_date(raw_date) if repair else None
            if recovered is None:
                _quarantine(quarantined, symbol, candle, BAD_DATE_FORMAT,
                            f"date {raw_date!r} is not ISO YYYY-MM-DD")
                continue
            parsed_date = recovered
            repairs.append({
                "code": REPAIR_DATE,
                "detail": f"{raw_date!r} read as {parsed_date.isoformat()} "
                          f"({'DD/MM' if DAYFIRST else 'MM/DD'} assumed)",
            })

        # Defect 1: same date twice. Not repairable -- there is no evidence
        # for which close is correct, so the first is kept and the later one
        # is quarantined rather than silently overwriting.
        if parsed_date in seen_dates:
            _quarantine(quarantined, symbol, candle, DUPLICATE_DATE,
                        f"{parsed_date.isoformat()} already seen; "
                        f"first occurrence kept")
            continue

        # --- required prices present ------------------------------------
        # Defect 2: a required price field absent entirely. Not repairable.
        missing = [f for f in REQUIRED_PRICE_FIELDS if f not in candle]
        if missing:
            _quarantine(quarantined, symbol, candle, MISSING_FIELD,
                        f"missing required field(s): {', '.join(missing)}")
            continue

        # Defect 3: present but not a number. Not repairable.
        prices: dict[str, float] = {}
        bad_types = []
        for field in REQUIRED_PRICE_FIELDS:
            number = _as_number(candle[field])
            if number is None:
                bad_types.append(f"{field}={candle[field]!r}")
            else:
                prices[field] = number
        if bad_types:
            _quarantine(quarantined, symbol, candle, NOT_A_NUMBER,
                        f"non-numeric price(s): {', '.join(bad_types)}")
            continue

        non_positive = [f for f, v in prices.items() if v <= 0]
        if non_positive:
            _quarantine(quarantined, symbol, candle, NON_POSITIVE_PRICE,
                        f"non-positive price(s): {', '.join(sorted(non_positive))}")
            continue

        # --- defect 4: high below low -----------------------------------
        if prices["high"] < prices["low"]:
            original_high, original_low = prices["high"], prices["low"]
            swapped_ok = (
                repair
                and original_low >= original_high
                and original_high <= prices["open"] <= original_low
                and original_high <= prices["close"] <= original_low
            )
            if not swapped_ok:
                # Either repair is off, or the swap does not fully resolve the
                # candle -- which means the transposition story does not hold
                # and a swap would be inventing a number.
                _quarantine(quarantined, symbol, candle, HIGH_BELOW_LOW,
                            f"high {original_high} < low {original_low}"
                            + ("" if repair else " (repair disabled)"))
                continue
            prices["high"], prices["low"] = original_low, original_high
            repairs.append({
                "code": REPAIR_HIGH_LOW,
                "detail": f"high/low transposed; swapped to high="
                          f"{prices['high']}, low={prices['low']} "
                          f"(open and close both fall inside the swapped range)",
            })

        # open and close must sit inside the day's range.
        outside = [
            f for f in ("open", "close")
            if not (prices["low"] <= prices[f] <= prices["high"])
        ]
        if outside:
            field = outside[0]
            _quarantine(quarantined, symbol, candle, HIGH_BELOW_LOW,
                        f"{field} {prices[field]} outside "
                        f"[{prices['low']}, {prices['high']}]")
            continue

        # --- defect 5: volume -------------------------------------------
        raw_volume = candle.get("volume")
        volume: int | None = None
        if raw_volume is not None:
            numeric_volume = _as_number(raw_volume)
            if numeric_volume is None:
                _quarantine(quarantined, symbol, candle, NOT_A_NUMBER,
                            f"non-numeric volume {raw_volume!r}")
                continue
            if numeric_volume in VOLUME_SENTINELS and repair:
                # Sentinel for "unknown", not a real count. The same feed
                # expresses unknown volume as null elsewhere, so normalise.
                volume = None
                repairs.append({
                    "code": REPAIR_VOLUME,
                    "detail": f"volume {raw_volume} is a sentinel for unknown; "
                              f"normalised to null (prices unaffected)",
                })
            elif numeric_volume < 0:
                _quarantine(quarantined, symbol, candle, NEGATIVE_VOLUME,
                            f"volume {raw_volume} is negative"
                            + ("" if repair else " (repair disabled)"))
                continue
            else:
                volume = int(numeric_volume)

        adjclose = _as_number(candle.get("adjclose"))
        seen_dates.add(parsed_date)
        rows.append({
            "symbol": symbol,
            "date": parsed_date,
            "open": prices["open"],
            "high": prices["high"],
            "low": prices["low"],
            "close": prices["close"],
            "adjclose": adjclose if adjclose is not None else prices["close"],
            "volume": volume,
            "synthetic": bool(candle.get("synthetic", False)),
            "currency": currency,
            "repaired": bool(repairs),
            "repairs": repairs,
        })

    rows.sort(key=lambda r: r["date"])
    _derive(rows)

    return {
        "symbol": symbol,
        "currency": currency,
        "interval": interval,
        "rows": rows,
        "quarantined": quarantined,
        "summary": _summarise(symbol, candles, rows, quarantined, repair),
    }


def _derive(rows: list[dict]) -> None:
    """Add per-row derived measures, in place. Requires rows sorted by date."""
    previous_close = None
    for row in rows:
        row["range"] = round(row["high"] - row["low"], 4)
        row["change"] = round(row["close"] - row["open"], 4)
        if previous_close:
            row["daily_return_pct"] = round(
                (row["close"] - previous_close) / previous_close * 100, 4
            )
        else:
            row["daily_return_pct"] = None
        row["turnover"] = (
            round(row["close"] * row["volume"], 2) if row["volume"] is not None else None
        )
        previous_close = row["close"]


def _summarise(symbol, candles, rows, quarantined, repair) -> dict:
    """Aggregate the cleaned rows. Counts reconcile: kept + quarantined = in."""
    reasons: dict[str, int] = {}
    for bad in quarantined:
        reasons[bad["reason"]] = reasons.get(bad["reason"], 0) + 1

    repair_counts: dict[str, int] = {}
    for row in rows:
        for entry in row["repairs"]:
            repair_counts[entry["code"]] = repair_counts.get(entry["code"], 0) + 1

    closes = [r["close"] for r in rows]
    volumes = [r["volume"] for r in rows if r["volume"] is not None]
    returns = [r["daily_return_pct"] for r in rows if r["daily_return_pct"] is not None]

    summary = {
        "symbol": symbol,
        "repair_enabled": repair,
        "candles_in": len(candles),
        "rows_kept": len(rows),
        "rows_quarantined": len(quarantined),
        "rows_repaired": sum(1 for r in rows if r["repaired"]),
        "quarantine_reasons": reasons,
        "repair_counts": repair_counts,
        "synthetic_rows": sum(1 for r in rows if r["synthetic"]),
        "missing_volume_rows": sum(1 for r in rows if r["volume"] is None),
    }
    if rows:
        summary.update({
            "date_from": rows[0]["date"],
            "date_to": rows[-1]["date"],
            "close_first": rows[0]["close"],
            "close_last": rows[-1]["close"],
            "close_min": min(closes),
            "close_max": max(closes),
            "period_return_pct": round(
                (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"] * 100, 4
            ),
            "avg_volume": round(sum(volumes) / len(volumes), 2) if volumes else None,
            "max_daily_move_pct": max(returns, key=abs) if returns else None,
        })
    return summary


def transform_many(payloads: list[dict], repair: bool = True) -> list[dict]:
    """Transform several payloads. One per symbol, in the order given."""
    return [transform(p, repair=repair) for p in payloads]
