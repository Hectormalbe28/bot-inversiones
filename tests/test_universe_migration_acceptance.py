import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.storage.sqlite import SQLiteStore


def test_case_01_fresh_database(settings):
    """CASE 1: Fresh DB initializes and creates all expected tables."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "schema_migrations",
            "instrument_versions",
            "source_ingestions",
            "universe_snapshots",
            "universe_snapshot_members",
        }.issubset(tables)


def test_case_02_migration_registry(settings):
    """CASE 2: schema_migrations records exactly 001 and 002 once."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        versions = [r["version"] for r in rows]
        assert versions == ["001_foundation.sql", "002_universe.sql"]
        for r in rows:
            assert len(r["checksum"]) == 64


def test_case_03_restart_safety(settings):
    """CASE 3: Restart is idempotent and preserves existing data."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
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
                "ing-restart",
                "nasdaq",
                "trader",
                "file.txt",
                "path.txt",
                "a" * 64,
                None,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:01:00Z",
                "2026-09-10T12:02:00Z",
                10,
                "SUCCESS",
            ),
        )
    # Restart
    store.initialize()
    with store.connection() as conn:
        count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert count == 2
        saved = conn.execute(
            "SELECT * FROM source_ingestions WHERE ingestion_id = 'ing-restart'"
        ).fetchone()
        assert saved is not None
        assert saved["record_count"] == 10


def test_case_04_foreign_keys_active(settings):
    """CASE 4: PRAGMA foreign_keys is enabled on active connections."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert enabled == 1

        # Prove enforcement
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
                    "snap-fk-fail",
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
                    "missing-ingestion",
                ),
            )


def test_case_05_full_valid_chain(settings):
    """CASE 5: Full valid provenance chain persists across re-initialization."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    valid_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-chain",
                "nasdaq",
                "trader",
                1,
                "AAPL",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                "{}",
                "hash-1",
            ),
        )
        conn.execute(
            """
            INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ing-chain",
                "nasdaq",
                "trader",
                "nasdaqlisted.txt",
                "raw/path.txt",
                valid_sha,
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:01:00Z",
                "2026-09-10T12:02:00Z",
                "2026-09-10T12:03:00Z",
                100,
                "SUCCESS",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-chain",
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
                "ing-chain",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-chain", "inst-chain", "nasdaq", "trader", 1, "AAPL"),
        )

    # Re-initialize and verify persistence
    store.initialize()
    with store.connection() as conn:
        member = conn.execute(
            """
            SELECT m.snapshot_id, m.instrument_id, m.symbol, s.as_of, i.source_name
            FROM universe_snapshot_members m
            JOIN universe_snapshots s ON m.snapshot_id = s.snapshot_id
            JOIN source_ingestions i ON s.source_ingestion_id = i.ingestion_id
            WHERE m.snapshot_id = 'snap-chain'
            """
        ).fetchone()
        assert member is not None
        assert member["instrument_id"] == "inst-chain"
        assert member["symbol"] == "AAPL"
        assert member["source_name"] == "nasdaqlisted.txt"


def _seed_foundation(conn):
    conn.execute(
        """
        INSERT OR IGNORE INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "inst-1",
            "nasdaq",
            "trader",
            1,
            "AAPL",
            "2026-09-10T12:00:00Z",
            "2026-09-10T12:00:00Z",
            "{}",
            "hash-1",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ing-1",
            "nasdaq",
            "trader",
            "file.txt",
            "path.txt",
            "a" * 64,
            None,
            "2026-09-10T12:00:00Z",
            "2026-09-10T12:01:00Z",
            "2026-09-10T12:02:00Z",
            10,
            "SUCCESS",
        ),
    )


def test_case_06_snapshot_without_ingestion_rejected(settings):
    """CASE 6: Snapshot without valid source_ingestion_id rejected by FK."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "snap-1",
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
                    "nonexistent-ing",
                ),
            )


def test_case_07_member_without_snapshot_rejected(settings):
    """CASE 7: Member without valid snapshot_id rejected by FK."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("nonexistent-snap", "inst-1", "nasdaq", "trader", 1, "AAPL"),
            )


def test_case_08_member_without_instrument_version_rejected(settings):
    """CASE 8: Member referencing nonexistent instrument version rejected by composite FK."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-1",
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
                "ing-1",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-1", "missing-inst", "nasdaq", "trader", 1, "AAPL"),
            )


def test_case_09_duplicate_membership_rejected(settings):
    """CASE 9: Duplicate (snapshot_id, instrument_id) rejected even with different symbol."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-1",
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
                "ing-1",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-1", "inst-1", "nasdaq", "trader", 1, "AAPL"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-1", "inst-1", "nasdaq", "trader", 1, "AAPL_DIFF"),
            )


def test_case_10_version_constraints(settings):
    """CASE 10: version < 1 rejected on snapshots and members."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        # Snapshot version 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "ing-1",
                ),
            )
        # Member instrument_version 0
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-1",
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
                "ing-1",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-1", "inst-1", "nasdaq", "trader", 0, "AAPL"),
            )


def test_case_11_record_count_constraint(settings):
    """CASE 11: record_count < 0 rejected."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-neg",
                    "nasdaq",
                    "trader",
                    "file.txt",
                    "path.txt",
                    "a" * 64,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    -1,
                    "SUCCESS",
                ),
            )


def test_case_12_ingestion_status_constraint(settings):
    """CASE 12: Ingestion status outside allowed set rejected."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-stat",
                    "nasdaq",
                    "trader",
                    "file.txt",
                    "path.txt",
                    "a" * 64,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:02:00Z",
                    10,
                    "UNKNOWN",
                ),
            )


def test_case_13_ingestion_temporal_order(settings):
    """CASE 13: Ingestion temporal ordering violated raises IntegrityError."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        # processed_at < received_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-t1",
                    "nasdaq",
                    "trader",
                    "file.txt",
                    "path.txt",
                    "a" * 64,
                    None,
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:01:00Z",
                    "2026-09-10T12:06:00Z",
                    10,
                    "SUCCESS",
                ),
            )
        # available_at < processed_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-t2",
                    "nasdaq",
                    "trader",
                    "file.txt",
                    "path.txt",
                    "a" * 64,
                    None,
                    "2026-09-10T12:00:00Z",
                    "2026-09-10T12:05:00Z",
                    "2026-09-10T12:04:00Z",
                    10,
                    "SUCCESS",
                ),
            )


def test_case_14_snapshot_temporal_provenance(settings):
    """CASE 14: Snapshot temporal provenance constraints enforced."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        # source_timestamp > available_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "ing-1",
                ),
            )
        # published_at > available_at
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "ing-1",
                ),
            )
        # published_at = NULL accepted
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "ing-1",
            ),
        )
        saved = conn.execute(
            "SELECT published_at FROM universe_snapshots WHERE snapshot_id = 'snap-null-pub'"
        ).fetchone()
        assert saved["published_at"] is None


def test_case_15_future_effective_snapshot_allowed(settings):
    """CASE 15: available_at < as_of accepted."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-future",
                "nasdaq",
                "trader",
                1,
                "2026-06-15T00:00:00Z",
                "2026-06-01T10:00:00Z",
                None,
                "2026-06-01T10:00:00Z",
                "2026-06-01T10:01:00Z",
                "2026-06-01T10:02:00Z",
                "2026-06-01T10:03:00Z",
                "ing-1",
            ),
        )
        saved = conn.execute(
            "SELECT as_of, available_at FROM universe_snapshots WHERE snapshot_id = 'snap-future'"
        ).fetchone()
        assert saved["available_at"] < saved["as_of"]


def test_case_16_delayed_availability_snapshot_allowed(settings):
    """CASE 16: as_of < available_at accepted."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-delayed",
                "nasdaq",
                "trader",
                1,
                "2026-06-30T23:59:59Z",
                "2026-07-01T10:00:00Z",
                None,
                "2026-07-01T10:00:00Z",
                "2026-07-01T10:01:00Z",
                "2026-07-01T10:02:00Z",
                "2026-07-01T10:03:00Z",
                "ing-1",
            ),
        )
        saved = conn.execute(
            "SELECT as_of, available_at FROM universe_snapshots WHERE snapshot_id = 'snap-delayed'"
        ).fetchone()
        assert saved["as_of"] < saved["available_at"]


def test_case_17_ticker_change_identity_stability(settings):
    """CASE 17: Stable instrument_id persists across ticker changes in different snapshots."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        conn.execute(
            """
            INSERT INTO instrument_versions VALUES
            ('inst-meta', 'nasdaq', 'trader', 1, 'FB', '2020-01-01T00:00:00Z',
             '2020-01-01T00:00:00Z', '{}', 'h1'),
            ('inst-meta', 'nasdaq', 'trader', 2, 'META', '2022-06-09T00:00:00Z',
             '2022-06-09T00:00:00Z', '{}', 'h2')
            """
        )
        conn.execute(
            """
            INSERT INTO source_ingestions VALUES
            ('ing-1', 'nasdaq', 'trader', 'f1.txt', 'p1.txt', ?, NULL,
             '2020-01-01T00:00:00Z', '2020-01-01T00:01:00Z', '2020-01-01T00:02:00Z',
             1, 'SUCCESS'),
            ('ing-2', 'nasdaq', 'trader', 'f2.txt', 'p2.txt', ?, NULL,
             '2022-06-09T00:00:00Z', '2022-06-09T00:01:00Z', '2022-06-09T00:02:00Z',
             1, 'SUCCESS')
            """,
            ("a" * 64, "b" * 64),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES
            ('snap-s1', 'nasdaq', 'trader', 1, '2020-01-01T00:00:00Z',
             '2020-01-01T00:00:00Z', NULL, '2020-01-01T00:00:00Z',
             '2020-01-01T00:01:00Z', '2020-01-01T00:02:00Z', '2020-01-01T00:03:00Z',
             'ing-1'),
            ('snap-s2', 'nasdaq', 'trader', 1, '2022-06-09T00:00:00Z',
             '2022-06-09T00:00:00Z', NULL, '2022-06-09T00:00:00Z',
             '2022-06-09T00:01:00Z', '2022-06-09T00:02:00Z', '2022-06-09T00:03:00Z',
             'ing-2')
            """
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES
            ('snap-s1', 'inst-meta', 'nasdaq', 'trader', 1, 'FB'),
            ('snap-s2', 'inst-meta', 'nasdaq', 'trader', 2, 'META')
            """
        )

        rows = conn.execute(
            """
            SELECT snapshot_id, instrument_id, symbol
            FROM universe_snapshot_members
            WHERE instrument_id = 'inst-meta'
            ORDER BY snapshot_id
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["instrument_id"] == rows[1]["instrument_id"] == "inst-meta"
        assert rows[0]["symbol"] == "FB"
        assert rows[1]["symbol"] == "META"


def test_case_18_symbol_does_not_define_identity(settings):
    """CASE 18: Within same snapshot, duplicate (snapshot_id, instrument_id) rejected.

    Rejection must happen even if symbol differs.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-1",
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
                "ing-1",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-1", "inst-1", "nasdaq", "trader", 1, "AAPL"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-1", "inst-1", "nasdaq", "trader", 1, "AAPL_DIFFERENT"),
            )


def test_case_19_same_symbol_different_identities(settings):
    """CASE 19: Storage does not automatically merge different instrument_ids sharing a symbol."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _seed_foundation(conn)
        conn.execute(
            """
            INSERT INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-2",
                "nasdaq",
                "trader",
                1,
                "AAPL",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                "{}",
                "hash-2",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-1",
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
                "ing-1",
            ),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES
            ('snap-1', 'inst-1', 'nasdaq', 'trader', 1, 'AAPL'),
            ('snap-1', 'inst-2', 'nasdaq', 'trader', 1, 'AAPL')
            """
        )
        rows = conn.execute(
            """
            SELECT instrument_id, symbol
            FROM universe_snapshot_members
            WHERE snapshot_id = 'snap-1'
            ORDER BY instrument_id
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["instrument_id"] == "inst-1"
        assert rows[1]["instrument_id"] == "inst-2"
        assert rows[0]["symbol"] == rows[1]["symbol"] == "AAPL"


def test_case_20_checksum_tamper_detection(settings):
    """CASE 20: Checksum tamper on 002_universe.sql detected on re-initialize."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        conn.execute(
            "UPDATE schema_migrations SET checksum='tampered' WHERE version='002_universe.sql'"
        )
    with pytest.raises(RuntimeError, match="checksum"):
        store.initialize()


def test_case_21_newer_unknown_migration_registry(settings):
    """CASE 21: Database with unknown/newer migration causes startup failure."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?)",
            ("999_future.sql", "hash", "2026-09-10T12:00:00Z"),
        )
    with pytest.raises(RuntimeError, match="newer than this application"):
        store.initialize()


def test_case_22_no_destructive_migration():
    """CASE 22: 002_universe.sql contains no destructive statements."""
    migration_path = Path("app/migrations/002_universe.sql")
    content = migration_path.read_text(encoding="utf-8").upper()

    assert "DROP TABLE" not in content
    assert "DELETE FROM" not in content
    assert "PRAGMA FOREIGN_KEYS=OFF" not in content
    assert "PRAGMA FOREIGN_KEYS = OFF" not in content
