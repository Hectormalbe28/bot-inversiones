import sqlite3

import pytest

from app.infrastructure.storage.sqlite import SQLiteStore


def test_fresh_migration_creates_source_ingestions(settings):
    """CASE 1: Fresh migration initializes empty database and creates source_ingestions."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "source_ingestions" in tables


def test_expected_columns_exist(settings):
    """CASE 2: All required columns exist on source_ingestions table."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        columns = {
            row["name"]: row["type"] for row in conn.execute("PRAGMA table_info(source_ingestions)")
        }
        expected_columns = {
            "ingestion_id",
            "provider",
            "feed",
            "source_name",
            "raw_path",
            "sha256",
            "source_timestamp",
            "received_at",
            "processed_at",
            "available_at",
            "record_count",
            "status",
        }
        assert expected_columns.issubset(columns.keys())


def test_migration_registration(settings):
    """CASE 3: Both 001_foundation.sql and 002_universe.sql appear in schema_migrations."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        migrations = [
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        assert migrations == ["001_foundation.sql", "002_universe.sql"]


def test_restart_idempotent_migration_execution(settings):
    """CASE 4: Re-initialization succeeds without duplicating registrations or tables."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    store.initialize()
    with store.connection() as conn:
        count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert count == 2


def test_valid_ingestion_row_persists(settings):
    """CASE 5: Valid ingestion row persists correctly."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    row = (
        "ing-001",
        "nasdaq",
        "trader",
        "nasdaqlisted.txt",
        "artifacts/raw/nasdaqlisted.txt",
        valid_sha,
        "2026-09-10T12:00:00Z",
        "2026-09-10T12:01:00Z",
        "2026-09-10T12:02:00Z",
        "2026-09-10T12:03:00Z",
        150,
        "SUCCESS",
    )
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO source_ingestions (
                ingestion_id, provider, feed, source_name, raw_path, sha256,
                source_timestamp, received_at, processed_at, available_at,
                record_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        saved = conn.execute(
            "SELECT * FROM source_ingestions WHERE ingestion_id = 'ing-001'"
        ).fetchone()
        assert saved["ingestion_id"] == "ing-001"
        assert saved["record_count"] == 150
        assert saved["status"] == "SUCCESS"


def test_negative_record_count_rejected(settings):
    """CASE 6: Negative record_count rejected by check constraint."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "a" * 64
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions (
                    ingestion_id, provider, feed, source_name, raw_path, sha256,
                    source_timestamp, received_at, processed_at, available_at,
                    record_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-neg",
                    "nasdaq",
                    "trader",
                    "nasdaqlisted.txt",
                    "raw.txt",
                    valid_sha,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    -1,
                    "SUCCESS",
                ),
            )


def test_invalid_status_rejected(settings):
    """CASE 7: Invalid status rejected by check constraint."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "a" * 64
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions (
                    ingestion_id, provider, feed, source_name, raw_path, sha256,
                    source_timestamp, received_at, processed_at, available_at,
                    record_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-status",
                    "nasdaq",
                    "trader",
                    "nasdaqlisted.txt",
                    "raw.txt",
                    valid_sha,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    10,
                    "UNKNOWN_STATUS",
                ),
            )


def test_invalid_temporal_ordering_rejected(settings):
    """CASE 8: Invalid temporal ordering rejected.

    Rejects when processed_at < received_at or available_at < processed_at.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "a" * 64

    # processed_at < received_at
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions (
                    ingestion_id, provider, feed, source_name, raw_path, sha256,
                    source_timestamp, received_at, processed_at, available_at,
                    record_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-t1",
                    "nasdaq",
                    "trader",
                    "nasdaqlisted.txt",
                    "raw.txt",
                    valid_sha,
                    None,
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:06:00Z",
                    10,
                    "SUCCESS",
                ),
            )

    # available_at < processed_at
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions (
                    ingestion_id, provider, feed, source_name, raw_path, sha256,
                    source_timestamp, received_at, processed_at, available_at,
                    record_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-t2",
                    "nasdaq",
                    "trader",
                    "nasdaqlisted.txt",
                    "raw.txt",
                    valid_sha,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:04:00Z",
                    10,
                    "SUCCESS",
                ),
            )


def test_nullable_source_timestamp_accepted(settings):
    """CASE 9: NULL source_timestamp accepted."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "b" * 64
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO source_ingestions (
                ingestion_id, provider, feed, source_name, raw_path, sha256,
                source_timestamp, received_at, processed_at, available_at,
                record_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ing-null-ts",
                "nasdaq",
                "trader",
                "nasdaqlisted.txt",
                "raw.txt",
                valid_sha,
                None,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:01:00Z",
                "2026-09-10T12:02:00Z",
                0,
                "PENDING",
            ),
        )
        saved = conn.execute(
            "SELECT source_timestamp FROM source_ingestions WHERE ingestion_id = 'ing-null-ts'"
        ).fetchone()
        assert saved["source_timestamp"] is None


def test_migration_checksum_behavior_preserved(settings):
    """CASE 10: Existing migration checksum detection works for 002_universe.sql."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        conn.execute(
            "UPDATE schema_migrations SET checksum='tampered' WHERE version='002_universe.sql'"
        )
    with pytest.raises(RuntimeError, match="checksum"):
        store.initialize()
