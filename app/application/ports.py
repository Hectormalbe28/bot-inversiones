from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime
from typing import Protocol, TypeVar, runtime_checkable

from app.domain.models import (
    ActualityEvent,
    CanonicalBar,
    CanonicalQuote,
    CanonicalTrade,
    HistoricalUniverseSnapshot,
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


@runtime_checkable
class HistoricalUniverseRepository(Protocol):
    """Application-layer contract for historical universe read resolution.

    This is not a PointInTimeRepository specialization. Universe membership has two
    independent temporal axes; collapsing them into available_at <= as_of would hide
    effective-time eligibility.

    Knowledge axis (universal PIT rule, unchanged globally):
        available_at <= query_time

    Effective axis (historical-universe specific):
        snapshot.as_of <= query_time

    A snapshot is usable at decision time T only if both conditions hold (inclusive).

    Scope is always explicit provider and feed. Implementations must not guess,
    combine, or reconcile sources.

    Among eligible snapshots for the same provider/feed, selection is deterministic:
        as_of DESC, available_at DESC, version DESC, snapshot_id ASC

    event_time, received_at, and processed_at are neither eligibility filters nor
    revision-priority keys.

    query_time must be timezone-aware. Naïve datetimes are rejected. Aware non-UTC
    values are normalized with require_utc from app.core.clock.

    No current-universe fallback: if no snapshot is both known and effective at
    query_time, get_as_of returns None. members_as_of returns None in that case
    and () when an eligible snapshot exists with empty instrument_ids. Those
    states must remain distinguishable.

    Membership identity is instrument_id, never symbol.
    """

    def get_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> HistoricalUniverseSnapshot | None:
        """Return the unique deterministic snapshot known and effective at query_time."""
        ...

    def members_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> tuple[str, ...] | None:
        """Return instrument_ids of the resolved snapshot, or None if none is eligible."""
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
