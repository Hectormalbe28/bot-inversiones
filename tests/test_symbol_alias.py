from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.models import SymbolAlias


def test_valid_alias_open_ended_interval(evidence):
    """1. Valid alias with open-ended interval (valid_to is None)."""
    valid_from = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    alias = SymbolAlias(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=valid_from,
        valid_to=None,
        **evidence,
    )
    assert alias.instrument_id == "inst-1"
    assert alias.symbol == "AAPL"
    assert alias.valid_from == valid_from
    assert alias.valid_to is None


def test_valid_alias_bounded_interval(evidence):
    """2. Valid alias with bounded half-open interval [valid_from, valid_to)."""
    valid_from = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    valid_to = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    alias = SymbolAlias(
        instrument_id="inst-1",
        symbol="FB",
        valid_from=valid_from,
        valid_to=valid_to,
        **evidence,
    )
    assert alias.instrument_id == "inst-1"
    assert alias.symbol == "FB"
    assert alias.valid_from == valid_from
    assert alias.valid_to == valid_to


def test_naive_valid_from_rejected(evidence):
    """3. Naïve valid_from is rejected."""
    naive_dt = datetime(2026, 1, 1, 0, 0)
    with pytest.raises(ValidationError, match="timezone"):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=naive_dt,
            **evidence,
        )


def test_aware_non_utc_valid_from_normalized_to_utc(evidence):
    """4. Aware non-UTC valid_from normalized to UTC."""
    offset_dt = datetime(2026, 1, 1, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
    alias = SymbolAlias(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=offset_dt,
        **evidence,
    )
    assert alias.valid_from == datetime(2026, 1, 1, 20, 0, tzinfo=UTC)
    assert alias.valid_from.tzinfo == UTC


def test_naive_valid_to_rejected(evidence):
    """5. Naïve valid_to is rejected."""
    valid_from = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    naive_valid_to = datetime(2026, 6, 1, 0, 0)
    with pytest.raises(ValidationError, match="timezone"):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=valid_from,
            valid_to=naive_valid_to,
            **evidence,
        )


def test_valid_to_less_than_or_equal_to_valid_from_rejected(evidence):
    """6. valid_to <= valid_from rejected (zero-length or reversed interval)."""
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    # valid_to == valid_from
    with pytest.raises(ValidationError, match="valid_to"):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            valid_to=t0,
            **evidence,
        )

    # valid_to < valid_from
    with pytest.raises(ValidationError, match="valid_to"):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=t0,
            valid_to=t0 - timedelta(hours=1),
            **evidence,
        )


def test_future_effective_alias_allowed_available_at_before_valid_from(evidence):
    """7. Future-effective alias allowed: available_at < valid_from."""
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    valid_from = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    data = evidence | {
        "event_time": t0,
        "source_timestamp": t0,
        "received_at": t0,
        "processed_at": t0,
        "available_at": t0,
    }

    alias = SymbolAlias(
        instrument_id="inst-1",
        symbol="META",
        valid_from=valid_from,
        **data,
    )
    assert alias.available_at < alias.valid_from


def test_stable_instrument_id_retained_independently_of_symbol(evidence):
    """8. Stable instrument_id retained independently across distinct symbols.

    Both are explicit, independent domain records sharing one stable canonical
    identity without automatic inference or resolver logic.
    """
    t1 = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)
    t2 = datetime(2022, 6, 9, 0, 0, tzinfo=UTC)

    old_alias = SymbolAlias(
        instrument_id="inst-meta",
        symbol="FB",
        valid_from=t1,
        valid_to=t2,
        **evidence,
    )

    new_alias = SymbolAlias(
        instrument_id="inst-meta",
        symbol="META",
        valid_from=t2,
        valid_to=None,
        **evidence,
    )

    assert old_alias.instrument_id == new_alias.instrument_id == "inst-meta"
    assert old_alias.symbol == "FB"
    assert new_alias.symbol == "META"
    assert old_alias.valid_to == new_alias.valid_from


def test_invalid_symbol_rejected(evidence):
    """9. Invalid symbol rejected using existing Symbol rules."""
    valid_from = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    # Empty symbol
    with pytest.raises(ValidationError):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="",
            valid_from=valid_from,
            **evidence,
        )

    # Lowercase symbol
    with pytest.raises(ValidationError):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="aapl",
            valid_from=valid_from,
            **evidence,
        )

    # Invalid special character
    with pytest.raises(ValidationError):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL@1",
            valid_from=valid_from,
            **evidence,
        )


def test_extra_unknown_fields_forbidden(evidence):
    """10. Extra/unknown fields remain forbidden according to Contract behavior."""
    valid_from = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        SymbolAlias(
            instrument_id="inst-1",
            symbol="AAPL",
            valid_from=valid_from,
            unknown_field="unsupported",
            **evidence,
        )
