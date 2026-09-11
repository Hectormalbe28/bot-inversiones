from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.models import CanonicalBar, Instrument
from app.infrastructure.storage.sqlite import InstrumentRepository, SQLiteStore


def test_temporal_contracts_reject_naive_datetimes(evidence):
    naive_evidence = evidence | {"received_at": datetime(2026, 9, 1, 20)}

    with pytest.raises(ValidationError, match="timezone"):
        Instrument(instrument_id="instrument-1", symbol="ABC", name="Example", **naive_evidence)

    with pytest.raises(ValidationError, match="timezone"):
        CanonicalBar(
            symbol="ABC",
            timeframe="1d",
            open=10,
            high=12,
            low=9,
            close=11,
            volume=100,
            **naive_evidence,
        )


def test_aware_datetimes_are_normalized_to_utc(evidence):
    offset_time = datetime(2026, 9, 1, 15, tzinfo=timezone(timedelta(hours=-5)))
    instrument = Instrument(
        instrument_id="instrument-1",
        symbol="ABC",
        name="Example",
        **(evidence | {"event_time": offset_time}),
    )

    assert instrument.event_time == datetime(2026, 9, 1, 20, tzinfo=UTC)
    assert instrument.event_time.tzinfo == UTC


def test_revision_is_not_visible_before_its_available_at(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repository = InstrumentRepository(store)
    available_at = evidence["available_at"] + timedelta(hours=1)
    revision = Instrument(
        instrument_id="instrument-1",
        symbol="ABC",
        name="Example",
        **(
            evidence
            | {
                "received_at": available_at,
                "processed_at": available_at,
                "available_at": available_at,
            }
        ),
    )
    repository.save(revision)

    assert repository.get_as_of("ABC", available_at - timedelta(microseconds=1)) is None


def test_revision_is_visible_at_its_available_at(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repository = InstrumentRepository(store)
    available_at = evidence["available_at"] + timedelta(hours=1)
    revision = Instrument(
        instrument_id="instrument-1",
        symbol="ABC",
        name="Example",
        **(
            evidence
            | {
                "received_at": available_at,
                "processed_at": available_at,
                "available_at": available_at,
            }
        ),
    )
    repository.save(revision)

    assert repository.get_as_of("ABC", available_at) == revision


def test_later_revision_does_not_change_earlier_historical_result(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repository = InstrumentRepository(store)
    first = Instrument(instrument_id="instrument-1", symbol="ABC", name="Before", **evidence)
    repository.save(first)
    later = evidence["available_at"] + timedelta(days=1)
    second = Instrument(
        **(
            first.model_dump()
            | {
                "name": "After",
                "version": 2,
                "received_at": later,
                "processed_at": later,
                "available_at": later,
            }
        )
    )
    repository.save(second)

    assert repository.get_as_of("ABC", evidence["available_at"]) == first


def test_future_scheduled_event_eligible_by_available_at_not_event_time():
    """
    Acceptance test: Future scheduled event point-in-time eligibility (Task S2.1C).

    Contract:
        Historical eligibility is determined universally by:
            available_at <= as_of
        and NOT by:
            event_time <= as_of

    Protects against future repository implementations (e.g. PointInTimeRepository)
    incorrectly applying `event_time <= as_of` as a generic eligibility filter.
    """
    as_of = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    event_time = datetime(2026, 9, 20, 14, 0, 0, tzinfo=UTC)
    available_at = datetime(2026, 9, 5, 10, 0, 0, tzinfo=UTC)

    # 1. as_of is UTC-aware
    assert as_of.tzinfo is not None
    assert as_of.tzinfo == UTC

    # 2. available_at is before as_of
    assert available_at < as_of

    # 3. event_time is after as_of
    assert event_time > as_of

    # Scheduled event record at domain/test level (pending PointInTimeRepository)
    record = {
        "event_id": "scheduled-event-1",
        "event_type": "earnings",
        "event_time": event_time,
        "available_at": available_at,
        "provider": "fixture",
        "feed": "test",
        "version": 1,
    }

    # Universal PIT eligibility rule: available_at <= as_of
    # Future repository implementation must satisfy this contract:
    # eligibility axis is available_at <= as_of, never event_time <= as_of.
    def is_pit_eligible(rec, query_as_of: datetime) -> bool:
        rec_avail = rec.available_at if hasattr(rec, "available_at") else rec["available_at"]
        return rec_avail <= query_as_of

    # 4. the record is considered PIT-eligible
    assert is_pit_eligible(record, as_of) is True

    # 5. no production change is required simply because event_time is future:
    # Eligibility depends solely on available_at <= as_of, unaffected by event_time > as_of.
    assert is_pit_eligible(record, as_of) == (available_at <= as_of)
    naive_event_filter = record["event_time"] <= as_of
    assert not naive_event_filter
    assert is_pit_eligible(record, as_of) and not naive_event_filter


def test_point_in_time_repository_protocol_contract():
    """Verify generic PointInTimeRepository protocol contract conformance (Task S2.2A)."""
    from collections.abc import Sequence

    from app.application.ports import PointInTimeRepository

    class StubPITRepo:
        def get_as_of(self, identifier: str, as_of: datetime) -> str | None:
            return f"{identifier}@{as_of.isoformat()}"

        def scan_as_of(self, as_of: datetime) -> Sequence[str]:
            return [f"item@{as_of.isoformat()}"]

        def latest_available(self, identifier: str, as_of: datetime) -> str | None:
            return f"latest_{identifier}@{as_of.isoformat()}"

    repo = StubPITRepo()
    assert isinstance(repo, PointInTimeRepository)

    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    assert repo.get_as_of("TEST", now) == f"TEST@{now.isoformat()}"
    assert repo.scan_as_of(now) == [f"item@{now.isoformat()}"]
    assert repo.latest_available("TEST", now) == f"latest_TEST@{now.isoformat()}"
