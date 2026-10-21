from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.routes import get_historical_universe
from app.domain.models import HistoricalUniverseSnapshot


class _UniverseStore:
    def __init__(self, snapshot: HistoricalUniverseSnapshot | None) -> None:
        self.snapshot = snapshot
        self.calls = []

    def get_as_of(self, provider: str, feed: str, query_time: datetime):
        self.calls.append((provider, feed, query_time))
        return self.snapshot


def _snapshot() -> HistoricalUniverseSnapshot:
    timestamp = datetime(2026, 10, 17, 12, tzinfo=UTC)
    return HistoricalUniverseSnapshot(
        snapshot_id="nasdaq:symbol_directory:fixture",
        provider="nasdaq",
        feed="symbol_directory",
        version=1,
        as_of=timestamp,
        event_time=timestamp,
        source_timestamp=timestamp,
        received_at=timestamp,
        processed_at=timestamp,
        available_at=timestamp,
        instrument_ids=("inst-aapl",),
    )


def test_historical_universe_endpoint_returns_only_repository_selected_snapshot():
    store = _UniverseStore(_snapshot())

    response = get_historical_universe(
        provider="nasdaq",
        feed="symbol_directory",
        as_of=datetime(2026, 10, 17, 12, tzinfo=UTC),
        repository=store,
    )

    assert response.instrument_ids == ("inst-aapl",)
    assert store.calls == [("nasdaq", "symbol_directory", datetime(2026, 10, 17, 12, tzinfo=UTC))]


def test_historical_universe_endpoint_returns_404_without_eligible_snapshot():
    with pytest.raises(HTTPException) as raised:
        get_historical_universe(
            provider="nasdaq",
            feed="symbol_directory",
            as_of=datetime(2026, 10, 17, 12, tzinfo=UTC),
            repository=_UniverseStore(None),
        )

    assert raised.value.status_code == 404
