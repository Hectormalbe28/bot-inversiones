from datetime import UTC, datetime
from io import StringIO

from app.cli import run_universe_show, show_historical_universe
from app.domain.models import HistoricalUniverseSnapshot
from app.infrastructure.providers.nasdaq_ingestion import (
    NasdaqIngestionDisposition,
    NasdaqUniverseIngestionOutcome,
)


class _Reader:
    def __init__(self, snapshot: HistoricalUniverseSnapshot | None) -> None:
        self.snapshot = snapshot
        self.calls = []

    def get_as_of(self, provider: str, feed: str, query_time: datetime):
        self.calls.append((provider, feed, query_time))
        return self.snapshot


def _snapshot() -> HistoricalUniverseSnapshot:
    timestamp = datetime(2026, 10, 17, 12, tzinfo=UTC)
    return HistoricalUniverseSnapshot(
        snapshot_id="fixture-snapshot",
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


def test_manual_cli_prints_only_the_repository_selected_snapshot():
    output = StringIO()
    reader = _Reader(_snapshot())

    result = show_historical_universe(
        provider="nasdaq",
        feed="symbol_directory",
        as_of="2026-10-17T12:00:00Z",
        repository=reader,
        output=output,
    )

    assert result == 0
    assert '"snapshot_id": "fixture-snapshot"' in output.getvalue()
    assert reader.calls == [("nasdaq", "symbol_directory", datetime(2026, 10, 17, 12, tzinfo=UTC))]


def test_manual_cli_does_not_refresh_when_snapshot_is_unavailable():
    output = StringIO()

    result = run_universe_show(
        ["--provider", "nasdaq", "--feed", "symbol_directory", "--as-of", "2026-10-17T12:00:00Z"],
        repository_factory=lambda: _Reader(None),
        output=output,
    )

    assert result == 3
    assert "No historical universe snapshot" in output.getvalue()


def test_manual_refresh_uses_explicit_cuts_and_reports_quarantine_without_retrying():
    class Downloader:
        def fetch(self):
            return type(
                "Download",
                (),
                {"raw": b"raw", "received_at": datetime(2026, 10, 17, 12, tzinfo=UTC)},
            )()

    class Ingestor:
        def __init__(self) -> None:
            self.kwargs = None

        def ingest(self, **kwargs):
            self.kwargs = kwargs
            return NasdaqUniverseIngestionOutcome(
                NasdaqIngestionDisposition.QUARANTINED, "ing-1", None, "PENDING_IDENTITY"
            )

    output = StringIO()
    ingestor = Ingestor()
    from app.cli import refresh_nasdaq_universe

    result = refresh_nasdaq_universe(
        effective_time="2026-10-17T00:00:00Z",
        source_timestamp="2026-10-17T01:00:00Z",
        downloader=Downloader(),
        ingestor=ingestor,
        clock=lambda: datetime(2026, 10, 17, 13, tzinfo=UTC),
        output=output,
    )

    assert result == 4
    assert ingestor.kwargs["effective_time"] == datetime(2026, 10, 17, tzinfo=UTC)
    assert ingestor.kwargs["source_timestamp"] == datetime(2026, 10, 17, 1, tzinfo=UTC)
    assert "PENDING_IDENTITY" in output.getvalue()
