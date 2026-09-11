from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime
from typing import Protocol, TypeVar, runtime_checkable

from app.domain.models import (
    ActualityEvent,
    CanonicalBar,
    CanonicalQuote,
    CanonicalTrade,
    Instrument,
)

T = TypeVar("T")


@runtime_checkable
class PointInTimeRepository(Protocol[T]):
    """Generic Point-in-Time (PIT) repository contract.

    Temporal rules:
    - as_of MUST be timezone-aware (normalized internally to UTC).
    - Generic historical eligibility is determined strictly by:
          available_at <= as_of
    - The boundary is inclusive: available_at == as_of is visible.
    - event_time MUST NOT be introduced as a generic eligibility filter.
    - Audit timestamps (received_at, processed_at) do not determine eligibility.
    - Later revisions (available_at > as_of) remain invisible to earlier queries.
    - No silent fallback to current state or unrestricted get_latest().
    """

    def get_as_of(self, identifier: str, as_of: datetime) -> T | None:
        """Return the deterministic latest revision for the entity eligible at as_of."""
        ...

    def scan_as_of(self, as_of: datetime) -> Sequence[T]:
        """Return only records eligible at as_of (available_at <= as_of)."""
        ...

    def latest_available(self, identifier: str, as_of: datetime) -> T | None:
        """Return the latest eligible revision known at as_of (available_at <= as_of)."""
        ...


class InstrumentStore(Protocol):
    def save(self, instrument: Instrument) -> bool: ...
    def get_as_of(self, symbol: str, as_of: datetime) -> Instrument | None: ...


class MarketDataProvider(Protocol):
    async def get_daily_market(self, session: date) -> list[CanonicalBar]: ...

    async def get_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str
    ) -> list[CanonicalBar]: ...

    def stream(
        self, symbols: frozenset[str], channels: frozenset[str]
    ) -> AsyncIterator[CanonicalBar | CanonicalQuote | CanonicalTrade]: ...


class ActualityProvider(Protocol):
    async def fetch_since(
        self, since: datetime, entities: tuple[str, ...]
    ) -> list[ActualityEvent]: ...
