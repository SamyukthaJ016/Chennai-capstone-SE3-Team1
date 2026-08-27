"""Live extract: the real Fauxnance client.

Same callable contract as `extract_fixtures.extract`, so `pipeline.py --live`
swaps one for the other and transform and load are untouched.

Not exercised yet: the key in circulation is a dummy. It is written to the
sprint's requirements so it works the day a real key lands.

THE KEY
    Read from FAUXNANCE_API_KEY and from nowhere else. Never a literal in
    source, a test, a fixture or a committed notebook. Never logged.

THE CACHE
    Raw responses are cached to `.cache/`, keyed by symbol and range, so
    re-running the pipeline costs nothing against the 2000/day quota. The RAW
    response is cached, not the cleaned frame, because changing the transform
    is the thing you do most and it must not need a fresh pull.

ERROR HANDLING
    Four cases, told apart, because they need different answers:

    | What happened            | How you know          | What we do            |
    |--------------------------|-----------------------|-----------------------|
    | Daily quota exhausted    | 429 + Retry-After     | Stop, say so plainly  |
    | The request is wrong     | Other 4xx (401/404/400)| Fail symbol, carry on|
    | Nothing reached service  | Connection error/timeout| Retry w/ backoff    |
    | Response arrived, wrong  | 200 + bad candle      | Transform's problem   |

    The fourth is deliberately absent from this module: a high below a low is
    not an HTTP problem, and deciding about it here would put cleaning logic
    in extract.
"""

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

DEFAULT_BASE_URL = "https://y4t9nq2bqf.execute-api.eu-west-2.amazonaws.com/v1"
CACHE_DIR = Path(__file__).parent / ".cache"
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

# NAMES of environment variables. Not values -- putting a key here would make
# it a literal in source, which the sprint forbids and which breaks the lookup
# below, since os.environ would then be searched for a variable named after
# the key itself.
KEY_ENV_VAR = "FAUXNANCE_API_KEY"
BASE_URL_ENV_VAR = "FAUXNANCE_BASE_URL"

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


def _read_env_file() -> dict:
    """Parse .env into a dict.

    Same parser the repo's scripts/db_config.py uses, so both halves of the
    project read the same file the same way. Nothing here exports to the
    process environment: the value is looked up and used, never leaked to
    child processes.
    """
    values = {}
    if not ENV_FILE.is_file():
        return values
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip().upper()] = val.strip().strip('"').strip("'")
    return values


def _setting(name: str, default: str | None = None) -> str | None:
    """Resolve a setting. Precedence: environment variable > .env > default."""
    return os.environ.get(name) or _read_env_file().get(name) or default


def base_url() -> str:
    return (_setting(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    key = _setting(KEY_ENV_VAR)
    if not key:
        raise MissingApiKey(
            f"{KEY_ENV_VAR} is not set. Put it in {ENV_FILE} as\n"
            f"    {KEY_ENV_VAR}=your-key-here\n"
            f"or export it in your shell. .env is git-ignored."
        )
    if key.startswith(("your-", "replace", "changeme")):
        raise MissingApiKey(
            f"{KEY_ENV_VAR} still holds the placeholder value. Replace it "
            f"with the key issued to you."
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

    url = f"{base_url()}/candles/{symbol}"
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
    return requests.get(f"{base_url()}/health", timeout=TIMEOUT_SECONDS).json()


def usage() -> dict:
    """GET /usage. Check where you stand before assuming the API is broken."""
    if requests is None:
        raise ImportError("requests is required for the live client")
    return requests.get(
        f"{base_url()}/usage",
        headers={"X-Api-Key": _api_key()},
        timeout=TIMEOUT_SECONDS,
    ).json()
