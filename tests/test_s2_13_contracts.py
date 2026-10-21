from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.application.identity import IdentityStatus, resolve_symbol_identity
from app.application.ingestion import IngestionResult, IngestionStage, IngestionStatus
from app.domain.models import SymbolAlias
from app.infrastructure.storage.sqlite import (
    SQLiteIngestionResultRepository,
    SQLiteStore,
    SQLiteSymbolAliasRepository,
)


def _time(hour: int = 12) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=UTC)


def _alias(*, version: int = 1, available_at: datetime | None = None, valid_to=None) -> SymbolAlias:
    available = available_at or _time()
    return SymbolAlias(
        instrument_id="inst-aapl",
        symbol="AAPL",
        valid_from=_time(8),
        valid_to=valid_to,
        event_time=_time(8),
        source_timestamp=_time(9),
        received_at=_time(10),
        processed_at=_time(11),
        available_at=available,
        provider="nasdaq",
        feed="symbol_directory",
        version=version,
    )


def _result(*, result_id="result-1", status=IngestionStatus.QUARANTINED) -> IngestionResult:
    return IngestionResult(
        result_id=result_id,
        provider="nasdaq",
        feed="symbol_directory",
        source_name="nasdaqlisted.txt",
        stage=IngestionStage.IDENTITY,
        status=status,
        reason_code="PENDING_IDENTITY",
        sha256="a" * 64,
        raw_path="raw/nasdaq/symbol_directory/a.raw",
        source_timestamp=None,
        received_at=_time(10),
        processed_at=_time(11),
        available_at=_time(12),
        record_count=3,
    )


def test_003_creates_alias_and_ingestion_result_tables(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"symbol_alias_versions", "ingestion_results"}.issubset(tables)


def test_alias_is_idempotent_and_available_at_controls_pit_read(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = SQLiteSymbolAliasRepository(store)
    alias = _alias(available_at=_time(12))
    assert repo.save(alias) is True
    assert repo.save(alias) is False
    assert repo.scan_as_of("nasdaq", "symbol_directory", _time(11)) == ()
    assert repo.scan_as_of("nasdaq", "symbol_directory", _time(12)) == (alias,)


def test_later_alias_revision_cannot_rewrite_prior_pit_result(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = SQLiteSymbolAliasRepository(store)
    first = _alias(available_at=_time(12), valid_to=None)
    revision = _alias(version=2, available_at=_time(14), valid_to=_time(16))
    repo.save(first)
    repo.save(revision)
    assert repo.scan_as_of("nasdaq", "symbol_directory", _time(13)) == (first,)
    assert repo.scan_as_of("nasdaq", "symbol_directory", _time(14)) == (revision,)


def test_persisted_alias_can_resolve_identity_after_restart(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    SQLiteSymbolAliasRepository(store).save(_alias())
    aliases = SQLiteSymbolAliasRepository(store).scan_as_of("nasdaq", "symbol_directory", _time())
    resolved = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=_time(),
        query_time=_time(),
        aliases=aliases,
    )
    assert resolved.status == IdentityStatus.RESOLVED
    assert resolved.instrument_id == "inst-aapl"


def test_alias_same_version_conflict_is_rejected(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = SQLiteSymbolAliasRepository(store)
    repo.save(_alias())
    with pytest.raises(ValueError, match="conflict"):
        repo.save(_alias(valid_to=_time(16)))


def test_ingestion_result_is_immutable_and_idempotent(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = SQLiteIngestionResultRepository(store)
    result = _result()
    assert repo.save(result) is True
    assert repo.save(result) is False
    with pytest.raises(ValueError, match="conflict"):
        repo.save(_result(status=IngestionStatus.FAILED))


def test_failed_fetch_needs_no_raw_artifact(settings):
    result = IngestionResult(
        result_id="fetch-failed",
        provider="nasdaq",
        feed="symbol_directory",
        source_name="nasdaqlisted.txt",
        stage=IngestionStage.FETCH,
        status=IngestionStatus.FAILED,
        reason_code="NETWORK_TIMEOUT",
        sha256=None,
        raw_path=None,
        source_timestamp=None,
        received_at=_time(10),
        processed_at=_time(11),
        available_at=_time(11),
        record_count=None,
    )
    assert result.status == IngestionStatus.FAILED


def test_result_rejects_partial_raw_reference():
    with pytest.raises(ValueError, match="together"):
        replace(_result(), raw_path=None)
