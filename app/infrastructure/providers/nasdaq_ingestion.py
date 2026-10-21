"""Offline canonical ingestion for a Nasdaq Symbol Directory payload.

This adapter deliberately has no HTTP client. Callers supply raw bytes and explicit UTC
evidence timestamps; a later increment owns acquisition and transport retries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.identity import build_identity_persistence_gate
from app.application.ingestion import IngestionResult, IngestionStage, IngestionStatus
from app.application.operational_universe import (
    CONSERVATIVE_NASDAQ_OPERATIONAL_POLICY,
    OperationalUniverseCandidate,
    OperationalUniverseResult,
    derive_operational_universe,
)
from app.application.universe import HistoricalUniverseMemberRef
from app.domain.models import HistoricalUniverseSnapshot
from app.infrastructure.providers.nasdaq import (
    NasdaqSymbolDirectoryError,
    normalize_nasdaqlisted,
    parse_nasdaqlisted,
    resolve_nasdaq_identities,
)
from app.infrastructure.providers.nasdaq_quality import NasdaqQualityReport, assess_nasdaq_quality
from app.infrastructure.storage.raw import RawIngestionStore
from app.infrastructure.storage.sqlite import (
    SQLiteHistoricalUniverseWriteRepository,
    SQLiteIngestionResultRepository,
    SQLiteInstrumentVersionRepository,
    SQLiteSymbolAliasRepository,
)


class NasdaqIngestionDisposition(StrEnum):
    SNAPSHOT_PERSISTED = "SNAPSHOT_PERSISTED"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class NasdaqUniverseIngestionOutcome:
    disposition: NasdaqIngestionDisposition
    ingestion_id: str | None
    snapshot_id: str | None
    reason_code: str | None
    quality: NasdaqQualityReport | None = None
    operational_universe: OperationalUniverseResult | None = None


class NasdaqUniverseIngestionService:
    """Orchestrates validated raw bytes through the canonical offline pipeline."""

    provider = "nasdaq"
    feed = "symbol_directory"

    def __init__(
        self,
        *,
        raw_store: RawIngestionStore,
        aliases: SQLiteSymbolAliasRepository,
        instrument_versions: SQLiteInstrumentVersionRepository,
        universe_writer: SQLiteHistoricalUniverseWriteRepository,
        results: SQLiteIngestionResultRepository,
    ) -> None:
        self._raw_store = raw_store
        self._aliases = aliases
        self._instrument_versions = instrument_versions
        self._universe_writer = universe_writer
        self._results = results

    def ingest(
        self,
        *,
        raw: bytes,
        source_name: str,
        effective_time: datetime,
        source_timestamp: datetime,
        received_at: datetime,
        processed_at: datetime,
        available_at: datetime,
        snapshot_version: int = 1,
    ) -> NasdaqUniverseIngestionOutcome:
        """Process one supplied Nasdaq file without making network calls.

        The provider timestamp is intentionally supplied by the caller. This adapter does
        not interpret Nasdaq's raw footer timestamp until its timezone contract is explicit.
        """
        try:
            parsed = parse_nasdaqlisted(raw)
        except NasdaqSymbolDirectoryError:
            stored = self._store_raw(
                raw=raw,
                source_name=source_name,
                source_timestamp=source_timestamp,
                received_at=received_at,
                processed_at=processed_at,
                available_at=available_at,
                record_count=0,
            )
            self._save_result(
                result_id=self._result_id("PARSE", stored.sha256),
                source_name=source_name,
                stage=IngestionStage.PARSE,
                status=IngestionStatus.FAILED,
                reason_code="PARSE_ERROR",
                sha256=stored.sha256,
                raw_path=stored.raw_path,
                source_timestamp=source_timestamp,
                received_at=received_at,
                processed_at=processed_at,
                available_at=available_at,
                record_count=0,
            )
            return NasdaqUniverseIngestionOutcome(
                NasdaqIngestionDisposition.FAILED, stored.ingestion_id, None, "PARSE_ERROR"
            )

        stored = self._store_raw(
            raw=raw,
            source_name=source_name,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            record_count=len(parsed.records),
        )
        try:
            normalized = normalize_nasdaqlisted(parsed)
        except NasdaqSymbolDirectoryError:
            self._save_result(
                result_id=self._result_id("NORMALIZE", stored.sha256),
                source_name=source_name,
                stage=IngestionStage.NORMALIZE,
                status=IngestionStatus.FAILED,
                reason_code="NORMALIZATION_ERROR",
                sha256=stored.sha256,
                raw_path=stored.raw_path,
                source_timestamp=source_timestamp,
                received_at=received_at,
                processed_at=processed_at,
                available_at=available_at,
                record_count=len(parsed.records),
            )
            return NasdaqUniverseIngestionOutcome(
                NasdaqIngestionDisposition.FAILED, stored.ingestion_id, None, "NORMALIZATION_ERROR"
            )

        quality = assess_nasdaq_quality(normalized)
        self._save_result(
            result_id=self._result_id("QUALITY", stored.sha256),
            source_name=source_name,
            stage=IngestionStage.QUALITY,
            status=IngestionStatus.SUCCESS,
            reason_code="QUALITY_WARNINGS" if quality.warning_count else None,
            sha256=stored.sha256,
            raw_path=stored.raw_path,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            record_count=quality.total_records,
        )

        resolved = resolve_nasdaq_identities(
            normalized,
            aliases=self._aliases.scan_as_of(self.provider, self.feed, available_at),
            effective_time=effective_time,
            query_time=available_at,
            provider=self.provider,
            feed=self.feed,
        )
        gate = build_identity_persistence_gate(
            resolved,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            provider=self.provider,
            feed=self.feed,
        )
        if gate.pending_identity_count or gate.conflict_count:
            reason = "IDENTITY_CONFLICT" if gate.conflict_count else "PENDING_IDENTITY"
            self._save_result(
                result_id=self._result_id("IDENTITY", stored.sha256),
                source_name=source_name,
                stage=IngestionStage.IDENTITY,
                status=IngestionStatus.QUARANTINED,
                reason_code=reason,
                sha256=stored.sha256,
                raw_path=stored.raw_path,
                source_timestamp=source_timestamp,
                received_at=received_at,
                processed_at=processed_at,
                available_at=available_at,
                record_count=gate.total_count,
            )
            return NasdaqUniverseIngestionOutcome(
                NasdaqIngestionDisposition.QUARANTINED, stored.ingestion_id, None, reason, quality
            )

        members: list[HistoricalUniverseMemberRef] = []
        seen_instrument_ids: set[str] = set()
        for record in gate.records:
            version = self._instrument_versions.get_as_of(
                record.instrument_id or "",
                self.provider,
                self.feed,
                effective_time,
                available_at,
            )
            if version is None:
                reason = "MISSING_INSTRUMENT_VERSION"
                self._save_result(
                    result_id=self._result_id("SNAPSHOT", stored.sha256),
                    source_name=source_name,
                    stage=IngestionStage.SNAPSHOT,
                    status=IngestionStatus.QUARANTINED,
                    reason_code=reason,
                    sha256=stored.sha256,
                    raw_path=stored.raw_path,
                    source_timestamp=source_timestamp,
                    received_at=received_at,
                    processed_at=processed_at,
                    available_at=available_at,
                    record_count=gate.total_count,
                )
                return NasdaqUniverseIngestionOutcome(
                    NasdaqIngestionDisposition.QUARANTINED,
                    stored.ingestion_id,
                    None,
                    reason,
                    quality,
                )
            members.append(
                HistoricalUniverseMemberRef(
                    instrument_id=version.instrument_id,
                    provider=version.provider,
                    feed=version.feed,
                    instrument_version=version.version,
                    symbol=record.record.symbol,
                )
            )
            if version.instrument_id in seen_instrument_ids:
                reason = "DUPLICATE_INSTRUMENT_ID"
                self._save_result(
                    result_id=self._result_id("SNAPSHOT", stored.sha256),
                    source_name=source_name,
                    stage=IngestionStage.SNAPSHOT,
                    status=IngestionStatus.QUARANTINED,
                    reason_code=reason,
                    sha256=stored.sha256,
                    raw_path=stored.raw_path,
                    source_timestamp=source_timestamp,
                    received_at=received_at,
                    processed_at=processed_at,
                    available_at=available_at,
                    record_count=gate.total_count,
                )
                return NasdaqUniverseIngestionOutcome(
                    NasdaqIngestionDisposition.QUARANTINED,
                    stored.ingestion_id,
                    None,
                    reason,
                    quality,
                )
            seen_instrument_ids.add(version.instrument_id)

        snapshot_id = self._snapshot_id(stored.sha256)
        snapshot = HistoricalUniverseSnapshot(
            snapshot_id=snapshot_id,
            provider=self.provider,
            feed=self.feed,
            version=snapshot_version,
            as_of=effective_time,
            event_time=effective_time,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            instrument_ids=tuple(member.instrument_id for member in members),
        )
        self._universe_writer.save_snapshot(
            snapshot, source_ingestion_id=stored.ingestion_id, members=tuple(members)
        )
        self._save_result(
            result_id=self._result_id("SNAPSHOT", stored.sha256),
            source_name=source_name,
            stage=IngestionStage.SNAPSHOT,
            status=IngestionStatus.SUCCESS,
            reason_code=None,
            sha256=stored.sha256,
            raw_path=stored.raw_path,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            record_count=gate.total_count,
        )
        operational_universe = derive_operational_universe(
            tuple(
                OperationalUniverseCandidate(
                    record.instrument_id or "",
                    record.record.test_issue,
                    record.record.financial_status,
                )
                for record in gate.records
            ),
            CONSERVATIVE_NASDAQ_OPERATIONAL_POLICY,
        )
        return NasdaqUniverseIngestionOutcome(
            NasdaqIngestionDisposition.SNAPSHOT_PERSISTED,
            stored.ingestion_id,
            snapshot_id,
            None,
            quality,
            operational_universe,
        )

    def _store_raw(self, **kwargs):
        return self._raw_store.save(
            provider=self.provider, feed=self.feed, status="SUCCESS", **kwargs
        )

    def _save_result(self, **kwargs) -> None:
        self._results.save(IngestionResult(provider=self.provider, feed=self.feed, **kwargs))

    @classmethod
    def _result_id(cls, stage: str, sha256: str) -> str:
        return f"{cls.provider}:{cls.feed}:{stage}:{sha256}"

    @classmethod
    def _snapshot_id(cls, sha256: str) -> str:
        return f"{cls.provider}:{cls.feed}:{hashlib.sha256(sha256.encode()).hexdigest()}"
