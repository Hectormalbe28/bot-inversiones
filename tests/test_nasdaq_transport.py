from __future__ import annotations

from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

from app.infrastructure.providers import nasdaq_transport
from app.infrastructure.providers.nasdaq_transport import (
    NASDAQ_LISTED_URL,
    NasdaqSymbolDirectoryHttpClient,
    NasdaqTransportError,
)


def test_default_urlopen_receives_timeout_as_a_keyword(monkeypatch):
    captured = {}

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(
            b"Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            b"Round Lot Size|ETF|NextShares\n"
        )

    monkeypatch.setattr(nasdaq_transport, "urlopen", fake_urlopen)
    client = NasdaqSymbolDirectoryHttpClient(timeout_seconds=3.5)

    client.fetch()

    assert captured["request"].full_url == NASDAQ_LISTED_URL
    assert captured["timeout"] == 3.5


class _Response:
    def __init__(self, raw: bytes, status: int = 200) -> None:
        self.raw = raw
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self.raw

    def getcode(self) -> int:
        return self.status


def test_fetches_raw_bytes_from_official_https_endpoint_without_parsing():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return _Response(b"provider bytes")

    client = NasdaqSymbolDirectoryHttpClient(
        opener=opener,
        sleeper=lambda _: None,
        clock=lambda: datetime(2026, 10, 17, 12, tzinfo=UTC),
    )

    download = client.fetch()

    assert download.raw == b"provider bytes"
    assert download.source_url == NASDAQ_LISTED_URL
    assert download.received_at == datetime(2026, 10, 17, 12, tzinfo=UTC)
    assert download.attempts == 1
    assert requests[0][0].full_url == NASDAQ_LISTED_URL
    assert requests[0][1] == 10.0


def test_retries_transient_http_failure_with_bounded_exponential_backoff():
    outcomes = [HTTPError(NASDAQ_LISTED_URL, 503, "unavailable", None, None), _Response(b"ok")]
    delays = []

    def opener(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    download = NasdaqSymbolDirectoryHttpClient(
        opener=opener, sleeper=delays.append, base_backoff_seconds=0.5
    ).fetch()

    assert download.raw == b"ok"
    assert download.attempts == 2
    assert delays == [0.5]


def test_does_not_retry_non_transient_http_error():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise HTTPError(NASDAQ_LISTED_URL, 404, "missing", None, None)

    with pytest.raises(NasdaqTransportError, match="HTTP 404") as raised:
        NasdaqSymbolDirectoryHttpClient(opener=opener, sleeper=lambda _: None).fetch()

    assert calls == 1
    assert raised.value.retryable is False
    assert raised.value.attempts == 1


def test_rejects_non_https_endpoint():
    with pytest.raises(ValueError, match="HTTPS"):
        NasdaqSymbolDirectoryHttpClient(url="http://example.test/nasdaqlisted.txt")
