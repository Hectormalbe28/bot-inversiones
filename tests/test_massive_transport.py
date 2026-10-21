from datetime import UTC, date, datetime
from urllib.error import HTTPError, URLError

import pytest

from app.infrastructure.providers.massive_transport import (
    MassiveGroupedDailyHttpClient,
    MassiveTransportError,
)


class _Response:
    def __init__(self, raw: bytes, status: int = 200):
        self.raw = raw
        self.status = status

    def read(self) -> bytes:
        return self.raw

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_grouped_daily_request_is_raw_and_secret_is_not_returned():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _Response(b'{"status":"OK","results":[],"resultsCount":0}')

    client = MassiveGroupedDailyHttpClient(
        api_key="super-secret",
        opener=opener,
        clock=lambda: datetime(2026, 10, 21, 19, 0, tzinfo=UTC),
    )
    result = client.fetch(date(2026, 10, 20))

    assert "/2026-10-20?" in captured["url"]
    assert "adjusted=false" in captured["url"]
    assert "apiKey=super-secret" in captured["url"]
    assert "super-secret" not in result.source_url
    assert result.session_date == date(2026, 10, 20)
    assert result.received_at == datetime(2026, 10, 21, 19, 0, tzinfo=UTC)


def test_api_key_is_required():
    with pytest.raises(ValueError, match="api_key"):
        MassiveGroupedDailyHttpClient(api_key="")


def test_https_is_required():
    with pytest.raises(ValueError, match="HTTPS"):
        MassiveGroupedDailyHttpClient(
            api_key="secret",
            base_url="http://api.massive.com",
        )


def test_429_is_retried_with_bounded_backoff():
    attempts = []
    sleeps = []

    def opener(request, timeout):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise HTTPError(request.full_url, 429, "rate limit", None, None)
        return _Response(b'{"status":"OK","results":[],"resultsCount":0}')

    client = MassiveGroupedDailyHttpClient(
        api_key="secret",
        opener=opener,
        sleeper=sleeps.append,
        base_backoff_seconds=0.5,
        max_attempts=2,
    )
    result = client.fetch(date(2026, 10, 20))

    assert result.attempts == 2
    assert sleeps == [0.5]


def test_network_error_is_retryable_then_terminal_at_limit():
    def opener(request, timeout):
        raise URLError("offline")

    client = MassiveGroupedDailyHttpClient(
        api_key="secret",
        opener=opener,
        sleeper=lambda _: None,
        max_attempts=2,
    )

    with pytest.raises(MassiveTransportError) as exc:
        client.fetch(date(2026, 10, 20))

    assert exc.value.retryable is True
    assert exc.value.attempts == 2
    assert "secret" not in str(exc.value)


def test_authentication_error_is_not_retried():
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, 401, "unauthorized", None, None)

    client = MassiveGroupedDailyHttpClient(
        api_key="secret",
        opener=opener,
        sleeper=lambda _: None,
        max_attempts=3,
    )

    with pytest.raises(MassiveTransportError) as exc:
        client.fetch(date(2026, 10, 20))

    assert calls == 1
    assert exc.value.retryable is False
    assert exc.value.attempts == 1
    assert "secret" not in str(exc.value)


def test_empty_payload_is_terminal():
    client = MassiveGroupedDailyHttpClient(
        api_key="secret",
        opener=lambda request, timeout: _Response(b""),
    )
    with pytest.raises(MassiveTransportError) as exc:
        client.fetch(date(2026, 10, 20))
    assert exc.value.retryable is False


def test_default_opener_passes_timeout_as_keyword(monkeypatch):
    captured = {}

    def fake_urlopen(request, *, timeout):
        captured["timeout"] = timeout
        return _Response(b'{"status":"OK","results":[],"resultsCount":0}')

    from app.infrastructure.providers import massive_transport

    monkeypatch.setattr(massive_transport, "urlopen", fake_urlopen)
    client = MassiveGroupedDailyHttpClient(api_key="secret", timeout_seconds=3.5)
    client.fetch(date(2026, 10, 20))

    assert captured["timeout"] == 3.5
