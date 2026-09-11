"""S2.7B acceptance tests for HistoricalUniverseRepository (intentional RED until S2.7C)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.clock import utc_key
from app.infrastructure.storage.sqlite import SQLiteStore


def repository(store: SQLiteStore):
    from app.infrastructure.storage import sqlite as sqlite_mod

    cls = getattr(sqlite_mod, "SQLiteHistoricalUniverseRepository", None)
    if cls is None:
        raise ImportError("SQLiteHistoricalUniverseRepository is not implemented")
    return cls(store)


def _store(settings) -> SQLiteStore:
    store = SQLiteStore(settings.database_path)
    store.initialize()
    return store


def _dt(*parts: int) -> datetime:
    if len(parts) == 3:
        year, month, day = parts
        return datetime(year, month, day, tzinfo=UTC)
    year, month, day, hour = parts
    return datetime(year, month, day, hour, tzinfo=UTC)


def _sha(label: str) -> str:
    return label.encode().hex().ljust(64, "0")[:64]


def _ensure_instrument(
    conn,
    *,
    instrument_id: str,
    provider: str,
    feed: str,
    version: int,
    symbol: str,
    at: datetime,
) -> None:
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
            utc_key(at),
            utc_key(at),
            "{}",
            _sha(f"{instrument_id}:{provider}:{feed}:{version}"),
        ),
    )


def insert_snapshot(
    conn,
    *,
    snapshot_id: str,
    provider: str,
    feed: str,
    version: int,
    as_of: datetime,
    available_at: datetime,
    members: tuple[tuple[str, int, str], ...] = (),
    event_time: datetime | None = None,
    published_at: datetime | None = None,
    source_timestamp: datetime | None = None,
    received_at: datetime | None = None,
    processed_at: datetime | None = None,
) -> None:
    event_time = as_of if event_time is None else event_time
    source_timestamp = available_at if source_timestamp is None else source_timestamp
    received_at = available_at if received_at is None else received_at
    processed_at = available_at if processed_at is None else processed_at
    ingestion_id = f"ing-{snapshot_id}"
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
            provider,
            feed,
            "fixture.txt",
            f"raw/{snapshot_id}.txt",
            _sha(ingestion_id),
            utc_key(source_timestamp),
            utc_key(received_at),
            utc_key(processed_at),
            utc_key(available_at),
            len(members),
            "SUCCESS",
        ),
    )
    conn.execute(
        """
        INSERT INTO universe_snapshots (
            snapshot_id, provider, feed, version, as_of, event_time,
            published_at, source_timestamp, received_at, processed_at,
            available_at, source_ingestion_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            provider,
            feed,
            version,
            utc_key(as_of),
            utc_key(event_time),
            None if published_at is None else utc_key(published_at),
            utc_key(source_timestamp),
            utc_key(received_at),
            utc_key(processed_at),
            utc_key(available_at),
            ingestion_id,
        ),
    )
    for instrument_id, instrument_version, symbol in members:
        _ensure_instrument(
            conn,
            instrument_id=instrument_id,
            provider=provider,
            feed=feed,
            version=instrument_version,
            symbol=symbol,
            at=available_at,
        )
        conn.execute(
            """
            INSERT INTO universe_snapshot_members (
                snapshot_id, instrument_id, provider, feed, instrument_version, symbol
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (snapshot_id, instrument_id, provider, feed, instrument_version, symbol),
        )


def test_case_1_no_snapshot(settings):
    store = _store(settings)
    repo = repository(store)
    query_time = _dt(2026, 7, 1)
    assert repo.get_as_of("P", "F", query_time) is None
    assert repo.members_as_of("P", "F", query_time) is None


def test_case_2_explicit_empty_snapshot(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-empty",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(),
        )
    repo = repository(store)
    query_time = _dt(2026, 7, 1)
    snapshot = repo.get_as_of("P", "F", query_time)
    assert snapshot is not None
    assert snapshot.instrument_ids == ()
    assert repo.members_as_of("P", "F", query_time) == ()


def test_case_3_normal_eligible_snapshot_reconstructs_provenance(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1, 12)
    published_at = _dt(2026, 7, 1, 10)
    source_timestamp = _dt(2026, 7, 1, 8)
    received_at = _dt(2026, 7, 1, 9)
    processed_at = _dt(2026, 7, 1, 11)
    event_time = _dt(2026, 6, 30)
    members = (("INST-A", 1, "AAA"), ("INST-B", 1, "BBB"))
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-normal",
            provider="nasdaq",
            feed="listed",
            version=3,
            as_of=as_of,
            available_at=available_at,
            members=members,
            event_time=event_time,
            published_at=published_at,
            source_timestamp=source_timestamp,
            received_at=received_at,
            processed_at=processed_at,
        )
    repo = repository(store)
    query_time = _dt(2026, 7, 2)
    snapshot = repo.get_as_of("nasdaq", "listed", query_time)
    assert snapshot is not None
    assert snapshot.snapshot_id == "snap-normal"
    assert snapshot.provider == "nasdaq"
    assert snapshot.feed == "listed"
    assert snapshot.version == 3
    assert snapshot.as_of == as_of
    assert snapshot.event_time == event_time
    assert snapshot.published_at == published_at
    assert snapshot.source_timestamp == source_timestamp
    assert snapshot.received_at == received_at
    assert snapshot.processed_at == processed_at
    assert snapshot.available_at == available_at
    assert snapshot.instrument_ids == ("INST-A", "INST-B")
    assert repo.members_as_of("nasdaq", "listed", query_time) == ("INST-A", "INST-B")


def test_case_4_future_effective_but_already_known(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-future-effective",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 6, 15),
            available_at=_dt(2026, 6, 1),
            members=(("INST-1", 1, "AAA"),),
        )
    repo = repository(store)
    assert repo.get_as_of("P", "F", _dt(2026, 6, 5)) is None
    assert repo.members_as_of("P", "F", _dt(2026, 6, 5)) is None
    selected = repo.get_as_of("P", "F", _dt(2026, 6, 15))
    assert selected is not None
    assert selected.snapshot_id == "snap-future-effective"
    assert repo.members_as_of("P", "F", _dt(2026, 6, 15)) == ("INST-1",)


def test_case_5_delayed_availability(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-delayed",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 6, 30),
            available_at=_dt(2026, 7, 1),
            members=(("INST-1", 1, "AAA"),),
        )
    repo = repository(store)
    assert repo.get_as_of("P", "F", _dt(2026, 6, 30)) is None
    assert repo.members_as_of("P", "F", _dt(2026, 6, 30)) is None
    selected = repo.get_as_of("P", "F", _dt(2026, 7, 1))
    assert selected is not None
    assert selected.snapshot_id == "snap-delayed"
    assert repo.members_as_of("P", "F", _dt(2026, 7, 1)) == ("INST-1",)


def test_case_6_inclusive_boundaries(settings):
    store = _store(settings)
    boundary = _dt(2026, 7, 1, 12)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-boundary",
            provider="P",
            feed="F",
            version=1,
            as_of=boundary,
            available_at=boundary,
            members=(("INST-1", 1, "AAA"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F", boundary)
    assert selected is not None
    assert selected.snapshot_id == "snap-boundary"
    assert repo.members_as_of("P", "F", boundary) == ("INST-1",)


def test_case_7_latest_effective_snapshot_wins_first(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-older-effective",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 6, 30),
            available_at=_dt(2026, 7, 10),
            members=(("INST-OLD", 1, "OLD"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-newer-effective",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 7, 5),
            available_at=_dt(2026, 7, 6),
            members=(("INST-NEW", 1, "NEW"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F", _dt(2026, 7, 10))
    assert selected is not None
    assert selected.snapshot_id == "snap-newer-effective"
    assert selected.as_of == _dt(2026, 7, 5)
    assert repo.members_as_of("P", "F", _dt(2026, 7, 10)) == ("INST-NEW",)


def test_case_8_revision_non_retroactivity(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-rev-1",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=_dt(2026, 7, 1),
            members=(("INST-V1", 1, "V1"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-rev-2",
            provider="P",
            feed="F",
            version=2,
            as_of=as_of,
            available_at=_dt(2026, 7, 3),
            members=(("INST-V2", 1, "V2"),),
        )
    repo = repository(store)
    july_2 = repo.get_as_of("P", "F", _dt(2026, 7, 2))
    assert july_2 is not None
    assert july_2.snapshot_id == "snap-rev-1"
    assert july_2.version == 1
    assert repo.members_as_of("P", "F", _dt(2026, 7, 2)) == ("INST-V1",)
    july_4 = repo.get_as_of("P", "F", _dt(2026, 7, 4))
    assert july_4 is not None
    assert july_4.snapshot_id == "snap-rev-2"
    assert july_4.version == 2
    assert repo.members_as_of("P", "F", _dt(2026, 7, 4)) == ("INST-V2",)


def test_case_9_version_tie_break(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-aaa",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-LOW", 1, "LOW"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-zzz",
            provider="P",
            feed="F",
            version=4,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-HIGH", 1, "HIGH"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F", _dt(2026, 7, 2))
    assert selected is not None
    assert selected.snapshot_id == "snap-zzz"
    assert selected.version == 4
    assert repo.members_as_of("P", "F", _dt(2026, 7, 2)) == ("INST-HIGH",)


def test_case_10_final_deterministic_snapshot_id_tie(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-z",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-Z", 1, "ZZZ"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-a",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-A", 1, "AAA"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F", _dt(2026, 7, 2))
    assert selected is not None
    assert selected.snapshot_id == "snap-a"
    assert repo.members_as_of("P", "F", _dt(2026, 7, 2)) == ("INST-A",)


def test_case_11_provider_isolation(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-p1",
            provider="P1",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-P1", 1, "P1"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-p2",
            provider="P2",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-P2", 1, "P2"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P1", "F", _dt(2026, 7, 2))
    assert selected is not None
    assert selected.provider == "P1"
    assert selected.snapshot_id == "snap-p1"
    assert repo.members_as_of("P1", "F", _dt(2026, 7, 2)) == ("INST-P1",)
    assert repo.get_as_of("P2", "F", _dt(2026, 7, 2)).snapshot_id == "snap-p2"


def test_case_12_feed_isolation(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 30)
    available_at = _dt(2026, 7, 1)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-f1",
            provider="P",
            feed="F1",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-F1", 1, "F1"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-f2",
            provider="P",
            feed="F2",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-F2", 1, "F2"),),
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F1", _dt(2026, 7, 2))
    assert selected is not None
    assert selected.feed == "F1"
    assert selected.snapshot_id == "snap-f1"
    assert repo.members_as_of("P", "F1", _dt(2026, 7, 2)) == ("INST-F1",)
    assert repo.get_as_of("P", "F2", _dt(2026, 7, 2)).snapshot_id == "snap-f2"


def test_case_13_canonical_membership_order(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-order",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 6, 30),
            available_at=_dt(2026, 7, 1),
            members=(
                ("INST-C", 1, "CCC"),
                ("INST-A", 1, "AAA"),
                ("INST-B", 1, "BBB"),
            ),
        )
    repo = repository(store)
    query_time = _dt(2026, 7, 1)
    assert repo.members_as_of("P", "F", query_time) == ("INST-A", "INST-B", "INST-C")
    selected = repo.get_as_of("P", "F", query_time)
    assert selected is not None
    assert selected.instrument_ids == ("INST-A", "INST-B", "INST-C")


def test_case_14_ticker_change_does_not_change_identity(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-old-ticker",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 6, 30),
            available_at=_dt(2026, 7, 1),
            members=(("INST-1", 1, "OLD"),),
        )
        insert_snapshot(
            conn,
            snapshot_id="snap-new-ticker",
            provider="P",
            feed="F",
            version=1,
            as_of=_dt(2026, 8, 31),
            available_at=_dt(2026, 9, 1),
            members=(("INST-1", 2, "NEW"),),
        )
    repo = repository(store)
    early = repo.members_as_of("P", "F", _dt(2026, 7, 15))
    later = repo.members_as_of("P", "F", _dt(2026, 9, 2))
    assert early == ("INST-1",)
    assert later == ("INST-1",)
    assert "OLD" not in early
    assert "NEW" not in later


def test_case_15_no_current_or_latest_fallback(settings):
    store = _store(settings)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-latest-ineligible",
            provider="P",
            feed="F",
            version=9,
            as_of=_dt(2026, 7, 5),
            available_at=_dt(2026, 7, 6),
            members=(("INST-LATEST", 1, "LAT"),),
        )
    repo = repository(store)
    query_time = _dt(2026, 6, 1)
    assert repo.get_as_of("P", "F", query_time) is None
    assert repo.members_as_of("P", "F", query_time) is None


def test_case_16_event_time_is_not_an_eligibility_axis(settings):
    store = _store(settings)
    as_of = _dt(2026, 6, 15)
    available_at = _dt(2026, 6, 1)
    event_time = _dt(2026, 6, 20)
    query_time = _dt(2026, 6, 15)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-event-time",
            provider="P",
            feed="F",
            version=1,
            as_of=as_of,
            available_at=available_at,
            members=(("INST-1", 1, "AAA"),),
            event_time=event_time,
        )
    repo = repository(store)
    selected = repo.get_as_of("P", "F", query_time)
    assert selected is not None
    assert selected.snapshot_id == "snap-event-time"
    assert selected.event_time == event_time
    assert selected.event_time > query_time
    assert repo.members_as_of("P", "F", query_time) == ("INST-1",)


def test_case_17_naive_datetime_rejected(settings):
    store = _store(settings)
    repo = repository(store)
    naive = datetime(2026, 7, 1, 12, 0)
    with pytest.raises((ValueError, TypeError), match="timezone|tzinfo|aware"):
        repo.get_as_of("P", "F", naive)
    with pytest.raises((ValueError, TypeError), match="timezone|tzinfo|aware"):
        repo.members_as_of("P", "F", naive)


def test_case_18_non_utc_aware_datetime_normalizes(settings):
    store = _store(settings)
    cutoff_utc = datetime(2026, 7, 1, 12, tzinfo=UTC)
    with store.connection() as conn:
        insert_snapshot(
            conn,
            snapshot_id="snap-utc-cutoff",
            provider="P",
            feed="F",
            version=1,
            as_of=cutoff_utc,
            available_at=cutoff_utc,
            members=(("INST-1", 1, "AAA"),),
        )
    repo = repository(store)
    offset_query = datetime(2026, 7, 1, 8, tzinfo=timezone(timedelta(hours=-4)))
    utc_result = repo.get_as_of("P", "F", cutoff_utc)
    offset_result = repo.get_as_of("P", "F", offset_query)
    assert utc_result is not None
    assert offset_result is not None
    assert utc_result.snapshot_id == offset_result.snapshot_id == "snap-utc-cutoff"
    assert repo.members_as_of("P", "F", offset_query) == ("INST-1",)
    assert repo.members_as_of("P", "F", cutoff_utc) == ("INST-1",)
