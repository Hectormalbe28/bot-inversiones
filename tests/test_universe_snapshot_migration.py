import sqlite3

import pytest

from app.infrastructure.storage.sqlite import SQLiteStore


def test_fresh_database_creates_both_tables(settings):
    """CASE 1: Fresh DB initialization creates source_ingestions and universe_snapshots."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "source_ingestions" in tables
        assert "universe_snapshots" in tables


def test_expected_snapshot_columns_exist(settings):
    """CASE 2: All required universe_snapshots columns exist."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(universe_snapshots)")}
        expected_columns = {
            "snapshot_id",
            "provider",
            "feed",
            "version",
            "as_of",
            "event_time",
            "published_at",
            "source_timestamp",
            "received_at",
            "processed_at",
            "available_at",
            "source_ingestion_id",
        }
        assert expected_columns.issubset(columns)


def test_foreign_key_references_source_ingestions(settings):
    """CASE 3: Foreign key on universe_snapshots references source_ingestions(ingestion_id)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        fks = [
            (row["table"], row["from"], row["to"])
            for row in conn.execute("PRAGMA foreign_key_list(universe_snapshots)")
        ]
        assert ("source_ingestions", "source_ingestion_id", "ingestion_id") in fks


def _insert_ingestion(conn, ingestion_id="ing-001"):
    conn.execute(
        """
        INSERT INTO source_ingestions (
            ingestion_id, provider, feed, source_name, raw_path, sha256,
            source_timestamp, received_at, processed_at, available_at,
            record_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ingestion_id,
            "nasdaq",
            "trader",
            "nasdaqlisted.txt",
            "raw/nasdaqlisted.txt",
            "a" * 64,
            "2026-09-10T12:00:00Z",
            "2026-09-10T12:01:00Z",
            "2026-09-10T12:02:00Z",
            "2026-09-10T12:03:00Z",
            100,
            "SUCCESS",
        ),
    )


def test_valid_snapshot_insert(settings):
    """CASE 4: Valid universe_snapshots row referencing source_ingestions persists."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")
        conn.execute(
            """
            INSERT INTO universe_snapshots (
                snapshot_id, provider, feed, version, as_of, event_time,
                published_at, source_timestamp, received_at, processed_at,
                available_at, source_ingestion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-001",
                "nasdaq",
                "trader",
                1,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:02:00Z",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:01:00Z",
                "2026-09-10T12:02:00Z",
                "2026-09-10T12:03:00Z",
                "ing-001",
            ),
        )
        saved = conn.execute(
            "SELECT * FROM universe_snapshots WHERE snapshot_id = 'snap-001'"
        ).fetchone()
        assert saved["snapshot_id"] == "snap-001"
        assert saved["source_ingestion_id"] == "ing-001"
        assert saved["version"] == 1


def test_missing_ingestion_rejected_by_foreign_key(settings):
    """CASE 5: Snapshot insert with nonexistent source_ingestion_id fails with FK error."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-orphan",
                    "nasdaq",
                    "trader",
                    1,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    "2026-09-10T12:03:00Z",
                    "nonexistent-ingestion-id",
                ),
            )


def test_invalid_version_rejected(settings):
    """CASE 6: version = 0 must fail check constraint."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-v0",
                    "nasdaq",
                    "trader",
                    0,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    "2026-09-10T12:03:00Z",
                    "ing-001",
                ),
            )


def test_invalid_provenance_ordering_rejected(settings):
    """CASE 7: processed_at < received_at or available_at < processed_at rejected."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")

        # processed_at < received_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-bad-order1",
                    "nasdaq",
                    "trader",
                    1,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:02:00Z",
                    "2026-09-10T12:06:00Z",
                    "ing-001",
                ),
            )

        # available_at < processed_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-bad-order2",
                    "nasdaq",
                    "trader",
                    1,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:04:00Z",
                    "ing-001",
                ),
            )


def test_source_timestamp_after_available_at_rejected(settings):
    """CASE 8: source_timestamp > available_at rejected."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-bad-src",
                    "nasdaq",
                    "trader",
                    1,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    None,
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    "2026-09-10T12:03:00Z",
                    "ing-001",
                ),
            )


def test_published_at_after_available_at_rejected(settings):
    """CASE 9: published_at > available_at rejected; NULL published_at accepted."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")

        # published_at > available_at rejected
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots (
                    snapshot_id, provider, feed, version, as_of, event_time,
                    published_at, source_timestamp, received_at, processed_at,
                    available_at, source_ingestion_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-bad-pub",
                    "nasdaq",
                    "trader",
                    1,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    "2026-09-10T12:03:00Z",
                    "ing-001",
                ),
            )

        # NULL published_at accepted
        conn.execute(
            """
            INSERT INTO universe_snapshots (
                snapshot_id, provider, feed, version, as_of, event_time,
                published_at, source_timestamp, received_at, processed_at,
                available_at, source_ingestion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-null-pub",
                "nasdaq",
                "trader",
                1,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                None,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:01:00Z",
                "2026-09-10T12:02:00Z",
                "2026-09-10T12:03:00Z",
                "ing-001",
            ),
        )
        saved = conn.execute(
            "SELECT published_at FROM universe_snapshots WHERE snapshot_id = 'snap-null-pub'"
        ).fetchone()
        assert saved["published_at"] is None


def test_future_effective_snapshot_allowed(settings):
    """CASE 10: Future-effective snapshot allowed (available_at < as_of)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")
        conn.execute(
            """
            INSERT INTO universe_snapshots (
                snapshot_id, provider, feed, version, as_of, event_time,
                published_at, source_timestamp, received_at, processed_at,
                available_at, source_ingestion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-future",
                "nasdaq",
                "trader",
                1,
                "2026-06-15T00:00:00Z",  # as_of June 15
                "2026-06-01T10:00:00Z",
                None,
                "2026-06-01T10:00:00Z",
                "2026-06-01T10:01:00Z",
                "2026-06-01T10:02:00Z",
                "2026-06-01T10:03:00Z",  # available_at June 1 (< as_of June 15)
                "ing-001",
            ),
        )
        saved = conn.execute(
            "SELECT as_of, available_at FROM universe_snapshots WHERE snapshot_id = 'snap-future'"
        ).fetchone()
        assert saved["available_at"] < saved["as_of"]


def test_delayed_availability_snapshot_allowed(settings):
    """CASE 11: Delayed-availability snapshot allowed (as_of < available_at)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _insert_ingestion(conn, "ing-001")
        conn.execute(
            """
            INSERT INTO universe_snapshots (
                snapshot_id, provider, feed, version, as_of, event_time,
                published_at, source_timestamp, received_at, processed_at,
                available_at, source_ingestion_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-delayed",
                "nasdaq",
                "trader",
                1,
                "2026-06-30T23:59:59Z",  # as_of June 30
                "2026-07-01T10:00:00Z",
                None,
                "2026-07-01T10:00:00Z",
                "2026-07-01T10:01:00Z",
                "2026-07-01T10:02:00Z",
                "2026-07-01T10:03:00Z",  # available_at July 1 (> as_of June 30)
                "ing-001",
            ),
        )
        saved = conn.execute(
            "SELECT as_of, available_at FROM universe_snapshots WHERE snapshot_id = 'snap-delayed'"
        ).fetchone()
        assert saved["as_of"] < saved["available_at"]


def test_restart_safe_migration(settings):
    """CASE 12: Re-initialization succeeds without duplicating tables or registrations."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    store.initialize()
    with store.connection() as conn:
        count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert count == 2
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        assert "source_ingestions" in tables
        assert "universe_snapshots" in tables
