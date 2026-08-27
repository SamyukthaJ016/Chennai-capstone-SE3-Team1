"""Offline extract.

Stands in for `Extract.py` while the Fauxnance key is a dummy. It returns the
same raw `CandlesResponse` envelope the live API returns, read from
`fixtures/` instead of over the network, and hands it on unchanged.

Extract obtains raw responses and hands them on unchanged. It does not parse,
clean or reshape: that is the transform's job, and keeping the split means a
wrong number can be traced to one of three places.

Swapping this for the live client is a one-line change in `pipeline.py`,
because both expose the same callable:

    extract(symbol, start=None, end=None) -> dict
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Symbol -> fixture filename. The live client builds a URL here instead.
FIXTURE_BY_SYMBOL = {
    "RELIANCE.NS": "candles-reliance-ns-2026-07.json",
    "INFY.NS": "candles-infy-ns-2026-07.json",
    "TATASTEEL.BO": "candles-malformed.json",
}


class SymbolNotAvailable(LookupError):
    """No fixture for this symbol.

    Stands in for the live client's 404: the request is wrong, so fail this
    symbol and carry on with the others rather than retrying.
    """


def available_symbols() -> list[str]:
    """Symbols this offline extract can serve."""
    return sorted(FIXTURE_BY_SYMBOL)


def extract(symbol: str, start: str | None = None, end: str | None = None) -> dict:
    """Return the raw candles envelope for `symbol`, unchanged.

    `start` and `end` are accepted so the signature matches the live client.
    The fixtures are fixed date ranges, so they are recorded in the returned
    envelope's meta rather than used to filter -- filtering is a transform
    concern, and this function must not reshape the payload.
    """
    try:
        filename = FIXTURE_BY_SYMBOL[symbol]
    except KeyError:
        raise SymbolNotAvailable(
            f"no fixture for {symbol!r}; available: {', '.join(available_symbols())}"
        ) from None

    path = FIXTURES_DIR / filename
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    # Provenance only. The payload itself is untouched.
    payload.setdefault("meta", {})
    payload["meta"]["retrievedFrom"] = f"fixture:{filename}"
    payload["meta"]["requestedRange"] = {"start": start, "end": end}
    return payload


def extract_many(symbols: list[str]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Extract several symbols.

    Returns (payloads, failures). A symbol that cannot be served is recorded as
    a failure and the rest carry on -- one bad symbol does not abort the run.
    """
    payloads: list[dict] = []
    failures: list[tuple[str, str]] = []
    for symbol in symbols:
        try:
            payloads.append(extract(symbol))
        except SymbolNotAvailable as exc:
            failures.append((symbol, str(exc)))
    return payloads, failures
