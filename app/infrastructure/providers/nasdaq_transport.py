"""Explicit HTTPS transport for the official Nasdaq Symbol Directory.

The client only acquires bytes.  It deliberately does not parse files, choose an
``as_of`` timestamp, or trigger ingestion: those decisions remain explicit in the
offline canonical pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.clock import require_utc, utc_now

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"


class _Response(Protocol):
    def read(self) -> bytes: ...

    def getcode(self) -> int | None: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: object) -> None: ...


UrlOpener = Callable[[Request, float], _Response]


class NasdaqTransportError(Exception):
    """A terminal error while acquiring the Nasdaq directory."""

    def __init__(self, message: str, *, retryable: bool, attempts: int) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class NasdaqDownload:
    raw: bytes
    source_url: str
    received_at: datetime
    attempts: int


class NasdaqSymbolDirectoryHttpClient:
    """Fetch ``nasdaqlisted.txt`` with bounded retries for transient failures."""

    def __init__(
        self,
        *,
        url: str = NASDAQ_LISTED_URL,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.25,
        opener: UrlOpener = urlopen,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not url.startswith("https://"):
            raise ValueError("Nasdaq Symbol Directory transport requires an HTTPS URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds cannot be negative")

        self._url = url
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._opener = opener
        self._sleeper = sleeper or _sleep
        self._clock = clock

    def fetch(self) -> NasdaqDownload:
        """Download raw provider bytes without applying domain interpretation."""
        request = Request(
            self._url,
            headers={"User-Agent": "bot-inversiones/0.1 research-client", "Accept": "text/plain"},
        )
        for attempt in range(1, self._max_attempts + 1):
            failure: Exception | None = None
            try:
                with self._opener(request, self._timeout_seconds) as response:
                    status = response.getcode() or 200
                    if status >= 400:
                        raise HTTPError(self._url, status, "HTTP failure", None, None)
                    raw = response.read()
                if not raw:
                    raise NasdaqTransportError(
                        "Nasdaq Symbol Directory returned an empty payload",
                        retryable=False,
                        attempts=attempt,
                    )
                return NasdaqDownload(raw, self._url, require_utc(self._clock()), attempt)
            except HTTPError as exc:
                failure = exc
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                message = f"Nasdaq Symbol Directory returned HTTP {exc.code}"
            except (URLError, TimeoutError) as exc:
                failure = exc
                retryable = True
                detail = exc.reason if isinstance(exc, URLError) else exc
                message = f"Nasdaq Symbol Directory transport failure: {detail}"

            if not retryable or attempt == self._max_attempts:
                raise NasdaqTransportError(
                    message, retryable=retryable, attempts=attempt
                ) from failure
            self._sleeper(self._base_backoff_seconds * (2 ** (attempt - 1)))

        raise AssertionError("unreachable")


def _sleep(seconds: float) -> None:
    # Lazy import keeps the deterministic test seam in the constructor obvious.
    from time import sleep

    sleep(seconds)
