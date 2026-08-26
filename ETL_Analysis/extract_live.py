from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - requests is a sprint dependency
    requests = None

BASE_URL = "https://y4t9nq2bqf.execute-api.eu-west-2.amazonaws.com/v1"
CACHE_DIR = Path(__file__).parent / ".cache"
KEY_ENV_VAR = "FAUXNANCE_API_KEY"

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
TIMEOUT_SECONDS = 15

log = logging.getLogger(__name__)


class QuotaExhausted(RuntimeError):
    """HTTP 429. Stop the run; sleeping until midnight UTC is not recovery."""


class BadRequest(RuntimeError):
    """A 4xx that retrying would only repeat. Fail this symbol, carry on."""


class ServiceUnreachable(RuntimeError):
    """Nothing reached the service after the retries were exhausted."""


class MissingApiKey(RuntimeError):
    """FAUXNANCE_API_KEY is not set."""


def _api_key() -> str:
    key = os.environ.get(KEY_ENV_VAR)
    if not key:
        raise MissingApiKey(
            f"{KEY_ENV_VAR} is not set. Copy .env.example to .env and put the "
            f"key there; .env is git-ignored."
        )
    return key


def _cache_path(symbol: str, start: str | None, end: str | None) -> Path:
    """One file per symbol+range. Hashed so a symbol like FX:EUR/USD is a
    legal filename."""
    token = f"{symbol}|{start or ''}|{end or ''}"
    digest = hashlib.sha256(token.encode()).hexdigest()[:12]
    safe = symbol.replace("/", "-").replace(":", "-")
    return CACHE_DIR / f"candles-{safe}-{digest}.json"


def extract(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    use_cache: bool = True,
) -> dict:
    """Return the raw candles envelope for `symbol`, unchanged.

    Hands the payload on exactly as received: no parsing, no cleaning, no
    reshaping. That is the transform's job.
    """
    cache_file = _cache_path(symbol, start, end)

    if use_cache and cache_file.exists():
        log.info("cache hit: %s (no quota used)", symbol)
        with cache_file.open(encoding="utf-8") as fh:
            return json.load(fh)

    if requests is None:
        raise ImportError("requests is required for the live client")

    url = f"{BASE_URL}/candles/{symbol}"
    params = {k: v for k, v in (("start", start), ("end", end)) if v}
    headers = {"X-Api-Key": _api_key()}  # never logged

    last_network_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=TIMEOUT_SECONDS
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            # Case 3: nothing reached the service. Retry with growing backoff.
            last_network_error = exc
            if attempt == MAX_RETRIES:
                break
            wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            log.warning(
                "network error for %s (attempt %d/%d), retrying in %.1fs: %s",
                symbol, attempt, MAX_RETRIES, wait, exc,
            )
            time.sleep(wait)
            continue

        # Case 1: quota exhausted. Stop; do not retry, do not sleep to midnight.
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise QuotaExhausted(
                f"daily quota exhausted (HTTP 429). Resets at midnight UTC; "
                f"Retry-After={retry_after}s. Check GET /usage."
            )

        # Case 2: the request itself is wrong. Retrying repeats the mistake.
        if 400 <= response.status_code < 500:
            meaning = {
                400: "bad request (a range over ten years?)",
                401: "bad or missing API key",
                404: f"Fauxnance does not serve {symbol}",
            }.get(response.status_code, "client error")
            raise BadRequest(f"HTTP {response.status_code} for {symbol}: {meaning}")

        response.raise_for_status()
        payload = response.json()

        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with cache_file.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            log.info("cached raw response for %s", symbol)

        return payload

    raise ServiceUnreachable(
        f"{symbol}: no response after {MAX_RETRIES} attempts: {last_network_error}"
    )


def health() -> dict:
    """GET /health. Needs no key -- check this before assuming anything."""
    if requests is None:
        raise ImportError("requests is required for the live client")
    return requests.get(f"{BASE_URL}/health", timeout=TIMEOUT_SECONDS).json()


def usage() -> dict:
    """GET /usage. Check where you stand before assuming the API is broken."""
    if requests is None:
        raise ImportError("requests is required for the live client")
    return requests.get(
        f"{BASE_URL}/usage",
        headers={"X-Api-Key": _api_key()},
        timeout=TIMEOUT_SECONDS,
    ).json()
