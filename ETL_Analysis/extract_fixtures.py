from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FIXTURE_BY_SYMBOL = {
    "RELIANCE.NS": "candles-reliance-ns-2026-07.json",
    "INFY.NS": "candles-infy-ns-2026-07.json",
    "TATASTEEL.BO": "candles-malformed.json",
}


class SymbolNotAvailable(LookupError):
    pass


def available_symbols() -> list[str]:
    return sorted(FIXTURE_BY_SYMBOL)


def extract(symbol: str, start: str | None = None, end: str | None = None,
            interval: str | None = None) -> dict:
    try:
        filename = FIXTURE_BY_SYMBOL[symbol]
    except KeyError:
        raise SymbolNotAvailable(
            f"no fixture for {symbol!r}; available: {', '.join(available_symbols())}"
        ) from None

    path = FIXTURES_DIR / filename
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    payload.setdefault("meta", {})
    payload["meta"]["retrievedFrom"] = f"fixture:{filename}"
    payload["meta"]["requestedRange"] = {"start": start, "end": end}
    payload["meta"]["requestedInterval"] = interval
    return payload


def extract_many(symbols: list[str],
                 interval: str | None = None) -> tuple:
    payloads: list[dict] = []
    failures: list[tuple[str, str]] = []
    for symbol in symbols:
        try:
            payloads.append(extract(symbol, interval=interval))
        except SymbolNotAvailable as exc:
            failures.append((symbol, str(exc)))
    return payloads, failures
