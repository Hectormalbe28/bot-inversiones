import inspect
from datetime import UTC, datetime

from app.application.ports import HistoricalUniverseRepository
from app.domain.models import HistoricalUniverseSnapshot


class StubHistoricalUniverseRepository:
    def get_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> HistoricalUniverseSnapshot | None:
        if provider == "missing" or feed == "missing":
            return None
        return None if query_time.year < 2026 else _snapshot(instrument_ids=())

    def members_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> tuple[str, ...] | None:
        snapshot = self.get_as_of(provider, feed, query_time)
        if snapshot is None:
            return None
        return snapshot.instrument_ids


def _snapshot(*, instrument_ids: tuple[str, ...]) -> HistoricalUniverseSnapshot:
    instant = datetime(2026, 6, 30, tzinfo=UTC)
    return HistoricalUniverseSnapshot(
        snapshot_id="snap-empty",
        as_of=instant,
        instrument_ids=instrument_ids,
        event_time=instant,
        source_timestamp=instant,
        received_at=instant,
        processed_at=instant,
        available_at=instant,
        provider="nasdaq",
        feed="listed",
        version=1,
    )


def test_historical_universe_repository_is_structurally_implementable():
    repo = StubHistoricalUniverseRepository()
    assert isinstance(repo, HistoricalUniverseRepository)


def test_historical_universe_repository_exposes_required_methods():
    assert hasattr(HistoricalUniverseRepository, "get_as_of")
    assert hasattr(HistoricalUniverseRepository, "members_as_of")


def test_historical_universe_repository_requires_explicit_provider_feed_query_time():
    for method_name in ("get_as_of", "members_as_of"):
        parameters = inspect.signature(
            getattr(HistoricalUniverseRepository, method_name)
        ).parameters
        assert tuple(parameters) == ("self", "provider", "feed", "query_time")


def test_get_as_of_can_represent_none():
    repo = StubHistoricalUniverseRepository()
    query_time = datetime(2026, 7, 1, tzinfo=UTC)
    assert repo.get_as_of("missing", "listed", query_time) is None
    assert repo.get_as_of("nasdaq", "missing", query_time) is None


def test_members_as_of_distinguishes_none_from_empty_tuple():
    repo = StubHistoricalUniverseRepository()
    no_snapshot = repo.members_as_of("nasdaq", "listed", datetime(2025, 1, 1, tzinfo=UTC))
    empty_snapshot = repo.members_as_of("nasdaq", "listed", datetime(2026, 7, 1, tzinfo=UTC))
    assert no_snapshot is None
    assert empty_snapshot == ()
    assert no_snapshot != empty_snapshot
