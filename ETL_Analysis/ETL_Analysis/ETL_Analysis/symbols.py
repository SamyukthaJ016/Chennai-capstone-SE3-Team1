"""The symbol universe: which instruments the pipeline pulls.

There is no discovery of any kind. The universe is `symbols_nse_bse.txt` -- a
plain list of NSE and BSE symbols, one per line, edited by hand. The pipeline
either pulls the symbols you name with `--symbols`, or every symbol in that
file.

The API documents no catalogue endpoint. Rather than probe for one, or pull
every symbol once to see which resolve, the file is simply the answer: you can
read it, edit it, and know exactly what a run will fetch before you start it.
A symbol the API does not serve fails that symbol with a 404 and the run
carries on, which is the same handling every other request error gets.

QUOTA
-----
The quota is 2000 requests per day per key, and a pull is one request per
symbol. `plan_pull` checks `GET /usage` and refuses to start a pull it cannot
finish, rather than exhausting the key halfway through and leaving a partial
dataset that looks complete.
"""

from __future__ import annotations

import logging
from pathlib import Path

SYMBOL_FILE = Path(__file__).parent / "symbols_nse_bse.txt"
log = logging.getLogger(__name__)


class QuotaTooLow(RuntimeError):
    """Not enough requests left today to finish the pull that was asked for."""


def filter_symbols(
    symbols: list[str],
    exchanges: list[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Narrow a symbol list.

    `exchanges` matches the venue codes `load.exchange_for` derives -- NSE,
    BSE, US, FX, CRYPTO -- so "every Indian instrument" is
    `filter_symbols(all_symbols, exchanges=["NSE", "BSE"])`.
    """
    from .load import exchange_for

    chosen = symbols
    if exchanges:
        wanted = {e.upper() for e in exchanges}
        chosen = [s for s in chosen if exchange_for(s) in wanted]
    if limit is not None:
        chosen = chosen[:limit]
    return chosen


def group_by_exchange(symbols: list[str]) -> dict:
    """Count symbols per venue. Useful before committing to a full pull."""
    from .load import exchange_for

    counts: dict[str, int] = {}
    for symbol in symbols:
        venue = exchange_for(symbol)
        counts[venue] = counts.get(venue, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# The bundled symbol file
# ---------------------------------------------------------------------------

def load_symbol_file(path: Path | str | None = None) -> list[str]:
    """Read the bundled NSE/BSE universe.

    One symbol per line. Blank lines are skipped, `#` starts a comment, and a
    trailing comment after a symbol is stripped -- so a company name can sit
    beside its ticker and stay readable.

    The file is a candidate universe of real listed companies. Nothing has
    been checked against Fauxnance -- a symbol it does not serve returns a 404,
    which fails that symbol and lets the run continue.
    """
    source = Path(path) if path else SYMBOL_FILE
    if not source.is_file():
        raise FileNotFoundError(f"symbol file not found: {source}")

    found: list[str] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            found.append(line)

    # Preserve file order (grouped by venue and sector, which is useful when
    # reading a --limit'd pull) but drop any accidental repeat.
    seen = set()
    return [s for s in found if not (s in seen or seen.add(s))]


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------

def remaining_quota() -> int | None:
    """Requests left today, or None if /usage does not say."""
    from .extract_live import usage

    try:
        report = usage()
    except Exception as exc:  # noqa: BLE001 - usage is advisory, never fatal
        log.warning("could not read /usage: %s", exc)
        return None
    return _remaining_from_usage(report)


def _remaining_from_usage(report) -> int | None:
    """Pull a remaining-requests number out of a /usage payload.

    Shape is undocumented, so several spellings are accepted, including
    deriving it from a limit and a used count.
    """
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
    """Decide whether a pull can finish, before starting it.

    Returns {"needed", "remaining", "ok"}. Raises QuotaTooLow when the API
    reports fewer requests left than the pull requires -- stopping before a
    partial dataset is created, rather than after.
    """
    needed = max(len(symbols) - cached, 0)
    remaining = remaining_quota() if check_quota else None

    if remaining is not None and needed > remaining:
        raise QuotaTooLow(
            f"{needed} request(s) needed for {len(symbols)} symbol(s) but only "
            f"{remaining} left today. Narrow the pull with --exchanges or "
            f"--limit, or wait for the quota to reset at midnight UTC."
        )
    return {"needed": needed, "remaining": remaining, "ok": True}
