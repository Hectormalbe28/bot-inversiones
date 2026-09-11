from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.models import HistoricalUniverseSnapshot


def test_valid_snapshot(evidence):
    """CASE 1: Valid snapshot verification."""
    effective_as_of = datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    members = ("inst-1", "inst-2", "inst-3")
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-20260910",
        as_of=effective_as_of,
        instrument_ids=members,
        **evidence,
    )
    assert snap.snapshot_id == "snap-20260910"
    assert snap.as_of == effective_as_of
    assert snap.instrument_ids == members
    assert snap.provider == evidence["provider"]
    assert snap.feed == evidence["feed"]
    assert snap.version == evidence["version"]


def test_naive_as_of_rejected(evidence):
    """CASE 2: Naïve as_of rejected."""
    naive_dt = datetime(2026, 9, 10, 12, 0)
    with pytest.raises(ValidationError, match="timezone"):
        HistoricalUniverseSnapshot(
            snapshot_id="snap-1",
            as_of=naive_dt,
            instrument_ids=("inst-1",),
            **evidence,
        )


def test_aware_non_utc_as_of_normalized(evidence):
    """CASE 3: Aware non-UTC as_of normalized to UTC."""
    offset_dt = datetime(2026, 9, 10, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-1",
        as_of=offset_dt,
        instrument_ids=("inst-1",),
        **evidence,
    )
    assert snap.as_of == datetime(2026, 9, 10, 20, 0, tzinfo=UTC)
    assert snap.as_of.tzinfo == UTC


def test_future_effective_snapshot_allowed(evidence):
    """CASE 4: Future-effective snapshot allowed (available_at < as_of)."""
    t_known = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    t_effective = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    data = evidence | {
        "event_time": t_known,
        "source_timestamp": t_known,
        "received_at": t_known,
        "processed_at": t_known,
        "available_at": t_known,
    }
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-future",
        as_of=t_effective,
        instrument_ids=("inst-1",),
        **data,
    )
    assert snap.available_at < snap.as_of


def test_delayed_availability_allowed(evidence):
    """CASE 5: Delayed availability allowed (as_of < available_at)."""
    t_effective = datetime(2025, 6, 30, 23, 59, tzinfo=UTC)
    t_known = datetime(2025, 7, 1, 10, 0, tzinfo=UTC)
    data = evidence | {
        "event_time": t_known,
        "source_timestamp": t_known,
        "received_at": t_known,
        "processed_at": t_known,
        "available_at": t_known,
    }
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-delayed",
        as_of=t_effective,
        instrument_ids=("inst-1",),
        **data,
    )
    assert snap.as_of < snap.available_at


def test_duplicate_instrument_ids_rejected(evidence):
    """CASE 6: Duplicate instrument IDs rejected without silent deduplication."""
    with pytest.raises(ValidationError, match="duplicate"):
        HistoricalUniverseSnapshot(
            snapshot_id="snap-1",
            as_of=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
            instrument_ids=("instrument-1", "instrument-1"),
            **evidence,
        )


def test_multiple_unique_instrument_ids_accepted(evidence):
    """CASE 7: Multiple unique stable instrument IDs accepted."""
    members = ("instrument-1", "instrument-2", "instrument-3")
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-multi",
        as_of=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        instrument_ids=members,
        **evidence,
    )
    assert snap.instrument_ids == members
    assert len(snap.instrument_ids) == 3


def test_empty_membership_representable(evidence):
    """CASE 8: Empty membership representable at domain-contract level."""
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-empty",
        as_of=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        instrument_ids=(),
        **evidence,
    )
    assert snap.instrument_ids == ()


def test_extra_fields_rejected(evidence):
    """CASE 9: Extra unknown fields rejected according to Contract behavior."""
    with pytest.raises(ValidationError):
        HistoricalUniverseSnapshot(
            snapshot_id="snap-1",
            as_of=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
            instrument_ids=("inst-1",),
            market_cap_tier="large",  # Unknown field
            **evidence,
        )


def test_provenance_preserved(evidence):
    """CASE 10: Inherited temporal and provenance fields remain intact."""
    snap = HistoricalUniverseSnapshot(
        snapshot_id="snap-prov",
        as_of=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        instrument_ids=("inst-1",),
        **evidence,
    )
    assert snap.provider == evidence["provider"]
    assert snap.feed == evidence["feed"]
    assert snap.version == evidence["version"]
    assert snap.available_at == evidence["available_at"]
    assert snap.source_timestamp == evidence["source_timestamp"]
    assert snap.received_at == evidence["received_at"]
    assert snap.processed_at == evidence["processed_at"]
    assert snap.event_time == evidence["event_time"]
