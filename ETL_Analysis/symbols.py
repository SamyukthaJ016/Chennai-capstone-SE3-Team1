from __future__ import annotations

import logging
from pathlib import Path

SYMBOL_FILE = Path(__file__).parent / "symbols_nse_bse.txt"
log = logging.getLogger(__name__)


class QuotaTooLow(RuntimeError):
    pass


def filter_symbols(
    symbols: list[str],
    exchanges: list[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    from .load import exchange_for

    chosen = symbols
    if exchanges:
        wanted = {e.upper() for e in exchanges}
        chosen = [s for s in chosen if exchange_for(s) in wanted]
    if limit is not None:
        chosen = chosen[:limit]
    return chosen


def group_by_exchange(symbols: list[str]) -> dict:
    from .load import exchange_for

    counts: dict[str, int] = {}
    for symbol in symbols:
        venue = exchange_for(symbol)
        counts[venue] = counts.get(venue, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def load_symbol_file(path: Path | str | None = None) -> list[str]:
    source = Path(path) if path else SYMBOL_FILE
    if not source.is_file():
        raise FileNotFoundError(f"symbol file not found: {source}")

    found: list[str] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            found.append(line)

    seen = set()
    return [s for s in found if not (s in seen or seen.add(s))]


def remaining_quota() -> int | None:
    from .extract_live import usage

    try:
        report = usage()
    except Exception as exc:
        log.warning("could not read /usage: %s", exc)
        return None
    return _remaining_from_usage(report)


def _remaining_from_usage(report) -> int | None:
    if not isinstance(report, dict):
        return None
    body = report.get("data") if isinstance(report.get("data"), dict) else report

    for key in ("remaining", "requestsRemaining", "requests_remaining", "left"):
        value = body.get(key)
        if isinstance(value, (int, float)):
            return int(value)

    limit = next((body.get(k) for k in ("limit", "quota", "dailyLimit",
                                        "daily_limit")
                  if isinstance(body.get(k), (int, float))), None)
    used = next((body.get(k) for k in ("used", "count", "requests",
                                       "requestsToday", "requests_today")
                 if isinstance(body.get(k), (int, float))), None)
    if limit is not None and used is not None:
        return int(limit) - int(used)
    return None


def plan_pull(symbols: list[str], cached: int = 0,
              check_quota: bool = True) -> dict:
    needed = max(len(symbols) - cached, 0)
    remaining = remaining_quota() if check_quota else None

    if remaining is not None and needed > remaining:
        raise QuotaTooLow(
            f"{needed} request(s) needed for {len(symbols)} symbol(s) but only "
            f"{remaining} left today. Narrow the pull with --exchanges or "
            f"--limit, or wait for the quota to reset at midnight UTC."
        )
    return {"needed": needed, "remaining": remaining, "ok": True}
