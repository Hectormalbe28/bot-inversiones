"""Immutable raw artifact store with source_ingestions provenance.

Stores provider raw bytes in content-addressed filesystem layout:
    <raw_root>/<provider>/<feed>/<sha256>.raw

Inserts an idempotent provenance record into the source_ingestions table
using (provider, feed, source_name, sha256) as the composite idempotency key.

Atomic filesystem write: temp file -> flush -> fsync -> rename.
Database write: BEGIN IMMEDIATE for safe concurrent idempotency check+insert.

SHA-256 is always computed from the raw bytes here — never accepted from callers.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.clock import require_utc, utc_key
from app.infrastructure.storage.sqlite import SQLiteStore

_VALID_STATUSES = frozenset({"PENDING", "SUCCESS", "DEGRADED", "FAILED"})


@dataclass(frozen=True, slots=True)
class RawIngestionResult:
    """Result of a successful or idempotent raw ingestion store operation.

    Attributes:
        ingestion_id: Stable UUID4 identifier for the source_ingestions row.
        sha256: Hex-encoded SHA-256 digest of the stored raw bytes (64 chars).
        raw_path: Absolute filesystem path where the raw bytes are stored.
    """

    ingestion_id: str
    sha256: str
    raw_path: str


class RawIngestionStore:
    """Content-addressed raw artifact store backed by filesystem + SQLite provenance.

    Thread-safety: Each call to save() opens a fresh DB connection with BEGIN IMMEDIATE,
    so concurrent callers are safe at the SQLite layer. Filesystem writes are atomic
    via temp-file rename within the same directory.
    """

    def __init__(self, *, raw_root: Path, sqlite_store: SQLiteStore) -> None:
        self._raw_root = raw_root
        self._sqlite_store = sqlite_store

    def save(
        self,
        *,
        raw: bytes,
        provider: str,
        feed: str,
        source_name: str,
        source_timestamp: datetime | None,
        received_at: datetime,
        processed_at: datetime,
        available_at: datetime,
        record_count: int,
        status: str,
    ) -> RawIngestionResult:
        """Store raw bytes and upsert provenance into source_ingestions.

        Args:
            raw: Raw provider bytes to store.
            provider: Provider identifier (e.g., 'nasdaq').
            feed: Feed identifier (e.g., 'symbol_directory').
            source_name: Original filename or source descriptor.
            source_timestamp: Provider-reported timestamp (optional; must be UTC if given).
            received_at: UTC timestamp when bytes were received.
            processed_at: UTC timestamp when processing completed.
            available_at: UTC knowledge cutoff timestamp.
            record_count: Number of parsed records in the raw file.
            status: Ingestion status; one of PENDING, SUCCESS, DEGRADED, FAILED.

        Returns:
            RawIngestionResult with ingestion_id, sha256, and raw_path.

        Raises:
            ValueError: If any timestamp is naive, temporal constraints are violated,
                        or status is not a recognised value.
        """
        _validate(
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
            available_at=available_at,
            status=status,
        )

        sha256 = hashlib.sha256(raw).hexdigest()
        dest_dir = self._raw_root / provider / feed
        dest_path = dest_dir / f"{sha256}.raw"
        raw_path_str = str(dest_path)

        # ------------------------------------------------------------------ #
        # 1. Atomic filesystem write (temp → rename), skip if already present.
        # ------------------------------------------------------------------ #
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not dest_path.exists():
            fd, tmp_name = tempfile.mkstemp(dir=dest_dir, prefix=".tmp_")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(raw)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, dest_path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise

        # ------------------------------------------------------------------ #
        # 2. Idempotent DB insert.
        # ------------------------------------------------------------------ #
        src_ts_key = (
            utc_key(require_utc(source_timestamp)) if source_timestamp is not None else None
        )
        recv_key = utc_key(require_utc(received_at))
        proc_key = utc_key(require_utc(processed_at))
        avail_key = utc_key(require_utc(available_at))

        with self._sqlite_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT ingestion_id FROM source_ingestions "
                "WHERE provider=? AND feed=? AND source_name=? AND sha256=?",
                (provider, feed, source_name, sha256),
            ).fetchone()

            if row is not None:
                return RawIngestionResult(
                    ingestion_id=row["ingestion_id"],
                    sha256=sha256,
                    raw_path=raw_path_str,
                )

            ingestion_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO source_ingestions "
                "(ingestion_id, provider, feed, source_name, raw_path, sha256, "
                "source_timestamp, received_at, processed_at, available_at, "
                "record_count, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ingestion_id,
                    provider,
                    feed,
                    source_name,
                    raw_path_str,
                    sha256,
                    src_ts_key,
                    recv_key,
                    proc_key,
                    avail_key,
                    record_count,
                    status,
                ),
            )

        return RawIngestionResult(
            ingestion_id=ingestion_id,
            sha256=sha256,
            raw_path=raw_path_str,
        )


def _validate(
    *,
    source_timestamp: datetime | None,
    received_at: datetime,
    processed_at: datetime,
    available_at: datetime,
    status: str,
) -> None:
    """Validate temporal constraints and status before any I/O.

    Raises:
        ValueError: If any constraint is violated.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of {sorted(_VALID_STATUSES)}.")

    # Enforce UTC-awareness on all timestamps.
    require_utc(received_at)
    require_utc(processed_at)
    require_utc(available_at)
    if source_timestamp is not None:
        require_utc(source_timestamp)

    # received_at <= processed_at <= available_at
    if received_at > processed_at:
        raise ValueError(
            f"received_at ({received_at!r}) must be <= processed_at ({processed_at!r})."
        )
    if processed_at > available_at:
        raise ValueError(
            f"processed_at ({processed_at!r}) must be <= available_at ({available_at!r})."
        )
    # source_timestamp <= available_at
    if source_timestamp is not None and source_timestamp > available_at:
        raise ValueError(
            f"source_timestamp ({source_timestamp!r}) must be <= available_at ({available_at!r})."
        )


def save_raw_ingestion(
    *,
    store: RawIngestionStore,
    raw: bytes,
    provider: str,
    feed: str,
    source_name: str,
    source_timestamp: datetime | None,
    received_at: datetime,
    processed_at: datetime,
    available_at: datetime,
    record_count: int,
    status: str,
) -> RawIngestionResult:
    """Module-level helper that delegates to RawIngestionStore.save().

    Prefer instantiating RawIngestionStore directly in production code.
    This helper exists for ergonomic use in tests and scripts.
    """
    return store.save(
        raw=raw,
        provider=provider,
        feed=feed,
        source_name=source_name,
        source_timestamp=source_timestamp,
        received_at=received_at,
        processed_at=processed_at,
        available_at=available_at,
        record_count=record_count,
        status=status,
    )
