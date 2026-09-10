from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Protocol

from app.domain.models import (
    ActualityEvent,
    CanonicalBar,
    CanonicalQuote,
    CanonicalTrade,
    Instrument,
)


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
