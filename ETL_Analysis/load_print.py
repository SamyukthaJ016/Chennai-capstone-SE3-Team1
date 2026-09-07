from __future__ import annotations

COLUMNS = [
    ("date", 12),
    ("open", 11),
    ("high", 11),
    ("low", 11),
    ("close", 11),
    ("volume", 13),
    ("return %", 10),
    ("synth", 6),
    ("fixed", 6),
]


def _fmt(value, width, numeric=True):
    if value is None:
        text = "-"
    elif isinstance(value, bool):
        text = "yes" if value else ""
    elif isinstance(value, float):
        text = f"{value:,.2f}"
    elif isinstance(value, int):
        text = f"{value:,}"
    else:
        text = str(value)
    return text.rjust(width) if numeric else text.ljust(width)


def load(result: dict, show_rows: int | None = None) -> int:
    symbol = result["symbol"]
    rows = result["rows"]
    quarantined = result["quarantined"]
    summary = result["summary"]

    print()
    print("=" * 78)
    print(f"  {symbol}   ({result.get('interval') or '?'}, {result.get('currency') or '?'})")
    print("=" * 78)

    if rows:
        header = "".join(_fmt(name, width) for name, width in COLUMNS)
        print(header)
        print("-" * len(header))
        shown = rows if show_rows is None else rows[:show_rows]
        for row in shown:
            print(
                _fmt(row["date"].isoformat(), 12)
                + _fmt(row["open"], 11)
                + _fmt(row["high"], 11)
                + _fmt(row["low"], 11)
                + _fmt(row["close"], 11)
                + _fmt(row["volume"], 13)
                + _fmt(row["daily_return_pct"], 10)
                + _fmt(row["synthetic"], 6)
                + _fmt(row.get("repaired", False), 6)
            )
        if show_rows is not None and len(rows) > show_rows:
            print(f"{'':>12}... {len(rows) - show_rows} more row(s)")
    else:
        print("  no clean rows")

    print()
    print(f"  candles in ......... {summary['candles_in']}")
    print(f"  rows loaded ........ {summary['rows_kept']}")
    print(f"  rows quarantined ... {summary['rows_quarantined']}")
    if summary.get("rows_repaired"):
        print(f"  rows repaired ...... {summary['rows_repaired']} (loaded with a flag)")

    if rows:
        print(f"  period ............. {summary['date_from']} to {summary['date_to']}")
        print(f"  close .............. {summary['close_first']:,.2f} "
              f"-> {summary['close_last']:,.2f} "
              f"({summary['period_return_pct']:+.2f}%)")
        print(f"  close range ........ {summary['close_min']:,.2f} "
              f".. {summary['close_max']:,.2f}")
        if summary["avg_volume"] is not None:
            print(f"  avg volume ......... {summary['avg_volume']:,.0f}")
        if summary["max_daily_move_pct"] is not None:
            print(f"  largest daily move . {summary['max_daily_move_pct']:+.2f}%")
        if summary["synthetic_rows"]:
            print(f"  synthetic rows ..... {summary['synthetic_rows']} "
                  f"(interpolated by the vendor, not observed)")
        if summary["missing_volume_rows"]:
            print(f"  rows w/o volume .... {summary['missing_volume_rows']}")

    repaired_rows = [r for r in rows if r.get("repaired")]
    if repaired_rows:
        print()
        print(f"  REPAIRED ({len(repaired_rows)}) -- loaded, but flagged so a "
              f"chart can exclude them:")
        for row in repaired_rows:
            for entry in row["repairs"]:
                print(f"    [{entry['code']:<18}] {row['date']}   {entry['detail']}")

    if quarantined:
        print()
        print(f"  QUARANTINED ({len(quarantined)}) -- not loaded, not discarded:")
        for bad in quarantined:
            raw_date = bad["candle"].get("date") if isinstance(bad["candle"], dict) else "?"
            print(f"    [{bad['reason']:<18}] {str(raw_date):<12} {bad['detail']}")

    return len(rows)


def load_many(results: list[dict], show_rows: int | None = None) -> dict:
    totals = {"symbols": 0, "rows_loaded": 0, "rows_quarantined": 0,
              "rows_repaired": 0, "reasons": {}, "repairs": {}}
    for result in results:
        totals["symbols"] += 1
        totals["rows_loaded"] += load(result, show_rows=show_rows)
        totals["rows_quarantined"] += result["summary"]["rows_quarantined"]
        totals["rows_repaired"] += result["summary"].get("rows_repaired", 0)
        for reason, count in result["summary"]["quarantine_reasons"].items():
            totals["reasons"][reason] = totals["reasons"].get(reason, 0) + count
        for code, count in result["summary"].get("repair_counts", {}).items():
            totals["repairs"][code] = totals["repairs"].get(code, 0) + count
    return totals
