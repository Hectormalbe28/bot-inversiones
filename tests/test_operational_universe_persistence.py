from datetime import UTC, datetime

import pytest

from app.application.operational_universe import (
    OperationalUniverseCandidate,
    OperationalUniversePolicy,
    derive_operational_universe,
)
from app.infrastructure.storage.sqlite import SQLiteOperationalUniverseRepository, SQLiteStore

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _result(*candidates: OperationalUniverseCandidate):
    return derive_operational_universe(
        candidates,
        OperationalUniversePolicy(
            policy_id="nasdaq-operational-conservative",
            version=1,
            exclude_test_issues=True,
            allowed_financial_statuses=frozenset({"N"}),
        ),
    )


def _seed_source_snapshot(store: SQLiteStore, snapshot_id: str = "source-1") -> None:
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO source_ingestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ingestion-1",
                "nasdaq",
                "symbol_directory",
                "nasdaqlisted.txt",
                "raw/content",
                "a" * 64,
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
                3,
                "SUCCESS",
            ),
        )
        conn.execute(
            "INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                "nasdaq",
                "symbol_directory",
                1,
                NOW.isoformat(),
                NOW.isoformat(),
                None,
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
                "ingestion-1",
            ),
        )


def test_exact_operational_replay_is_idempotent_and_preserves_all_decisions(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    _seed_source_snapshot(store)
    repo = SQLiteOperationalUniverseRepository(store)
    result = _result(
        OperationalUniverseCandidate("inst-good", False, "N"),
        OperationalUniverseCandidate("inst-test", True, "N"),
        OperationalUniverseCandidate("inst-status", False, "D"),
    )

    first = repo.save("source-1", "nasdaq-operational-conservative", 1, NOW, result)
    second = repo.save("source-1", "nasdaq-operational-conservative", 1, NOW, result)

    assert second == first
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT instrument_id, included, reason_code FROM operational_universe_members "
            "WHERE operational_snapshot_id=? ORDER BY instrument_id",
            (first,),
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("inst-good", 1, None),
        ("inst-status", 0, "FINANCIAL_STATUS"),
        ("inst-test", 0, "TEST_ISSUE"),
    ]


def test_conflicting_replay_cannot_silently_overwrite_history(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    _seed_source_snapshot(store)
    repo = SQLiteOperationalUniverseRepository(store)
    repo.save(
        "source-1",
        "nasdaq-operational-conservative",
        1,
        NOW,
        _result(OperationalUniverseCandidate("inst-a", False, "N")),
    )

    with pytest.raises(ValueError, match="conflict"):
        repo.save(
            "source-1",
            "nasdaq-operational-conservative",
            1,
            NOW,
            _result(OperationalUniverseCandidate("inst-a", True, "N")),
        )


def test_new_policy_version_creates_an_independent_materialization(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    _seed_source_snapshot(store)
    repo = SQLiteOperationalUniverseRepository(store)
    result = _result(OperationalUniverseCandidate("inst-a", False, "N"))

    v1 = repo.save("source-1", "nasdaq-operational-conservative", 1, NOW, result)
    v2 = repo.save("source-1", "nasdaq-operational-conservative", 2, NOW, result)

    assert v1 != v2
    with store.connection() as conn:
        assert conn.execute("SELECT count(*) FROM universe_snapshots").fetchone()[0] == 1
        assert (
            conn.execute("SELECT count(*) FROM operational_universe_snapshots").fetchone()[0] == 2
        )
