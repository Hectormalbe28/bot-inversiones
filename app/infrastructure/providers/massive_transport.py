"""HTTPS-only transport for Massive grouped daily U.S. stock aggregates.

This module acquires provider bytes only. It deliberately does not parse,
resolve identity, apply adjustments, or persist canonical bars.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.clock import require_utc, utc_now

MASSIVE_BASE_URL = "https://api.massive.com"
_GROUPED_DAILY_PATH = "/v2/aggs/grouped/locale/us/market/stocks"


class _Response(Protocol):
    def read(self) -> bytes: ...

    def getcode(self) -> int | None: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: object) -> None: ...


UrlOpener = Callable[[Request, float], _Response]


class MassiveTransportError(Exception):
    """Terminal or exhausted transport error without credential leakage."""

    def __init__(self, message: str, *, retryable: bool, attempts: int) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class MassiveGroupedDailyDownload:
    raw: bytes
    source_url: str
    session_date: date
    received_at: datetime
    attempts: int


class MassiveGroupedDailyHttpClient:
    """Fetch one all-market daily response with raw/as-traded adjustment semantics."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = MASSIVE_BASE_URL,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        opener: UrlOpener | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        if not base_url.startswith("https://"):
            raise ValueError("Massive transport requires an HTTPS base URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds cannot be negative")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._opener = opener or _open_url
        self._sleeper = sleeper or _sleep
        self._clock = clock

    def fetch(self, session_date: date) -> MassiveGroupedDailyDownload:
        """Download raw grouped daily bytes; canonical parsing is a later boundary."""

        source_url = f"{self._base_url}{_GROUPED_DAILY_PATH}/{session_date.isoformat()}"
        query = urlencode({"adjusted": "false", "apiKey": self._api_key})
        request = Request(
            f"{source_url}?{query}",
            headers={
                "User-Agent": "bot-inversiones/0.1 research-client",
                "Accept": "application/json",
            },
        )

        for attempt in range(1, self._max_attempts + 1):
            failure: Exception | None = None
            try:
                with self._opener(request, self._timeout_seconds) as response:
                    status = response.getcode() or 200
                    if status >= 400:
                        raise HTTPError(source_url, status, "HTTP failure", None, None)
                    raw = response.read()

                if not raw:
                    raise MassiveTransportError(
                        "Massive grouped daily returned an empty payload",
                        retryable=False,
                        attempts=attempt,
                    )

                return MassiveGroupedDailyDownload(
                    raw=raw,
                    source_url=source_url,
                    session_date=session_date,
                    received_at=require_utc(self._clock()),
                    attempts=attempt,
                )

            except MassiveTransportError:
                raise
            except HTTPError as exc:
                failure = exc
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                message = f"Massive grouped daily returned HTTP {exc.code}"
            except (URLError, TimeoutError) as exc:
                failure = exc
                retryable = True
                detail = exc.reason if isinstance(exc, URLError) else exc
                message = f"Massive grouped daily transport failure: {detail}"

            if not retryable or attempt == self._max_attempts:
                raise MassiveTransportError(
                    message,
                    retryable=retryable,
                    attempts=attempt,
                ) from failure

            self._sleeper(self._base_backoff_seconds * (2 ** (attempt - 1)))

        raise AssertionError("unreachable")


def _sleep(seconds: float) -> None:
    from time import sleep

    sleep(seconds)


def _open_url(request: Request, timeout: float) -> _Response:
    """Keep urllib's optional request body separate from timeout on all platforms."""

    return urlopen(request, timeout=timeout)
