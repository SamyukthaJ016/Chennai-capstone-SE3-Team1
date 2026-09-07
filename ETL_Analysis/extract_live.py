from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

DEFAULT_BASE_URL = "https://y4t9nq2bqf.execute-api.eu-west-2.amazonaws.com/v1"
CACHE_DIR = Path(__file__).parent / ".cache"
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

KEY_ENV_VAR = "FAUXNANCE_API_KEY"
BASE_URL_ENV_VAR = "FAUXNANCE_BASE_URL"

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
TIMEOUT_SECONDS = 15

log = logging.getLogger(__name__)


class QuotaExhausted(RuntimeError):
    pass


class BadRequest(RuntimeError):
    pass


class ServiceUnreachable(RuntimeError):
    pass


class MissingApiKey(RuntimeError):
    pass


def _read_env_file() -> dict:
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


def _cache_path(symbol: str, start: str | None, end: str | None,
                interval: str | None = None) -> Path:
    token = f"{symbol}|{start or ''}|{end or ''}|{interval or ''}"
    digest = hashlib.sha256(token.encode()).hexdigest()[:12]
    safe = symbol.replace("/", "-").replace(":", "-")
    return CACHE_DIR / f"candles-{safe}-{digest}.json"


def extract(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    use_cache: bool = True,
    interval: str | None = None,
) -> dict:
    cache_file = _cache_path(symbol, start, end, interval)

    if use_cache and cache_file.exists():
        log.info("cache hit: %s (no quota used)", symbol)
        with cache_file.open(encoding="utf-8") as fh:
            return json.load(fh)

    if requests is None:
        raise ImportError("requests is required for the live client")

    url = f"{base_url()}/candles/{symbol}"
    params = {k: v for k, v in (("start", start), ("end", end),
                                ("interval", interval)) if v}
    headers = {"X-Api-Key": _api_key()}

    last_network_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=TIMEOUT_SECONDS
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
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

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise QuotaExhausted(
                f"daily quota exhausted (HTTP 429). Resets at midnight UTC; "
                f"Retry-After={retry_after}s. Check GET /usage."
            )

        if 400 <= response.status_code < 500:
            meaning = {
                400: "bad request (a range over ten years?)",
                401: f"no API key was sent; set {KEY_ENV_VAR}",
                403: (f"the key in {KEY_ENV_VAR} reached Fauxnance and was "
                      f"refused. It is present but not accepted: check it is "
                      f"current, not revoked, and issued for {base_url()}"),
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
    if requests is None:
        raise ImportError("requests is required for the live client")
    return requests.get(f"{base_url()}/health", timeout=TIMEOUT_SECONDS).json()


def usage() -> dict:
    if requests is None:
        raise ImportError("requests is required for the live client")
    return requests.get(
        f"{base_url()}/usage",
        headers={"X-Api-Key": _api_key()},
        timeout=TIMEOUT_SECONDS,
    ).json()
