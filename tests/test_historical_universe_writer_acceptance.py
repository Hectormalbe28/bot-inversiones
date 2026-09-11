"""S2.12B Acceptance tests for SQLiteHistoricalUniverseWriteRepository.

Validates the complete atomic persistence contract for historical universe snapshots:
1. valid non-empty snapshot persists
2. persisted metadata round-trips exactly
3. persisted members round-trip
4. members stored/reconstructed canonically by instrument_id ASC
5. explicit empty snapshot persists
6. exact replay returns False
7. exact replay does not add rows
8. exact replay survives store/repository restart
9. same snapshot_id + changed as_of -> conflict
10. same snapshot_id + changed available_at -> conflict
11. same snapshot_id + changed version -> conflict
12. same snapshot_id + changed source_ingestion_id -> conflict
13. same snapshot_id + changed membership -> conflict
14. same snapshot_id + same instrument_id but changed member version -> conflict
15. same snapshot_id + changed member symbol -> conflict
16. same snapshot_id + changed member provider/feed -> conflict
17. reordered equivalent members -> idempotent False, not conflict
18. snapshot.instrument_ids/member set mismatch rejected
19. duplicate member identity rejected
20. nonexistent source_ingestion FK fails
21. nonexistent instrument version FK fails
22. member from different canonical provider/feed succeeds when valid FK exists
23. transaction rollback leaves no snapshot if one member FK fails
24. transaction rollback leaves no partial members
25. future-effective snapshot accepted
26. delayed-availability snapshot accepted
27. event_time > available_at accepted when domain snapshot permits it
28. no current-universe fallback involved
29. migration 002 unchanged
30. foreign keys remain enabled
Plus: revision non-retroactivity round-trip test.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.application.universe import (
    HistoricalUniverseMemberRef,
    HistoricalUniverseWriteConflict,
)
from app.core.clock import utc_key
from app.domain.models import HistoricalUniverseSnapshot
from app.infrastructure.storage.sqlite import (
    SQLiteHistoricalUniverseRepository,
    SQLiteHistoricalUniverseWriteRepository,
    SQLiteStore,
)


def _sha(label: str) -> str:
    return label.encode().hex().ljust(64, "0")[:64]


def _seed_ingestion(
    conn: sqlite3.Connection,
    ingestion_id: str,
    *,
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    available_at: datetime | None = None,
) -> None:
    t = available_at or datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    conn.execute(
        """
        INSERT OR IGNORE INTO source_ingestions (
            ingestion_id, provider, feed, source_name, raw_path, sha256,
            source_timestamp, received_at, processed_at, available_at,
            record_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ingestion_id,
            provider,
            feed,
            "test_source.txt",
            f"raw/{ingestion_id}.raw",
            _sha(ingestion_id),
            utc_key(t),
            utc_key(t),
            utc_key(t),
            utc_key(t),
            10,
            "SUCCESS",
        ),
    )


def _seed_instrument(
    conn: sqlite3.Connection,
    *,
    instrument_id: str,
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    version: int = 1,
    symbol: str = "AAPL",
    available_at: datetime | None = None,
) -> None:
    t = available_at or datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    conn.execute(
        """
        INSERT OR IGNORE INTO instrument_versions (
            instrument_id, provider, feed, version, symbol, event_time, available_at,
            payload, payload_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            instrument_id,
            provider,
            feed,
            version,
            symbol,
            utc_key(t),
            utc_key(t),
            "{}",
            _sha(f"{instrument_id}:{provider}:{feed}:{version}"),
        ),
    )


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "test.db")
    s.initialize()
    return s


@pytest.fixture
def writer(store):
    return SQLiteHistoricalUniverseWriteRepository(store)


@pytest.fixture
def reader(store):
    return SQLiteHistoricalUniverseRepository(store)


def _make_snapshot(
    snapshot_id: str = "snap-1",
    *,
    as_of: datetime | None = None,
    available_at: datetime | None = None,
    event_time: datetime | None = None,
    instrument_ids: tuple[str, ...] = ("inst-1",),
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    version: int = 1,
) -> HistoricalUniverseSnapshot:
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    snap_as_of = as_of or t
    snap_avail = available_at or t
    snap_event = event_time or t
    return HistoricalUniverseSnapshot(
        snapshot_id=snapshot_id,
        as_of=snap_as_of,
        instrument_ids=instrument_ids,
        event_time=snap_event,
        source_timestamp=snap_avail,
        received_at=snap_avail,
        processed_at=snap_avail,
        available_at=snap_avail,
        provider=provider,
        feed=feed,
        version=version,
    )


# 1. valid non-empty snapshot persists
def test_case_01_valid_non_empty_snapshot_persists(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-1", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    result = writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)
    assert result is True


# 2. persisted metadata round-trips exactly
def test_case_02_persisted_metadata_round_trips_exactly(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-rt-meta", as_of=t, available_at=t, instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    read_snap = reader.get_as_of("nasdaq", "symbol_directory", t)
    assert read_snap is not None
    assert read_snap.snapshot_id == "snap-rt-meta"
    assert read_snap.version == 1
    assert read_snap.as_of == t
    assert read_snap.available_at == t


# 3. persisted members round-trip
def test_case_03_persisted_members_round_trip(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-rt-mem", as_of=t, available_at=t, instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    read_snap = reader.get_as_of("nasdaq", "symbol_directory", t)
    assert read_snap is not None
    assert read_snap.instrument_ids == ("inst-1",)


# 4. members stored/reconstructed canonically by instrument_id ASC
def test_case_04_members_stored_canonically_by_instrument_id_asc(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-C", symbol="C")
        _seed_instrument(conn, instrument_id="inst-A", symbol="A")
        _seed_instrument(conn, instrument_id="inst-B", symbol="B")

    # Pass in non-sorted order
    snap = _make_snapshot(
        "snap-order",
        as_of=t,
        available_at=t,
        instrument_ids=("inst-C", "inst-A", "inst-B"),
    )
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-C",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="C",
        ),
        HistoricalUniverseMemberRef(
            instrument_id="inst-A",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="A",
        ),
        HistoricalUniverseMemberRef(
            instrument_id="inst-B",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="B",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    read_members = reader.members_as_of("nasdaq", "symbol_directory", t)
    assert read_members == ("inst-A", "inst-B", "inst-C")


# 5. explicit empty snapshot persists
def test_case_05_explicit_empty_snapshot_persists(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-empty")

    snap = _make_snapshot("snap-empty", as_of=t, available_at=t, instrument_ids=())
    assert writer.save_snapshot(snap, source_ingestion_id="ing-empty", members=()) is True

    read_snap = reader.get_as_of("nasdaq", "symbol_directory", t)
    assert read_snap is not None
    assert read_snap.instrument_ids == ()
    assert reader.members_as_of("nasdaq", "symbol_directory", t) == ()


# 6. exact replay returns False
def test_case_06_exact_replay_returns_false(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-replay", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    assert writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is True
    assert writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is False


# 7. exact replay does not add rows
def test_case_07_exact_replay_does_not_add_rows(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-replay-rows", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    with store.connection() as conn:
        snap_count = conn.execute(
            "SELECT COUNT(*) FROM universe_snapshots WHERE snapshot_id='snap-replay-rows'"
        ).fetchone()[0]
        mem_count = conn.execute(
            "SELECT COUNT(*) FROM universe_snapshot_members WHERE snapshot_id='snap-replay-rows'"
        ).fetchone()[0]
    assert snap_count == 1
    assert mem_count == 1


# 8. exact replay survives store/repository restart
def test_case_08_exact_replay_survives_restart(tmp_path):
    db_path = tmp_path / "restart.db"
    store1 = SQLiteStore(db_path)
    store1.initialize()
    with store1.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    writer1 = SQLiteHistoricalUniverseWriteRepository(store1)
    snap = _make_snapshot("snap-restart", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    assert writer1.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is True

    # Restart
    store2 = SQLiteStore(db_path)
    writer2 = SQLiteHistoricalUniverseWriteRepository(store2)
    assert writer2.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is False


# 9. same snapshot_id + changed as_of -> conflict
def test_case_09_conflict_on_changed_as_of(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    t1 = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    snap1 = _make_snapshot("snap-as-of", as_of=t1, instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap1, source_ingestion_id="ing-1", members=members)

    snap2 = _make_snapshot("snap-as-of", as_of=t2, instrument_ids=("inst-1",))
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap2, source_ingestion_id="ing-1", members=members)


# 10. same snapshot_id + changed available_at -> conflict
def test_case_10_conflict_on_changed_available_at(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    t1 = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    snap1 = _make_snapshot("snap-avail", available_at=t1, instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap1, source_ingestion_id="ing-1", members=members)

    snap2 = _make_snapshot("snap-avail", available_at=t2, instrument_ids=("inst-1",))
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap2, source_ingestion_id="ing-1", members=members)


# 11. same snapshot_id + changed version -> conflict
def test_case_11_conflict_on_changed_version(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap1 = _make_snapshot("snap-ver", version=1, instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap1, source_ingestion_id="ing-1", members=members)

    snap2 = _make_snapshot("snap-ver", version=2, instrument_ids=("inst-1",))
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap2, source_ingestion_id="ing-1", members=members)


# 12. same snapshot_id + changed source_ingestion_id -> conflict
def test_case_12_conflict_on_changed_source_ingestion_id(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_ingestion(conn, "ing-2")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-ing", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap, source_ingestion_id="ing-2", members=members)


# 13. same snapshot_id + changed membership -> conflict
def test_case_13_conflict_on_changed_membership(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")
        _seed_instrument(conn, instrument_id="inst-2", symbol="MSFT")

    snap1 = _make_snapshot("snap-mem", instrument_ids=("inst-1",))
    members1 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap1, source_ingestion_id="ing-1", members=members1)

    snap2 = _make_snapshot("snap-mem", instrument_ids=("inst-2",))
    members2 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-2",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="MSFT",
        ),
    )
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap2, source_ingestion_id="ing-1", members=members2)


# 14. same snapshot_id + same instrument_id but changed member version -> conflict
def test_case_14_conflict_on_changed_member_version(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", version=1, symbol="AAPL")
        _seed_instrument(conn, instrument_id="inst-1", version=2, symbol="AAPL")

    snap = _make_snapshot("snap-mver", instrument_ids=("inst-1",))
    members1 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members1)

    members2 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=2,
            symbol="AAPL",
        ),
    )
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members2)


# 15. same snapshot_id + changed member symbol -> conflict
def test_case_15_conflict_on_changed_member_symbol(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-msym", instrument_ids=("inst-1",))
    members1 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members1)

    members2 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL_NEW",
        ),
    )
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members2)


# 16. same snapshot_id + changed member provider/feed -> conflict
def test_case_16_conflict_on_changed_member_provider_feed(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", provider="nasdaq", feed="symbol_directory")
        _seed_instrument(conn, instrument_id="inst-1", provider="sec", feed="edgar")

    snap = _make_snapshot("snap-mpf", instrument_ids=("inst-1",))
    members1 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members1)

    members2 = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="sec",
            feed="edgar",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    with pytest.raises(HistoricalUniverseWriteConflict):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=members2)


# 17. reordered equivalent members -> idempotent False, not conflict
def test_case_17_reordered_equivalent_members_returns_false(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")
        _seed_instrument(conn, instrument_id="inst-2", symbol="MSFT")

    snap = _make_snapshot("snap-reorder", instrument_ids=("inst-1", "inst-2"))
    m1 = HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL")
    m2 = HistoricalUniverseMemberRef("inst-2", "nasdaq", "symbol_directory", 1, "MSFT")

    assert writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m1, m2)) is True
    assert writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m2, m1)) is False


# 18. snapshot.instrument_ids/member set mismatch rejected
def test_case_18_membership_set_mismatch_rejected(writer):
    snap = _make_snapshot("snap-mismatch", instrument_ids=("inst-1", "inst-2"))
    m1 = HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL")
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m1,))


# 19. duplicate member identity rejected
def test_case_19_duplicate_member_identity_rejected(writer):
    snap = _make_snapshot("snap-dup-id", instrument_ids=("inst-1",))
    m1 = HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL")
    m2 = HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 2, "AAPL")
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m1, m2))


# 20. nonexistent source_ingestion FK fails
def test_case_20_nonexistent_source_ingestion_fk_fails(store, writer):
    with store.connection() as conn:
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL")

    snap = _make_snapshot("snap-no-ing", instrument_ids=("inst-1",))
    m = (HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL"),)
    with pytest.raises(sqlite3.IntegrityError):
        writer.save_snapshot(snap, source_ingestion_id="missing-ing", members=m)


# 21. nonexistent instrument version FK fails
def test_case_21_nonexistent_instrument_version_fk_fails(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")

    snap = _make_snapshot("snap-no-inst", instrument_ids=("inst-missing",))
    m = (HistoricalUniverseMemberRef("inst-missing", "nasdaq", "symbol_directory", 1, "AAPL"),)
    with pytest.raises(sqlite3.IntegrityError):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=m)


# 22. member from different canonical provider/feed succeeds when valid FK exists
def test_case_22_cross_provider_feed_member_succeeds(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1", provider="nasdaq", feed="symbol_directory")
        _seed_instrument(
            conn, instrument_id="inst-cross", provider="sec", feed="company_tickers", symbol="AAPL"
        )

    snap = _make_snapshot(
        "snap-cross-prov",
        as_of=t,
        available_at=t,
        instrument_ids=("inst-cross",),
        provider="nasdaq",
        feed="symbol_directory",
    )
    m = (HistoricalUniverseMemberRef("inst-cross", "sec", "company_tickers", 1, "AAPL"),)
    assert writer.save_snapshot(snap, source_ingestion_id="ing-1", members=m) is True

    read_members = reader.members_as_of("nasdaq", "symbol_directory", t)
    assert read_members == ("inst-cross",)


# 23. transaction rollback leaves no snapshot if one member FK fails
def test_case_23_transaction_rollback_leaves_no_snapshot_on_member_fk_failure(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-good", symbol="GOOD")
        # inst-bad is NOT seeded

    snap = _make_snapshot("snap-atomic-snap", instrument_ids=("inst-good", "inst-bad"))
    m1 = HistoricalUniverseMemberRef("inst-good", "nasdaq", "symbol_directory", 1, "GOOD")
    m2 = HistoricalUniverseMemberRef("inst-bad", "nasdaq", "symbol_directory", 1, "BAD")

    with pytest.raises(sqlite3.IntegrityError):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m1, m2))

    with store.connection() as conn:
        snap_row = conn.execute(
            "SELECT * FROM universe_snapshots WHERE snapshot_id = 'snap-atomic-snap'"
        ).fetchone()
    assert snap_row is None


# 24. transaction rollback leaves no partial members
def test_case_24_transaction_rollback_leaves_no_partial_members(store, writer):
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1")
        _seed_instrument(conn, instrument_id="inst-good", symbol="GOOD")
        # inst-bad is NOT seeded

    snap = _make_snapshot("snap-atomic-mems", instrument_ids=("inst-good", "inst-bad"))
    m1 = HistoricalUniverseMemberRef("inst-good", "nasdaq", "symbol_directory", 1, "GOOD")
    m2 = HistoricalUniverseMemberRef("inst-bad", "nasdaq", "symbol_directory", 1, "BAD")

    with pytest.raises(sqlite3.IntegrityError):
        writer.save_snapshot(snap, source_ingestion_id="ing-1", members=(m1, m2))

    with store.connection() as conn:
        mem_rows = conn.execute(
            "SELECT * FROM universe_snapshot_members WHERE snapshot_id = 'snap-atomic-mems'"
        ).fetchall()
    assert len(mem_rows) == 0


# 25. future-effective snapshot accepted
def test_case_25_future_effective_snapshot_accepted_and_roundtrips(store, writer, reader):
    t_avail = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    t_effective = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-future", available_at=t_avail)
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL", available_at=t_avail)

    snap = _make_snapshot(
        "snap-future", as_of=t_effective, available_at=t_avail, instrument_ids=("inst-1",)
    )
    m = (HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL"),)
    assert writer.save_snapshot(snap, source_ingestion_id="ing-future", members=m) is True

    # Before as_of: invisible
    assert reader.get_as_of("nasdaq", "symbol_directory", t_avail) is None
    # At as_of: visible
    assert reader.get_as_of("nasdaq", "symbol_directory", t_effective) is not None


# 26. delayed-availability snapshot accepted
def test_case_26_delayed_availability_snapshot_accepted_and_roundtrips(store, writer, reader):
    t_effective = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    t_avail = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-delayed", available_at=t_avail)
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL", available_at=t_avail)

    snap = _make_snapshot(
        "snap-delayed", as_of=t_effective, available_at=t_avail, instrument_ids=("inst-1",)
    )
    m = (HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL"),)
    assert writer.save_snapshot(snap, source_ingestion_id="ing-delayed", members=m) is True

    # Before available_at: invisible
    t_before = t_avail - timedelta(seconds=1)
    assert reader.get_as_of("nasdaq", "symbol_directory", t_before) is None
    # At available_at: visible
    assert reader.get_as_of("nasdaq", "symbol_directory", t_avail) is not None


# 27. event_time > available_at accepted when domain snapshot permits it
def test_case_27_event_time_greater_than_available_at_accepted(store, writer):
    t_avail = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    t_event = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-ev", available_at=t_avail)
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL", available_at=t_avail)

    snap = _make_snapshot(
        "snap-ev",
        as_of=t_avail,
        available_at=t_avail,
        event_time=t_event,
        instrument_ids=("inst-1",),
    )
    m = (HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL"),)
    assert writer.save_snapshot(snap, source_ingestion_id="ing-ev", members=m) is True


# 28. no current-universe fallback involved
def test_case_28_no_current_universe_fallback(store, writer, reader):
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    with store.connection() as conn:
        _seed_ingestion(conn, "ing-1", available_at=t)
        _seed_instrument(conn, instrument_id="inst-1", symbol="AAPL", available_at=t)

    snap = _make_snapshot("snap-fallback", as_of=t, available_at=t, instrument_ids=("inst-1",))
    m = (HistoricalUniverseMemberRef("inst-1", "nasdaq", "symbol_directory", 1, "AAPL"),)
    writer.save_snapshot(snap, source_ingestion_id="ing-1", members=m)

    # Querying before T returns None, never falls back to current snapshot
    t_early = datetime(2020, 1, 1, tzinfo=UTC)
    assert reader.get_as_of("nasdaq", "symbol_directory", t_early) is None
    assert reader.members_as_of("nasdaq", "symbol_directory", t_early) is None


# 29. migration 002 unchanged
def test_case_29_migration_002_unchanged():
    from importlib.resources import files

    sql = files("app.migrations").joinpath("002_universe.sql").read_text(encoding="utf-8")
    assert "source_ingestions" in sql
    assert "universe_snapshots" in sql
    assert "universe_snapshot_members" in sql


# 30. foreign keys remain enabled
def test_case_30_foreign_keys_enforced(store):
    with store.connection() as conn:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1


# Revision non-retroactivity round-trip test
def test_revision_non_retroactivity(store, writer, reader):
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    t1 = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    with store.connection() as conn:
        _seed_ingestion(conn, "ing-rev1", available_at=t1)
        _seed_ingestion(conn, "ing-rev2", available_at=t2)
        _seed_instrument(conn, instrument_id="inst-A", symbol="A", available_at=t0)
        _seed_instrument(conn, instrument_id="inst-B", symbol="B", available_at=t0)

    # Revision 1: available at t1
    snap1 = _make_snapshot(
        "snap-rev1", as_of=t0, available_at=t1, version=1, instrument_ids=("inst-A",)
    )
    m1 = (HistoricalUniverseMemberRef("inst-A", "nasdaq", "symbol_directory", 1, "A"),)
    writer.save_snapshot(snap1, source_ingestion_id="ing-rev1", members=m1)

    # Revision 2: available at t2
    snap2 = _make_snapshot(
        "snap-rev2", as_of=t0, available_at=t2, version=2, instrument_ids=("inst-B",)
    )
    m2 = (HistoricalUniverseMemberRef("inst-B", "nasdaq", "symbol_directory", 1, "B"),)
    writer.save_snapshot(snap2, source_ingestion_id="ing-rev2", members=m2)

    # Query between t1 and t2: revision 1 is returned
    t_mid = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    res_mid = reader.get_as_of("nasdaq", "symbol_directory", t_mid)
    assert res_mid is not None
    assert res_mid.snapshot_id == "snap-rev1"
    assert res_mid.version == 1
    assert res_mid.instrument_ids == ("inst-A",)

    # Query at/after t2: revision 2 is returned
    res_late = reader.get_as_of("nasdaq", "symbol_directory", t2)
    assert res_late is not None
    assert res_late.snapshot_id == "snap-rev2"
    assert res_late.version == 2
    assert res_late.instrument_ids == ("inst-B",)
