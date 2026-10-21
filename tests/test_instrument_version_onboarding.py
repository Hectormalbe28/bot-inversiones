import sqlite3
from datetime import UTC, datetime

import pytest

from app.domain.models import Instrument, InstrumentVersion
from app.infrastructure.storage.sqlite import (
    InstrumentRepository,
    SQLiteInstrumentVersionRepository,
    SQLiteStore,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=UTC)


def _instrument(version: int = 1) -> Instrument:
    return Instrument(
        instrument_id="inst-aapl",
        symbol="AAPL",
        name="Apple Inc.",
        event_time=_dt(8),
        source_timestamp=_dt(9),
        received_at=_dt(10),
        processed_at=_dt(11),
        available_at=_dt(12),
        provider="nasdaq",
        feed="symbol_directory",
        version=version,
    )


def _version(version: int = 1, *, valid_from=None, valid_to=None) -> InstrumentVersion:
    return InstrumentVersion(
        instrument_id="inst-aapl",
        symbol="AAPL",
        valid_from=valid_from or _dt(8),
        valid_to=valid_to,
        event_time=_dt(8),
        source_timestamp=_dt(9),
        received_at=_dt(10),
        processed_at=_dt(11),
        available_at=_dt(12),
        provider="nasdaq",
        feed="symbol_directory",
        version=version,
    )


def test_version_requires_explicit_base_instrument(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with pytest.raises(sqlite3.IntegrityError):
        SQLiteInstrumentVersionRepository(store).save(_version())


def test_version_is_idempotent_and_resolves_with_two_pit_axes(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    InstrumentRepository(store).save(_instrument())
    repo = SQLiteInstrumentVersionRepository(store)
    record = _version(valid_to=_dt(16))
    assert repo.save(record) is True
    assert repo.save(record) is False
    assert repo.get_as_of("inst-aapl", "nasdaq", "symbol_directory", _dt(14), _dt(11)) is None
    assert repo.get_as_of("inst-aapl", "nasdaq", "symbol_directory", _dt(14), _dt(12)) == record
    assert repo.get_as_of("inst-aapl", "nasdaq", "symbol_directory", _dt(16), _dt(16)) is None


def test_overlapping_effective_versions_are_rejected(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    instruments = InstrumentRepository(store)
    instruments.save(_instrument(1))
    instruments.save(_instrument(2))
    repo = SQLiteInstrumentVersionRepository(store)
    repo.save(_version(1, valid_to=_dt(16)))
    with pytest.raises(ValueError, match="overlap"):
        repo.save(_version(2, valid_from=_dt(15)))
