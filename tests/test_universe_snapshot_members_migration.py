import sqlite3

import pytest

from app.infrastructure.storage.sqlite import SQLiteStore


def test_fresh_database_creates_all_three_tables(settings):
    """CASE 1: Fresh DB initialization creates all three S2 tables."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "source_ingestions" in tables
        assert "universe_snapshots" in tables
        assert "universe_snapshot_members" in tables


def test_expected_member_columns_exist(settings):
    """CASE 2: All required universe_snapshot_members columns exist."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(universe_snapshot_members)")
        }
        expected_columns = {
            "snapshot_id",
            "instrument_id",
            "provider",
            "feed",
            "instrument_version",
            "symbol",
        }
        assert expected_columns.issubset(columns)


def test_snapshot_foreign_key(settings):
    """CASE 3: snapshot_id references universe_snapshots(snapshot_id)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        fks = [
            (row["table"], row["from"], row["to"])
            for row in conn.execute("PRAGMA foreign_key_list(universe_snapshot_members)")
        ]
        assert ("universe_snapshots", "snapshot_id", "snapshot_id") in fks


def test_instrument_version_foreign_key(settings):
    """CASE 4: Composite FK references instrument_versions."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        fks = [
            (row["table"], row["from"], row["to"])
            for row in conn.execute("PRAGMA foreign_key_list(universe_snapshot_members)")
            if row["table"] == "instrument_versions"
        ]
        expected = {
            ("instrument_versions", "instrument_id", "instrument_id"),
            ("instrument_versions", "provider", "provider"),
            ("instrument_versions", "feed", "feed"),
            ("instrument_versions", "instrument_version", "version"),
        }
        assert expected.issubset(set(fks))


def _setup_fixtures(conn, instrument_id="inst-1", version=1, symbol="AAPL"):
    conn.execute(
        """
        INSERT OR IGNORE INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            instrument_id,
            "nasdaq",
            "trader",
            version,
            symbol,
            "2026-09-10T12:00:00Z",
            "2026-09-10T12:00:00Z",
            "{}",
            "hash",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ing-001",
            "nasdaq",
            "trader",
            "nasdaqlisted.txt",
            "raw/nasdaqlisted.txt",
            "a" * 64,
            None,
            "2026-09-10T12:00:00Z",
            "2026-09-10T12:01:00Z",
            "2026-09-10T12:02:00Z",
            100,
            "SUCCESS",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "snap-001",
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


def test_valid_membership_insert(settings):
    """CASE 5: Valid universe_snapshot_members record persists."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "AAPL")
        conn.execute(
            """
            INSERT INTO universe_snapshot_members (
                snapshot_id, instrument_id, provider, feed, instrument_version, symbol
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-001", "inst-1", "nasdaq", "trader", 1, "AAPL"),
        )
        saved = conn.execute(
            "SELECT * FROM universe_snapshot_members WHERE snapshot_id = 'snap-001'"
        ).fetchone()
        assert saved["snapshot_id"] == "snap-001"
        assert saved["instrument_id"] == "inst-1"
        assert saved["symbol"] == "AAPL"
        assert saved["instrument_version"] == 1


def test_nonexistent_snapshot_rejected(settings):
    """CASE 6: Nonexistent snapshot_id rejected by foreign key."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "AAPL")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members (
                    snapshot_id, instrument_id, provider, feed, instrument_version, symbol
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-unknown", "inst-1", "nasdaq", "trader", 1, "AAPL"),
            )


def test_nonexistent_instrument_version_rejected(settings):
    """CASE 7: Nonexistent referenced instrument evidence rejected by foreign key."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "AAPL")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members (
                    snapshot_id, instrument_id, provider, feed, instrument_version, symbol
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-001", "inst-missing", "nasdaq", "trader", 1, "MSFT"),
            )


def test_duplicate_stable_membership_rejected(settings):
    """CASE 8: Duplicate (snapshot_id, instrument_id) rejected even with different symbol."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "AAPL")
        conn.execute(
            """
            INSERT INTO universe_snapshot_members (
                snapshot_id, instrument_id, provider, feed, instrument_version, symbol
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-001", "inst-1", "nasdaq", "trader", 1, "AAPL"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members (
                    snapshot_id, instrument_id, provider, feed, instrument_version, symbol
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-001", "inst-1", "nasdaq", "trader", 1, "AAPL_NEW"),
            )


def test_invalid_instrument_version_rejected(settings):
    """CASE 9: instrument_version = 0 rejected by check constraint."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "AAPL")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO universe_snapshot_members (
                    snapshot_id, instrument_id, provider, feed, instrument_version, symbol
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("snap-001", "inst-1", "nasdaq", "trader", 0, "AAPL"),
            )


def test_same_stable_instrument_different_snapshots_accepted(settings):
    """CASE 10: Same instrument_id across different snapshots accepted (e.g. ticker change)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-1", 1, "FB")
        # Add second version of instrument_versions for META
        conn.execute(
            """
            INSERT INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-1",
                "nasdaq",
                "trader",
                2,
                "META",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                "{}",
                "hash2",
            ),
        )
        # Add second snapshot
        conn.execute(
            """
            INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snap-002",
                "nasdaq",
                "trader",
                1,
                "2026-09-15T00:00:00Z",
                "2026-09-15T00:00:00Z",
                None,
                "2026-09-15T00:00:00Z",
                "2026-09-15T00:01:00Z",
                "2026-09-15T00:02:00Z",
                "2026-09-15T00:03:00Z",
                "ing-001",
            ),
        )

        conn.execute(
            """
            INSERT INTO universe_snapshot_members (
                snapshot_id, instrument_id, provider, feed, instrument_version, symbol
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-001", "inst-1", "nasdaq", "trader", 1, "FB"),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members (
                snapshot_id, instrument_id, provider, feed, instrument_version, symbol
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-002", "inst-1", "nasdaq", "trader", 2, "META"),
        )

        rows = conn.execute(
            """
            SELECT * FROM universe_snapshot_members
            WHERE instrument_id = 'inst-1'
            ORDER BY snapshot_id
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["symbol"] == "FB"
        assert rows[1]["symbol"] == "META"


def test_same_symbol_does_not_merge_distinct_identities(settings):
    """CASE 11: Schema does not merge identities when symbols are identical."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        _setup_fixtures(conn, "inst-A", 1, "REUSED")
        conn.execute(
            """
            INSERT INTO instrument_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-B",
                "nasdaq",
                "trader",
                1,
                "REUSED",
                "2026-09-10T12:00:00Z",
                "2026-09-10T12:00:00Z",
                "{}",
                "hashB",
            ),
        )

        # Both can coexist in the same snapshot as distinct instrument_ids
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-001", "inst-A", "nasdaq", "trader", 1, "REUSED"),
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("snap-001", "inst-B", "nasdaq", "trader", 1, "REUSED"),
        )

        members = conn.execute(
            "SELECT instrument_id FROM universe_snapshot_members WHERE snapshot_id = 'snap-001'"
        ).fetchall()
        assert {m["instrument_id"] for m in members} == {"inst-A", "inst-B"}


def test_restart_safe_migration(settings):
    """CASE 12: Re-initialization succeeds without error.

    Ensures no duplicate tables or duplicate registrations.
    """
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
        assert "universe_snapshot_members" in tables
