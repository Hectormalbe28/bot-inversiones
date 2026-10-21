"""Manual, read-only commands for locally persisted research evidence."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol, TextIO

from app.core.clock import require_utc
from app.domain.models import HistoricalUniverseSnapshot


class HistoricalUniverseReader(Protocol):
    def get_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> HistoricalUniverseSnapshot | None: ...


class NasdaqDownloader(Protocol):
    def fetch(self): ...


class NasdaqIngestor(Protocol):
    def ingest(self, **kwargs): ...


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and require its explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of must be a valid ISO-8601 timestamp") from exc
    return require_utc(parsed)


def show_historical_universe(
    *,
    provider: str,
    feed: str,
    as_of: str,
    repository: HistoricalUniverseReader,
    output: TextIO,
) -> int:
    """Print exactly one eligible snapshot, never triggering a refresh."""
    query_time = parse_utc(as_of)
    snapshot = repository.get_as_of(provider, feed, query_time)
    if snapshot is None:
        output.write("No historical universe snapshot available at the requested as_of.\n")
        return 3
    output.write(json.dumps(snapshot.model_dump(mode="json"), sort_keys=True) + "\n")
    return 0


def run_universe_show(
    args: Sequence[str],
    *,
    repository_factory: Callable[[], HistoricalUniverseReader],
    output: TextIO,
) -> int:
    """Small argument boundary kept separate from the server entry point."""
    if len(args) != 6 or args[0] != "--provider" or args[2] != "--feed" or args[4] != "--as-of":
        output.write("Usage: universe show --provider PROVIDER --feed FEED --as-of ISO-8601\n")
        return 2
    try:
        return show_historical_universe(
            provider=args[1],
            feed=args[3],
            as_of=args[5],
            repository=repository_factory(),
            output=output,
        )
    except ValueError as exc:
        output.write(f"Invalid universe query: {exc}\n")
        return 2


def refresh_nasdaq_universe(
    *,
    effective_time: str,
    source_timestamp: str,
    downloader: NasdaqDownloader,
    ingestor: NasdaqIngestor,
    clock: Callable[[], datetime],
    output: TextIO,
) -> int:
    """Acquire once, then submit bytes to the canonical pipeline with explicit cuts."""
    effective = parse_utc(effective_time)
    source = parse_utc(source_timestamp)
    download = downloader.fetch()
    processed = require_utc(clock())
    if download.received_at > processed:
        raise ValueError("clock cannot precede the transport received_at timestamp")
    outcome = ingestor.ingest(
        raw=download.raw,
        source_name="nasdaqlisted.txt",
        effective_time=effective,
        source_timestamp=source,
        received_at=download.received_at,
        processed_at=processed,
        available_at=processed,
    )
    output.write(
        json.dumps(
            {
                "disposition": str(outcome.disposition),
                "ingestion_id": outcome.ingestion_id,
                "snapshot_id": outcome.snapshot_id,
                "reason_code": outcome.reason_code,
                "operational_universe": (
                    {
                        "policy_id": "nasdaq-operational-conservative",
                        "policy_version": 1,
                        "included_instrument_ids": (
                            outcome.operational_universe.included_instrument_ids
                        ),
                    }
                    if outcome.operational_universe
                    else None
                ),
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if str(outcome.disposition) == "SNAPSHOT_PERSISTED" else 4
