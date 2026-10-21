from datetime import UTC, datetime

from app.domain.models import Instrument, InstrumentVersion, SymbolAlias
from app.infrastructure.providers.nasdaq_ingestion import (
    NasdaqIngestionDisposition,
    NasdaqUniverseIngestionService,
)
from app.infrastructure.storage.raw import RawIngestionStore
from app.infrastructure.storage.sqlite import (
    InstrumentRepository,
    SQLiteHistoricalUniverseRepository,
    SQLiteHistoricalUniverseWriteRepository,
    SQLiteIngestionResultRepository,
    SQLiteInstrumentVersionRepository,
    SQLiteStore,
    SQLiteSymbolAliasRepository,
)

RAW = (
    b"Symbol|Security Name|Market Category|Test Issue|Financial Status|"
    b"Round Lot Size|ETF|NextShares\n"
    b"AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
    b"File Creation Time: 1016202612:00|||||||\n"
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 10, 16, hour, tzinfo=UTC)


def _service(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    aliases = SQLiteSymbolAliasRepository(store)
    return (
        store,
        aliases,
        NasdaqUniverseIngestionService(
            raw_store=RawIngestionStore(raw_root=settings.artifact_dir / "raw", sqlite_store=store),
            aliases=aliases,
            instrument_versions=SQLiteInstrumentVersionRepository(store),
            universe_writer=SQLiteHistoricalUniverseWriteRepository(store),
            results=SQLiteIngestionResultRepository(store),
        ),
    )


def _seed_identity(store, aliases):
    evidence = dict(
        event_time=_dt(8),
        source_timestamp=_dt(9),
        received_at=_dt(10),
        processed_at=_dt(11),
        available_at=_dt(12),
        provider="nasdaq",
        feed="symbol_directory",
        version=1,
    )
    InstrumentRepository(store).save(
        Instrument(instrument_id="inst-aapl", symbol="AAPL", name="Apple Inc.", **evidence)
    )
    SQLiteInstrumentVersionRepository(store).save(
        InstrumentVersion(instrument_id="inst-aapl", symbol="AAPL", valid_from=_dt(8), **evidence)
    )
    aliases.save(
        SymbolAlias(instrument_id="inst-aapl", symbol="AAPL", valid_from=_dt(8), **evidence)
    )


def _ingest(service, raw=RAW):
    return service.ingest(
        raw=raw,
        source_name="nasdaqlisted.txt",
        effective_time=_dt(12),
        source_timestamp=_dt(9),
        received_at=_dt(10),
        processed_at=_dt(11),
        available_at=_dt(12),
    )


def test_complete_identity_persists_snapshot_and_is_idempotent(settings):
    store, aliases, service = _service(settings)
    _seed_identity(store, aliases)
    first = _ingest(service)
    second = _ingest(service)
    assert first.disposition == NasdaqIngestionDisposition.SNAPSHOT_PERSISTED
    assert second.snapshot_id == first.snapshot_id
    snapshot = SQLiteHistoricalUniverseRepository(store).get_as_of(
        "nasdaq", "symbol_directory", _dt(12)
    )
    assert snapshot is not None
    assert snapshot.instrument_ids == ("inst-aapl",)


def test_unresolved_identity_is_quarantined_without_snapshot(settings):
    store, _, service = _service(settings)
    outcome = _ingest(service)
    assert outcome.disposition == NasdaqIngestionDisposition.QUARANTINED
    assert outcome.reason_code == "PENDING_IDENTITY"
    assert (
        SQLiteHistoricalUniverseRepository(store).get_as_of("nasdaq", "symbol_directory", _dt(12))
        is None
    )


def test_malformed_file_is_saved_and_reports_parse_failure(settings):
    store, _, service = _service(settings)
    outcome = _ingest(service, raw=b"not a Nasdaq directory")
    assert outcome.disposition == NasdaqIngestionDisposition.FAILED
    assert outcome.reason_code == "PARSE_ERROR"
    with store.connection() as conn:
        assert conn.execute("SELECT count(*) FROM source_ingestions").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM ingestion_results").fetchone()[0] == "FAILED"
