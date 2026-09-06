from __future__ import annotations

import json

import pytest

from ETL_Analysis import extract_live as E


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status reached for " + str(self.status_code))


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setenv(E.KEY_ENV_VAR, "fnx_test_key_not_a_real_one")
    monkeypatch.setattr(E, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(E, "BACKOFF_BASE_SECONDS", 0)
    return E


def respond_with(monkeypatch, response):
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers or {}
        seen["params"] = params or {}
        return response

    monkeypatch.setattr(E.requests, "get", fake_get)
    return seen


def test_the_key_is_sent_as_the_header_the_api_recognises(live, monkeypatch):
    seen = respond_with(monkeypatch, FakeResponse(200, {"data": {"candles": []}}))
    live.extract("RELIANCE.NS", use_cache=False)
    assert "X-Api-Key" in seen["headers"]
    assert seen["headers"]["X-Api-Key"] == "fnx_test_key_not_a_real_one"


def test_a_rejected_key_says_the_key_was_refused(live, monkeypatch):
    respond_with(monkeypatch, FakeResponse(403, {"message": "Forbidden"}))
    with pytest.raises(E.BadRequest) as caught:
        live.extract("RELIANCE.NS", use_cache=False)
    message = str(caught.value)
    assert "403" in message
    assert E.KEY_ENV_VAR in message
    assert "refused" in message
    assert "client error" not in message


def test_a_missing_key_is_reported_differently_from_a_rejected_one(live, monkeypatch):
    respond_with(monkeypatch, FakeResponse(401, {"message": "Unauthorized"}))
    with pytest.raises(E.BadRequest) as caught:
        live.extract("RELIANCE.NS", use_cache=False)
    assert "no API key was sent" in str(caught.value)


def test_an_unserved_symbol_names_the_symbol(live, monkeypatch):
    respond_with(monkeypatch, FakeResponse(404))
    with pytest.raises(E.BadRequest) as caught:
        live.extract("NOSUCH.NS", use_cache=False)
    assert "NOSUCH.NS" in str(caught.value)


def test_a_bad_range_is_reported_as_a_bad_request(live, monkeypatch):
    respond_with(monkeypatch, FakeResponse(400))
    with pytest.raises(E.BadRequest) as caught:
        live.extract("RELIANCE.NS", use_cache=False)
    assert "bad request" in str(caught.value)


def test_quota_exhaustion_is_its_own_exception(live, monkeypatch):
    respond_with(monkeypatch, FakeResponse(429, headers={"Retry-After": "3600"}))
    with pytest.raises(E.QuotaExhausted) as caught:
        live.extract("RELIANCE.NS", use_cache=False)
    assert "3600" in str(caught.value)


def test_no_error_path_puts_the_key_in_its_message(live, monkeypatch):
    key = "fnx_test_key_not_a_real_one"
    for status in (400, 401, 403, 404, 429):
        respond_with(monkeypatch, FakeResponse(status, headers={"Retry-After": "1"}))
        with pytest.raises((E.BadRequest, E.QuotaExhausted)) as caught:
            live.extract("RELIANCE.NS", use_cache=False)
        assert key not in str(caught.value), status


def test_a_missing_key_raises_before_any_request_is_made(monkeypatch):
    monkeypatch.delenv(E.KEY_ENV_VAR, raising=False)
    monkeypatch.setattr(E, "_read_env_file", dict)

    def explode(*args, **kwargs):
        raise AssertionError("a request was made without a key")

    monkeypatch.setattr(E.requests, "get", explode)
    with pytest.raises(E.MissingApiKey):
        E.extract("RELIANCE.NS", use_cache=False)


def test_a_placeholder_key_is_refused_before_any_request(monkeypatch):
    monkeypatch.setenv(E.KEY_ENV_VAR, "your-key-here")
    with pytest.raises(E.MissingApiKey) as caught:
        E._api_key()
    assert "placeholder" in str(caught.value)


def test_a_successful_response_is_cached_and_read_back(live, monkeypatch, tmp_path):
    payload = {"data": {"symbol": "RELIANCE.NS", "candles": [{"close": 1}]}}
    respond_with(monkeypatch, FakeResponse(200, payload))
    first = live.extract("RELIANCE.NS", use_cache=True)
    assert first == payload

    def explode(*args, **kwargs):
        raise AssertionError("the cache was not used on the second call")

    monkeypatch.setattr(E.requests, "get", explode)
    assert live.extract("RELIANCE.NS", use_cache=True) == payload


def test_the_cache_key_separates_intervals(live, monkeypatch):
    daily = live._cache_path("RELIANCE.NS", None, None, "1d")
    weekly = live._cache_path("RELIANCE.NS", None, None, "1wk")
    assert daily != weekly


def test_health_needs_no_key(monkeypatch):
    monkeypatch.delenv(E.KEY_ENV_VAR, raising=False)
    monkeypatch.setattr(E, "_read_env_file", dict)
    seen = respond_with(monkeypatch, FakeResponse(200, {"data": {"status": "ok"}}))

    def fake_get(url, timeout=None):
        seen["url"] = url
        return FakeResponse(200, {"data": {"status": "ok"}})

    monkeypatch.setattr(E.requests, "get", fake_get)
    assert E.health()["data"]["status"] == "ok"
    assert seen["url"].endswith("/health")
