import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from app.core.clock import utc_key, utc_now
from app.domain.models import Instrument


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
                "ORDER BY available_at DESC, version DESC, event_time DESC) AS rank "
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
                "ORDER BY available_at DESC, version DESC, event_time DESC) AS rank "
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
                "ORDER BY available_at DESC, version DESC, event_time DESC) AS rank "
                "FROM instrument_versions WHERE available_at <= ?) "
                "SELECT payload FROM eligible WHERE rank=1 AND (symbol=? OR instrument_id=?)",
                (cutoff, identifier.upper(), identifier),
            ).fetchall()
        if len(rows) > 1:
            raise ValueError("Ambiguous instrument sources: reconciliation required")
        return Instrument.model_validate_json(rows[0][0]) if rows else None
