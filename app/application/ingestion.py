"""Immutable outcomes for the canonical ingestion pipeline."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.clock import require_utc


class IngestionStage(StrEnum):
    FETCH = "FETCH"
    PARSE = "PARSE"
    NORMALIZE = "NORMALIZE"
    IDENTITY = "IDENTITY"
    QUALITY = "QUALITY"
    SNAPSHOT = "SNAPSHOT"


class IngestionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """One immutable, auditable terminal result from an ingestion attempt stage."""

    result_id: str
    provider: str
    feed: str
    source_name: str
    stage: IngestionStage
    status: IngestionStatus
    reason_code: str | None
    sha256: str | None
    raw_path: str | None
    source_timestamp: datetime | None
    received_at: datetime
    processed_at: datetime
    available_at: datetime
    record_count: int | None

    def __post_init__(self) -> None:
        if not self.result_id:
            raise ValueError("result_id is mandatory")
        if not self.provider or not self.feed or not self.source_name:
            raise ValueError("provider, feed, and source_name are mandatory")
        if (self.sha256 is None) != (self.raw_path is None):
            raise ValueError("sha256 and raw_path must be provided together")
        if self.sha256 is not None and (
            len(self.sha256) != 64 or not all(c in "0123456789abcdef" for c in self.sha256.lower())
        ):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        if self.record_count is not None and self.record_count < 0:
            raise ValueError("record_count must be non-negative")
        source_timestamp = (
            require_utc(self.source_timestamp) if self.source_timestamp is not None else None
        )
        received_at = require_utc(self.received_at)
        processed_at = require_utc(self.processed_at)
        available_at = require_utc(self.available_at)
        if received_at > processed_at or processed_at > available_at:
            raise ValueError("Require received_at <= processed_at <= available_at")
        if source_timestamp is not None and source_timestamp > available_at:
            raise ValueError("source_timestamp must be <= available_at")
        object.__setattr__(self, "source_timestamp", source_timestamp)
        object.__setattr__(self, "received_at", received_at)
        object.__setattr__(self, "processed_at", processed_at)
        object.__setattr__(self, "available_at", available_at)
