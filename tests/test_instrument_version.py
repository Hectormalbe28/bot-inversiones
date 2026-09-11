from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.models import InstrumentVersion


def test_valid_instrument_version(evidence):
    """1. Valid InstrumentVersion creation with all required and optional fields."""
    valid_from = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    valid_to = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    iv = InstrumentVersion(
        instrument_id="inst-123",
        symbol="AAPL",
        exchange="NASDAQ",
        valid_from=valid_from,
        valid_to=valid_to,
        listing_date=date(2020, 1, 1),
        delisting_date=date(2026, 12, 31),
        status="active",
        **evidence,
    )
    assert iv.instrument_id == "inst-123"
    assert iv.symbol == "AAPL"
    assert iv.exchange == "NASDAQ"
    assert iv.valid_from == valid_from
    assert iv.valid_to == valid_to
    assert iv.listing_date == date(2020, 1, 1)
    assert iv.delisting_date == date(2026, 12, 31)
    assert iv.status == "active"


def test_naive_valid_from_rejected(evidence):
    """2. Naïve valid_from is rejected."""
    naive_dt = datetime(2026, 1, 1, 0, 0)
    with pytest.raises(ValidationError, match="timezone"):
        InstrumentVersion(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=naive_dt,
            **evidence,
        )


def test_aware_non_utc_valid_from_normalized_to_utc(evidence):
    """3. Aware non-UTC valid_from normalized to UTC."""
    offset_dt = datetime(2026, 1, 1, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
    iv = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=offset_dt,
        **evidence,
    )
    assert iv.valid_from == datetime(2026, 1, 1, 20, 0, tzinfo=UTC)
    assert iv.valid_from.tzinfo == UTC


def test_valid_to_less_than_or_equal_to_valid_from_rejected(evidence):
    """4. valid_to <= valid_from rejected (zero-length or reversed interval)."""
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    # valid_to == valid_from
    with pytest.raises(ValidationError, match="valid_to"):
        InstrumentVersion(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            valid_to=t0,
            **evidence,
        )

    # valid_to < valid_from
    with pytest.raises(ValidationError, match="valid_to"):
        InstrumentVersion(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            valid_to=t0 - timedelta(hours=1),
            **evidence,
        )


def test_valid_to_none_accepted(evidence):
    """5. valid_to=None accepted (open-ended validity interval)."""
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    iv = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=t0,
        valid_to=None,
        **evidence,
    )
    assert iv.valid_to is None


def test_future_effective_version_allowed_available_at_before_valid_from(evidence):
    """6. Future-effective version allowed: available_at < valid_from."""
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    valid_from = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    data = evidence | {
        "event_time": t0,
        "source_timestamp": t0,
        "received_at": t0,
        "processed_at": t0,
        "available_at": t0,
    }

    iv = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=valid_from,
        **data,
    )
    assert iv.available_at < iv.valid_from


def test_listing_and_delisting_date_valid_ordering(evidence):
    """7. listing_date/delisting_date valid ordering (delisting_date >= listing_date)."""
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    # delisting_date > listing_date
    iv1 = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=t0,
        listing_date=date(2020, 1, 1),
        delisting_date=date(2026, 1, 1),
        **evidence,
    )
    assert iv1.listing_date < iv1.delisting_date

    # delisting_date == listing_date
    iv2 = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=t0,
        listing_date=date(2020, 1, 1),
        delisting_date=date(2020, 1, 1),
        **evidence,
    )
    assert iv2.listing_date == iv2.delisting_date


def test_delisting_date_before_listing_date_rejected(evidence):
    """8. delisting_date before listing_date rejected."""
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="delisting_date"):
        InstrumentVersion(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            listing_date=date(2026, 1, 1),
            delisting_date=date(2025, 1, 1),
            **evidence,
        )


def test_invalid_status_rejected(evidence):
    """9. Invalid status rejected."""
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        InstrumentVersion(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            status="pending_ipo",
            **evidence,
        )
