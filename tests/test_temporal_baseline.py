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
