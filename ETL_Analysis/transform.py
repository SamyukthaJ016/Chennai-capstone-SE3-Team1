from __future__ import annotations

from datetime import date, datetime

DUPLICATE_DATE = "DUPLICATE_DATE"
MISSING_FIELD = "MISSING_FIELD"
NOT_A_NUMBER = "NOT_A_NUMBER"
HIGH_BELOW_LOW = "HIGH_BELOW_LOW"
NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
BAD_DATE_FORMAT = "BAD_DATE_FORMAT"
NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"

REPAIR_HIGH_LOW = "repair_high_low"
REPAIR_VOLUME = "repair_volume"
REPAIR_DATE = "repair_date"

REQUIRED_PRICE_FIELDS = ("open", "high", "low", "close")

DAYFIRST = True
NON_ISO_DATE_FORMAT = "%d/%m/%Y" if DAYFIRST else "%m/%d/%Y"

VOLUME_SENTINELS = (-1,)


def _parse_iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_non_iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, NON_ISO_DATE_FORMAT).date()
    except ValueError:
        return None


def _as_number(value) -> float | None:
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

        raw_date = candle.get("date")
        parsed_date = _parse_iso_date(raw_date)

        if parsed_date is None:
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

        if parsed_date in seen_dates:
            _quarantine(quarantined, symbol, candle, DUPLICATE_DATE,
                        f"{parsed_date.isoformat()} already seen; "
                        f"first occurrence kept")
            continue

        missing = [f for f in REQUIRED_PRICE_FIELDS if f not in candle]
        if missing:
            _quarantine(quarantined, symbol, candle, MISSING_FIELD,
                        f"missing required field(s): {', '.join(missing)}")
            continue

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

        if prices["high"] < prices["low"]:
            original_high, original_low = prices["high"], prices["low"]
            swapped_ok = (
                repair
                and original_low >= original_high
                and original_high <= prices["open"] <= original_low
                and original_high <= prices["close"] <= original_low
            )
            if not swapped_ok:
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

        raw_volume = candle.get("volume")
        volume: int | None = None
        if raw_volume is not None:
            numeric_volume = _as_number(raw_volume)
            if numeric_volume is None:
                _quarantine(quarantined, symbol, candle, NOT_A_NUMBER,
                            f"non-numeric volume {raw_volume!r}")
                continue
            if numeric_volume in VOLUME_SENTINELS and repair:
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
            "interval": interval,
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
    reasons: dict[str, int] = {}
    for bad in quarantined:
        reasons[bad["reason"]] = reasons.get(bad["reason"], 0) + 1

    repair_counts: dict[str, int] = {}
    for row in rows:
        for entry in row["repairs"]:
            repair_counts[entry["code"]] = repair_counts.get(entry["code"], 0) + 1

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
        "observed_rows": sum(
            1 for r in rows if not r["synthetic"] and not r["repaired"]
        ),
    }
    if rows:
        summary.update(_price_measures(rows))
    return summary


def _price_measures(rows: list[dict]) -> dict:
    closes = [r["close"] for r in rows]
    volumes = [r["volume"] for r in rows if r["volume"] is not None]
    turnovers = [r["turnover"] for r in rows if r["turnover"] is not None]
    returns = [r["daily_return_pct"] for r in rows
               if r["daily_return_pct"] is not None]
    ranges_pct = [
        (r["high"] - r["low"]) / r["low"] * 100 for r in rows if r["low"]
    ]

    measures = {
        "date_from": rows[0]["date"],
        "date_to": rows[-1]["date"],
        "trading_days": len(rows),
        "close_first": rows[0]["close"],
        "close_last": rows[-1]["close"],
        "close_min": min(closes),
        "close_max": max(closes),
        "close_mean": round(sum(closes) / len(closes), 4),
        "period_return_pct": round(
            (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"] * 100, 4
        ),
        "avg_volume": round(sum(volumes) / len(volumes), 2) if volumes else None,
        "max_volume": max(volumes) if volumes else None,
        "min_volume": min(volumes) if volumes else None,
        "total_turnover": round(sum(turnovers), 2) if turnovers else None,
        "avg_daily_range_pct": (
            round(sum(ranges_pct) / len(ranges_pct), 4) if ranges_pct else None
        ),
        "max_drawdown_pct": _max_drawdown_pct(closes),
    }

    if returns:
        best = max(returns)
        worst = min(returns)
        measures.update({
            "max_daily_move_pct": max(returns, key=abs),
            "best_day_pct": best,
            "worst_day_pct": worst,
            "best_day": next(r["date"] for r in rows
                             if r["daily_return_pct"] == best),
            "worst_day": next(r["date"] for r in rows
                              if r["daily_return_pct"] == worst),
            "avg_daily_return_pct": round(sum(returns) / len(returns), 4),
            "volatility_pct": _stdev(returns),
            "up_days": sum(1 for r in returns if r > 0),
            "down_days": sum(1 for r in returns if r < 0),
            "flat_days": sum(1 for r in returns if r == 0),
        })
    return measures


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return round(variance ** 0.5, 4)


def _max_drawdown_pct(closes: list[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for close in closes[1:]:
        peak = max(peak, close)
        drawdown = (close - peak) / peak * 100
        worst = min(worst, drawdown)
    return round(worst, 4)


METRIC_SPEC = [
    ("trading_days", "Trading days", "days"),
    ("close_first", "First close", "price"),
    ("close_last", "Last close", "price"),
    ("close_min", "Lowest close", "price"),
    ("close_max", "Highest close", "price"),
    ("close_mean", "Mean close", "price"),
    ("period_return_pct", "Return over period", "pct"),
    ("avg_daily_return_pct", "Average daily return", "pct"),
    ("volatility_pct", "Daily volatility (std dev)", "pct"),
    ("max_drawdown_pct", "Maximum drawdown", "pct"),
    ("best_day_pct", "Best day", "pct"),
    ("worst_day_pct", "Worst day", "pct"),
    ("max_daily_move_pct", "Largest daily move", "pct"),
    ("avg_daily_range_pct", "Average daily range", "pct"),
    ("up_days", "Up days", "days"),
    ("down_days", "Down days", "days"),
    ("flat_days", "Flat days", "days"),
    ("avg_volume", "Average volume", "shares"),
    ("max_volume", "Highest volume", "shares"),
    ("min_volume", "Lowest volume", "shares"),
    ("total_turnover", "Total turnover", "currency"),
    ("candles_in", "Candles received", "rows"),
    ("rows_kept", "Rows loaded", "rows"),
    ("rows_repaired", "Rows repaired", "rows"),
    ("rows_quarantined", "Rows quarantined", "rows"),
    ("observed_rows", "Rows observed (not repaired or synthetic)", "rows"),
    ("synthetic_rows", "Rows flagged synthetic", "rows"),
    ("missing_volume_rows", "Rows with no volume", "rows"),
]


def metrics(result: dict) -> list[dict]:
    summary = result["summary"]
    out = []
    for key, label, unit in METRIC_SPEC:
        value = summary.get(key)
        if value is None:
            continue
        out.append({
            "symbol": summary["symbol"],
            "metric": key,
            "label": label,
            "unit": unit,
            "value": float(value),
        })
    return out


def summarise_rows(symbol: str, rows: list[dict],
                   quarantined: list[dict] | None = None,
                   repair: bool = True,
                   candles_in: int | None = None) -> dict:
    quarantined = list(quarantined or [])
    rows.sort(key=lambda r: r["date"])
    _derive(rows)
    if candles_in is None:
        candles_in = len(rows) + len(quarantined)
    return _summarise(symbol, range(candles_in), rows, quarantined, repair)


def transform_many(payloads: list[dict], repair: bool = True) -> list[dict]:
    return [transform(p, repair=repair) for p in payloads]
