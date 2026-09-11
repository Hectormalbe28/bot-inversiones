"""S2.12A Phase A: HistoricalUniverseWriteRepository contract tests.

Validates the application-layer write contract before SQLite implementation:
1. contract exists and is a runtime_checkable Protocol
2. new exact snapshot contract can return inserted=True
3. exact replay semantics defined as False
4. changed same snapshot_id defined as conflict (HistoricalUniverseWriteConflict)
5. snapshot/member membership sets must match (mismatch raises ValueError)
6. duplicate member instrument_id invalid (raises ValueError)
7. member order has no semantic meaning
8. empty snapshot valid
9. member provider/feed independent from snapshot provider/feed
10. no identity generation in contract (caller supplies snapshot_id)
11. source_ingestion_id is mandatory
12. contract does not expose current-universe fallback
"""

import inspect
from datetime import UTC, datetime

import pytest

from app.application.ports import HistoricalUniverseWriteRepository
from app.application.universe import (
    HistoricalUniverseMemberRef,
    HistoricalUniverseWriteConflict,
)
from app.domain.models import HistoricalUniverseSnapshot


class StubHistoricalUniverseWriteRepository:
    """In-memory stub strictly following the HistoricalUniverseWriteRepository contract."""

    def __init__(self) -> None:
        self._snapshots: dict[
            str,
            tuple[
                HistoricalUniverseSnapshot,
                str,
                frozenset[tuple[str, str, str, int, str]],
            ],
        ] = {}

    def save_snapshot(
        self,
        snapshot: HistoricalUniverseSnapshot,
        *,
        source_ingestion_id: str,
        members: tuple[HistoricalUniverseMemberRef, ...],
    ) -> bool:
        if not source_ingestion_id or not isinstance(source_ingestion_id, str):
            raise ValueError("source_ingestion_id is mandatory")

        # 6. Duplicate member check
        member_ids: list[str] = [m.instrument_id for m in members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Duplicate member instrument_id in members")

        # 5. Membership sets must match
        if set(snapshot.instrument_ids) != set(member_ids):
            raise ValueError("Snapshot instrument_ids and member refs set mismatch")

        canonical_members = frozenset(
            (m.instrument_id, m.provider, m.feed, m.instrument_version, m.symbol) for m in members
        )

        # Idempotency / Conflict check
        if snapshot.snapshot_id in self._snapshots:
            existing_snap, existing_ingestion, existing_members = self._snapshots[
                snapshot.snapshot_id
            ]
            if (
                existing_snap == snapshot
                and existing_ingestion == source_ingestion_id
                and existing_members == canonical_members
            ):
                return False
            raise HistoricalUniverseWriteConflict(
                f"Conflicting snapshot write for snapshot_id={snapshot.snapshot_id}"
            )

        self._snapshots[snapshot.snapshot_id] = (
            snapshot,
            source_ingestion_id,
            canonical_members,
        )
        return True


def _make_snapshot(
    snapshot_id: str = "snap-1",
    as_of: datetime | None = None,
    instrument_ids: tuple[str, ...] = ("inst-1",),
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    version: int = 1,
) -> HistoricalUniverseSnapshot:
    t = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    snap_as_of = as_of if as_of is not None else t
    return HistoricalUniverseSnapshot(
        snapshot_id=snapshot_id,
        as_of=snap_as_of,
        instrument_ids=instrument_ids,
        event_time=t,
        source_timestamp=t,
        received_at=t,
        processed_at=t,
        available_at=t,
        provider=provider,
        feed=feed,
        version=version,
    )


# 1. contract exists
def test_contract_exists_and_is_runtime_checkable():
    assert inspect.isclass(HistoricalUniverseWriteRepository)
    repo = StubHistoricalUniverseWriteRepository()
    assert isinstance(repo, HistoricalUniverseWriteRepository)


# 2. new exact snapshot contract can return inserted=True
def test_new_exact_snapshot_returns_inserted_true():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-new", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    result = repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members)
    assert result is True


# 3. exact replay semantics defined as False
def test_exact_replay_returns_false():
    repo = StubHistoricalUniverseWriteRepository()
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
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is True
    # Exact replay
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is False


# 4. changed same snapshot_id defined as conflict
def test_changed_same_snapshot_id_raises_conflict():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-conflict", instrument_ids=("inst-1",), version=1)
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is True

    # Replay with changed version
    snap_changed = _make_snapshot("snap-conflict", instrument_ids=("inst-1",), version=2)
    with pytest.raises(HistoricalUniverseWriteConflict):
        repo.save_snapshot(snap_changed, source_ingestion_id="ing-1", members=members)

    # Replay with changed member
    members_changed = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=2,  # different version
            symbol="AAPL",
        ),
    )
    with pytest.raises(HistoricalUniverseWriteConflict):
        repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members_changed)


# 5. snapshot/member membership sets must match
def test_membership_sets_must_match():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-set", instrument_ids=("inst-1", "inst-2"))
    # Only inst-1 supplied
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    with pytest.raises(ValueError, match="mismatch"):
        repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members)

    # Extra member supplied
    snap_single = _make_snapshot("snap-set-2", instrument_ids=("inst-1",))
    members_extra = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
        HistoricalUniverseMemberRef(
            instrument_id="inst-2",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="MSFT",
        ),
    )
    with pytest.raises(ValueError, match="mismatch"):
        repo.save_snapshot(snap_single, source_ingestion_id="ing-1", members=members_extra)


# 6. duplicate member instrument_id invalid
def test_duplicate_member_instrument_id_invalid():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-dup", instrument_ids=("inst-1",))
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="AAPL",
        ),
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=2,
            symbol="AAPL",
        ),
    )
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members)


# 7. member order has no semantic meaning
def test_member_order_has_no_semantic_meaning():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-order", instrument_ids=("inst-B", "inst-A", "inst-C"))
    members_order_1 = (
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
        HistoricalUniverseMemberRef(
            instrument_id="inst-C",
            provider="nasdaq",
            feed="symbol_directory",
            instrument_version=1,
            symbol="C",
        ),
    )
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members_order_1) is True

    # Reordered members in exact replay -> returns False (not conflict)
    members_order_2 = (
        members_order_1[2],
        members_order_1[0],
        members_order_1[1],
    )
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members_order_2) is False


# 8. empty snapshot valid
def test_empty_snapshot_valid():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot("snap-empty", instrument_ids=())
    result = repo.save_snapshot(snap, source_ingestion_id="ing-empty", members=())
    assert result is True
    # Idempotent replay of empty snapshot
    assert repo.save_snapshot(snap, source_ingestion_id="ing-empty", members=()) is False


# 9. member provider/feed independent from snapshot provider/feed
def test_member_provider_feed_independent_from_snapshot():
    repo = StubHistoricalUniverseWriteRepository()
    snap = _make_snapshot(
        "snap-cross",
        instrument_ids=("inst-1",),
        provider="nasdaq",
        feed="symbol_directory",
    )
    members = (
        HistoricalUniverseMemberRef(
            instrument_id="inst-1",
            provider="sec",  # cross-provider canonical reference
            feed="company_tickers",
            instrument_version=1,
            symbol="AAPL",
        ),
    )
    assert repo.save_snapshot(snap, source_ingestion_id="ing-1", members=members) is True


# 10. no identity generation in contract
def test_no_identity_generation_in_contract():
    # Caller supplies snapshot_id directly on HistoricalUniverseSnapshot
    snap = _make_snapshot("caller-supplied-id", instrument_ids=())
    assert snap.snapshot_id == "caller-supplied-id"


# 11. source_ingestion_id is mandatory
def test_source_ingestion_id_is_mandatory():
    params = inspect.signature(HistoricalUniverseWriteRepository.save_snapshot).parameters
    assert "source_ingestion_id" in params
    assert params["source_ingestion_id"].kind == inspect.Parameter.KEYWORD_ONLY


# 12. contract does not expose current-universe fallback
def test_contract_does_not_expose_current_universe_fallback():
    repo_methods = [
        name
        for name, _ in inspect.getmembers(
            HistoricalUniverseWriteRepository, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    ]
    assert "get_current" not in repo_methods
    assert "get_latest" not in repo_methods
    assert "fallback" not in repo_methods
    assert repo_methods == ["save_snapshot"]
