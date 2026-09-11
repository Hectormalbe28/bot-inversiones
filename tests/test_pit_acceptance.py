import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.clock import utc_key
from app.domain.models import Instrument
from app.infrastructure.storage.sqlite import InstrumentRepository, SQLiteStore


def test_case_1_future_availability_invisible(settings, evidence):
    """CASE 1: Revision with available_at = T+1 must be invisible at as_of = T."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    t = evidence["available_at"]
    t_plus_1 = t + timedelta(days=1)

    rev = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company",
        **(
            evidence
            | {
                "received_at": t_plus_1,
                "processed_at": t_plus_1,
                "available_at": t_plus_1,
            }
        ),
    )
    repo.save(rev)

    assert repo.get_as_of("ABC", t) is None


def test_case_2_exact_boundary_visible(settings, evidence):
    """CASE 2: Revision with available_at = T must be visible at as_of = T (inclusive boundary)."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    t = evidence["available_at"]
    rev = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company",
        **evidence,
    )
    repo.save(rev)

    res = repo.get_as_of("ABC", t)
    assert res is not None
    assert res.instrument_id == "inst-1"
    assert res.available_at == t


def test_case_3_later_revision_invisible_historically(settings, evidence):
    """CASE 3: Later revision B (Jan 20) is invisible at as_of Jan 15;
    query returns Revision A (Jan 10).
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    jan_10 = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    jan_15 = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    jan_20 = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)

    rev_a = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company-RevA",
        **(
            evidence
            | {
                "version": 1,
                "event_time": jan_10,
                "source_timestamp": jan_10,
                "received_at": jan_10,
                "processed_at": jan_10,
                "available_at": jan_10,
            }
        ),
    )
    repo.save(rev_a)

    rev_b = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company-RevB",
        **(
            evidence
            | {
                "version": 2,
                "event_time": jan_20,
                "source_timestamp": jan_20,
                "received_at": jan_20,
                "processed_at": jan_20,
                "available_at": jan_20,
            }
        ),
    )
    repo.save(rev_b)

    res = repo.get_as_of("ABC", jan_15)
    assert res is not None
    assert res.version == 1
    assert res.name == "Company-RevA"
    assert res.available_at == jan_10


def test_case_4_current_latest_may_differ_from_historical(settings, evidence):
    """CASE 4: Historical query at Jan 15 returns Rev A,
    while latest_available at Jan 25 returns Rev B.

    Proves historical queries cannot fall back to current state.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    jan_10 = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    jan_15 = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    jan_20 = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    jan_25 = datetime(2026, 1, 25, 12, 0, tzinfo=UTC)

    rev_a = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company-RevA",
        **(
            evidence
            | {
                "version": 1,
                "event_time": jan_10,
                "source_timestamp": jan_10,
                "received_at": jan_10,
                "processed_at": jan_10,
                "available_at": jan_10,
            }
        ),
    )
    repo.save(rev_a)

    rev_b = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company-RevB",
        **(
            evidence
            | {
                "version": 2,
                "event_time": jan_20,
                "source_timestamp": jan_20,
                "received_at": jan_20,
                "processed_at": jan_20,
                "available_at": jan_20,
            }
        ),
    )
    repo.save(rev_b)

    hist = repo.get_as_of("ABC", jan_15)
    assert hist is not None
    assert hist.version == 1

    # latest_available at Jan 25 reflects current/latest state (Rev B)
    latest = repo.latest_available("ABC", jan_25)
    assert latest is not None
    assert latest.version == 2
    assert hist.version != latest.version


def test_case_5_naive_as_of_rejected(settings, evidence):
    """CASE 5: Datetime without timezone must be rejected with validation/domain error."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    rev = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company",
        **evidence,
    )
    repo.save(rev)

    naive_dt = datetime(2026, 9, 1, 20, 0)
    with pytest.raises((ValueError, TypeError), match="timezone|tzinfo|aware"):
        repo.get_as_of("ABC", naive_dt)


def test_case_6_aware_non_utc_as_of_normalized(settings, evidence):
    """CASE 6: Aware non-UTC datetime is normalized and queries the correct instant in UTC."""
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    utc_dt = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
    rev = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Company",
        **(
            evidence
            | {
                "event_time": utc_dt,
                "source_timestamp": utc_dt,
                "received_at": utc_dt,
                "processed_at": utc_dt,
                "available_at": utc_dt,
            }
        ),
    )
    repo.save(rev)

    # 15:00 at UTC-5 is exactly 20:00 UTC
    non_utc_dt = datetime(2026, 9, 1, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
    res = repo.get_as_of("ABC", non_utc_dt)
    assert res is not None
    assert res.instrument_id == "inst-1"


def test_case_7_future_scheduled_event_eligible(settings):
    """CASE 7: Information known in advance (available_at <= as_of < event_time) is eligible.

    Do NOT filter merely because event_time is future.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    as_of = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    available_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
    event_time = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)

    # Insert a version directly into storage to test repository PIT eligibility logic
    # without coupling to Pydantic domain models that may validate event_time <= available_at
    payload = json.dumps(
        {
            "instrument_id": "future-inst-1",
            "symbol": "FUT",
            "name": "FutureCorp",
            "currency": "USD",
            "asset_class": "equity",
            "active": True,
            "cik": None,
            "exchange": None,
            "event_time": event_time.isoformat(),
            "source_timestamp": available_at.isoformat(),
            "received_at": available_at.isoformat(),
            "processed_at": available_at.isoformat(),
            "available_at": available_at.isoformat(),
            "provider": "fixture",
            "feed": "test",
            "version": 1,
        }
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO instrument_versions "
            "(instrument_id, provider, feed, version, symbol, "
            "event_time, available_at, payload, payload_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "future-inst-1",
                "fixture",
                "test",
                1,
                "FUT",
                utc_key(event_time),
                utc_key(available_at),
                payload,
                digest,
            ),
        )

    # Must be eligible at as_of because available_at <= as_of, even though event_time > as_of
    res = repo.get_as_of("FUT", as_of)
    assert res is not None, (
        "Record must be eligible at as_of when available_at <= as_of, even if event_time > as_of"
    )
    assert res.symbol == "FUT"


def test_case_8_non_retroactivity(settings, evidence):
    """CASE 8: Performing a historical query at T, adding a revision at T+1,
    and re-querying at T returns the same result.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    t = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    rev_1 = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Version1",
        **(
            evidence
            | {
                "version": 1,
                "event_time": t,
                "source_timestamp": t,
                "received_at": t,
                "processed_at": t,
                "available_at": t,
            }
        ),
    )
    repo.save(rev_1)

    # Historical query at T
    first_result = repo.get_as_of("ABC", t)
    assert first_result is not None
    assert first_result.name == "Version1"

    # Add revision with available_at > T
    t_plus_1 = t + timedelta(days=5)
    rev_2 = Instrument(
        instrument_id="inst-1",
        symbol="ABC",
        name="Version2",
        **(
            evidence
            | {
                "version": 2,
                "event_time": t_plus_1,
                "source_timestamp": t_plus_1,
                "received_at": t_plus_1,
                "processed_at": t_plus_1,
                "available_at": t_plus_1,
            }
        ),
    )
    repo.save(rev_2)

    # Repeat historical query at T
    second_result = repo.get_as_of("ABC", t)
    assert second_result is not None
    assert second_result.name == "Version1"
    assert second_result == first_result


def test_case_9_scan_as_of_temporal_invariant(settings, evidence):
    """CASE 9: For every result returned by scan_as_of(T),
    result.available_at <= T without exception.
    """
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)

    t = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    t_minus_1 = t - timedelta(days=2)
    t_plus_1 = t + timedelta(days=2)

    # Add record eligible at T
    repo.save(
        Instrument(
            instrument_id="inst-eligible",
            symbol="ELG",
            name="Eligible",
            **(
                evidence
                | {
                    "version": 1,
                    "event_time": t_minus_1,
                    "source_timestamp": t_minus_1,
                    "received_at": t_minus_1,
                    "processed_at": t_minus_1,
                    "available_at": t_minus_1,
                }
            ),
        )
    )

    # Add record ineligible at T (future available_at)
    repo.save(
        Instrument(
            instrument_id="inst-ineligible",
            symbol="INELG",
            name="Ineligible",
            **(
                evidence
                | {
                    "version": 1,
                    "event_time": t_plus_1,
                    "source_timestamp": t_plus_1,
                    "received_at": t_plus_1,
                    "processed_at": t_plus_1,
                    "available_at": t_plus_1,
                }
            ),
        )
    )

    # scan_as_of must return only records where available_at <= T
    results = repo.scan_as_of(t)
    assert len(results) > 0
    for record in results:
        assert record.available_at <= t, f"Invariant violated: {record.available_at} > {t}"
