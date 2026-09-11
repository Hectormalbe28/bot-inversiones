import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from app.application.universe import (
    HistoricalUniverseMemberRef,
    HistoricalUniverseWriteConflict,
)
from app.core.clock import utc_key, utc_now
from app.domain.models import HistoricalUniverseSnapshot, Instrument


class SQLiteStore:
    def __init__(self, path: Path, busy_timeout_ms: int = 5000):
        self.path = path
        self.busy_timeout_ms = busy_timeout_ms

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resources = files("app.migrations")
        migrations = sorted(
            (p for p in resources.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name
        )
        with self.connection() as conn:
            if conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("SQLite WAL is required")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            applied = {
                row["version"]: row["checksum"]
                for row in conn.execute("SELECT version, checksum FROM schema_migrations")
            }
            known = {p.name for p in migrations}
            if applied.keys() - known:
                raise RuntimeError("Database schema is newer than this application")
            for migration in migrations:
                sql = migration.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                if migration.name in applied:
                    if applied[migration.name] != checksum:
                        raise RuntimeError(f"Migration checksum mismatch: {migration.name}")
                    continue
                # execute(), unlike executescript(), does not implicitly commit the transaction.
                statement = ""
                for line in sql.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ""
                if statement.strip():
                    raise RuntimeError(f"Incomplete migration: {migration.name}")
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (migration.name, checksum, utc_key(utc_now())),
                )

    def probe(self) -> None:
        # mode=rw avoids recreating a missing database and falsely reporting success.
        conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True)
        try:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity check failed")
            conn.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
            conn.execute("SELECT count(*) FROM knowledge_index WHERE knowledge_index MATCH 'probe'")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO health_probe DEFAULT VALUES")
            conn.rollback()
        finally:
            conn.close()


class InstrumentRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def save(self, instrument: Instrument) -> bool:
        payload = json.dumps(
            instrument.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        key = (instrument.instrument_id, instrument.provider, instrument.feed, instrument.version)
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT payload_hash FROM instrument_versions "
                "WHERE instrument_id=? AND provider=? AND feed=? AND version=?",
                key,
            ).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError("Immutable instrument version conflict")
                return False
            conn.execute(
                "INSERT INTO instrument_versions "
                "(instrument_id, provider, feed, version, symbol, event_time, available_at, "
                "payload, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    *key,
                    instrument.symbol,
                    utc_key(instrument.event_time),
                    utc_key(instrument.available_at),
                    payload,
                    digest,
                ),
            )
        return True

    def get_as_of(self, symbol: str, as_of: datetime) -> Instrument | None:
        cutoff = utc_key(as_of)
        with self.store.connection() as conn:
            rows = conn.execute(
                "WITH eligible AS (SELECT *, ROW_NUMBER() OVER ("
                "PARTITION BY instrument_id, provider, feed "
                "ORDER BY available_at DESC, version DESC) AS rank "
                "FROM instrument_versions WHERE available_at <= ?) "
                "SELECT payload FROM eligible WHERE rank=1 AND symbol=?",
                (cutoff, symbol.upper()),
            ).fetchall()
        if len(rows) > 1:
            raise ValueError("Ambiguous instrument sources: reconciliation required")
        return Instrument.model_validate_json(rows[0][0]) if rows else None

    def scan_as_of(self, as_of: datetime) -> Sequence[Instrument]:
        cutoff = utc_key(as_of)
        with self.store.connection() as conn:
            rows = conn.execute(
                "WITH eligible AS (SELECT *, ROW_NUMBER() OVER ("
                "PARTITION BY instrument_id, provider, feed "
                "ORDER BY available_at DESC, version DESC) AS rank "
                "FROM instrument_versions WHERE available_at <= ?) "
                "SELECT payload FROM eligible WHERE rank=1 ORDER BY symbol ASC, instrument_id ASC",
                (cutoff,),
            ).fetchall()
        return tuple(Instrument.model_validate_json(row[0]) for row in rows)

    def latest_available(self, identifier: str, as_of: datetime) -> Instrument | None:
        cutoff = utc_key(as_of)
        with self.store.connection() as conn:
            rows = conn.execute(
                "WITH eligible AS (SELECT *, ROW_NUMBER() OVER ("
                "PARTITION BY instrument_id, provider, feed "
                "ORDER BY available_at DESC, version DESC) AS rank "
                "FROM instrument_versions WHERE available_at <= ?) "
                "SELECT payload FROM eligible WHERE rank=1 AND (symbol=? OR instrument_id=?)",
                (cutoff, identifier.upper(), identifier),
            ).fetchall()
        if len(rows) > 1:
            raise ValueError("Ambiguous instrument sources: reconciliation required")
        return Instrument.model_validate_json(rows[0][0]) if rows else None


class SQLiteHistoricalUniverseRepository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def get_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> HistoricalUniverseSnapshot | None:
        cutoff = utc_key(query_time)
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT snapshot_id, provider, feed, version, as_of, event_time, "
                "published_at, source_timestamp, received_at, processed_at, available_at "
                "FROM universe_snapshots "
                "WHERE provider = ? AND feed = ? AND available_at <= ? AND as_of <= ? "
                "ORDER BY as_of DESC, available_at DESC, version DESC, snapshot_id ASC "
                "LIMIT 1",
                (provider, feed, cutoff, cutoff),
            ).fetchone()
            if row is None:
                return None
            members = conn.execute(
                "SELECT instrument_id FROM universe_snapshot_members "
                "WHERE snapshot_id = ? ORDER BY instrument_id ASC",
                (row["snapshot_id"],),
            ).fetchall()
        return HistoricalUniverseSnapshot(
            snapshot_id=row["snapshot_id"],
            provider=row["provider"],
            feed=row["feed"],
            version=row["version"],
            as_of=row["as_of"],
            event_time=row["event_time"],
            published_at=row["published_at"],
            source_timestamp=row["source_timestamp"],
            received_at=row["received_at"],
            processed_at=row["processed_at"],
            available_at=row["available_at"],
            instrument_ids=tuple(member["instrument_id"] for member in members),
        )

    def members_as_of(
        self, provider: str, feed: str, query_time: datetime
    ) -> tuple[str, ...] | None:
        snapshot = self.get_as_of(provider, feed, query_time)
        if snapshot is None:
            return None
        return snapshot.instrument_ids


class SQLiteHistoricalUniverseWriteRepository:
    """SQLite implementation of HistoricalUniverseWriteRepository.

    Persists historical universe snapshots and member references atomically.
    Idempotent on exact replay; raises HistoricalUniverseWriteConflict on conflicting data.
    Enforces foreign keys to source_ingestions and instrument_versions.
    """

    def __init__(self, store: SQLiteStore):
        self.store = store

    def save_snapshot(
        self,
        snapshot: HistoricalUniverseSnapshot,
        *,
        source_ingestion_id: str,
        members: tuple[HistoricalUniverseMemberRef, ...],
    ) -> bool:
        if not source_ingestion_id or not isinstance(source_ingestion_id, str):
            raise ValueError("source_ingestion_id is mandatory")

        # 1. Membership set and duplicate validation
        seen_member_ids: set[str] = set()
        for m in members:
            if m.instrument_id in seen_member_ids:
                raise ValueError(f"Duplicate member instrument_id in members: {m.instrument_id}")
            seen_member_ids.add(m.instrument_id)

        if set(snapshot.instrument_ids) != seen_member_ids:
            raise ValueError(
                f"Snapshot instrument_ids and member refs must represent the same set. "
                f"Mismatch: snapshot={set(snapshot.instrument_ids)}, members={seen_member_ids}"
            )

        # Canonical sort by instrument_id ASC
        sorted_members = sorted(members, key=lambda m: m.instrument_id)

        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")

            # Check if snapshot_id already exists
            row = conn.execute(
                "SELECT snapshot_id, provider, feed, version, as_of, event_time, "
                "published_at, source_timestamp, received_at, processed_at, available_at, "
                "source_ingestion_id "
                "FROM universe_snapshots "
                "WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()

            if row is not None:
                published_at_key = (
                    utc_key(snapshot.published_at) if snapshot.published_at is not None else None
                )
                metadata_match = (
                    row["provider"] == snapshot.provider
                    and row["feed"] == snapshot.feed
                    and row["version"] == snapshot.version
                    and row["as_of"] == utc_key(snapshot.as_of)
                    and row["event_time"] == utc_key(snapshot.event_time)
                    and row["published_at"] == published_at_key
                    and row["source_timestamp"] == utc_key(snapshot.source_timestamp)
                    and row["received_at"] == utc_key(snapshot.received_at)
                    and row["processed_at"] == utc_key(snapshot.processed_at)
                    and row["available_at"] == utc_key(snapshot.available_at)
                    and row["source_ingestion_id"] == source_ingestion_id
                )
                if not metadata_match:
                    raise HistoricalUniverseWriteConflict(
                        f"Snapshot metadata conflict for snapshot_id={snapshot.snapshot_id}"
                    )

                existing_member_rows = conn.execute(
                    "SELECT instrument_id, provider, feed, instrument_version, symbol "
                    "FROM universe_snapshot_members "
                    "WHERE snapshot_id = ? "
                    "ORDER BY instrument_id ASC",
                    (snapshot.snapshot_id,),
                ).fetchall()

                existing_member_tuples = tuple(
                    (
                        r["instrument_id"],
                        r["provider"],
                        r["feed"],
                        r["instrument_version"],
                        r["symbol"],
                    )
                    for r in existing_member_rows
                )
                new_member_tuples = tuple(
                    (
                        m.instrument_id,
                        m.provider,
                        m.feed,
                        m.instrument_version,
                        m.symbol,
                    )
                    for m in sorted_members
                )

                if existing_member_tuples != new_member_tuples:
                    raise HistoricalUniverseWriteConflict(
                        f"Snapshot membership conflict for snapshot_id={snapshot.snapshot_id}"
                    )

                return False

            published_at_key = (
                utc_key(snapshot.published_at) if snapshot.published_at is not None else None
            )
            conn.execute(
                "INSERT INTO universe_snapshots ("
                "snapshot_id, provider, feed, version, as_of, event_time, "
                "published_at, source_timestamp, received_at, processed_at, available_at, "
                "source_ingestion_id"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.snapshot_id,
                    snapshot.provider,
                    snapshot.feed,
                    snapshot.version,
                    utc_key(snapshot.as_of),
                    utc_key(snapshot.event_time),
                    published_at_key,
                    utc_key(snapshot.source_timestamp),
                    utc_key(snapshot.received_at),
                    utc_key(snapshot.processed_at),
                    utc_key(snapshot.available_at),
                    source_ingestion_id,
                ),
            )

            for m in sorted_members:
                conn.execute(
                    "INSERT INTO universe_snapshot_members ("
                    "snapshot_id, instrument_id, provider, feed, instrument_version, symbol"
                    ") VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        snapshot.snapshot_id,
                        m.instrument_id,
                        m.provider,
                        m.feed,
                        m.instrument_version,
                        m.symbol,
                    ),
                )

            return True


SQLiteHistoricalUniverseWriter = SQLiteHistoricalUniverseWriteRepository
