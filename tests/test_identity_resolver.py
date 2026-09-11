"""Acceptance tests for the provider-neutral temporal identity resolver.

Validates pure temporal resolution using explicit SymbolAlias evidence,
strict point-in-time knowledge cutoff (available_at <= query_time),
semi-open interval validity [valid_from, valid_to), and ambiguity detection.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.application.identity import (
    IdentityReason,
    IdentityStatus,
    resolve_symbol_identity,
)
from app.domain.models import SymbolAlias

T0 = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
T2 = datetime(2025, 12, 1, 0, 0, tzinfo=UTC)


def _make_alias(
    symbol: str = "AAPL",
    instrument_id: str = "inst-apple",
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    available_at: datetime = T0,
    valid_from: datetime = T0,
    valid_to: datetime | None = None,
    event_time: datetime = T0,
    version: int = 1,
) -> SymbolAlias:
    return SymbolAlias(
        symbol=symbol,
        instrument_id=instrument_id,
        provider=provider,
        feed=feed,
        source_timestamp=available_at,
        received_at=available_at,
        processed_at=available_at,
        available_at=available_at,
        valid_from=valid_from,
        valid_to=valid_to,
        event_time=event_time,
        version=version,
    )


def test_no_aliases_returns_unresolved():
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=(),
    )
    assert res.status == IdentityStatus.UNRESOLVED
    assert res.instrument_id is None
    assert res.reason == IdentityReason.NO_ELIGIBLE_ALIAS


def test_one_explicit_alias_returns_resolved():
    alias = _make_alias()
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_returned_id_equals_explicit_alias_instrument_id():
    alias = _make_alias(instrument_id="inst-12345")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.instrument_id == "inst-12345"
    assert res.reason == IdentityReason.EXPLICIT_ALIAS


def test_provider_mismatch_returns_unresolved():
    alias = _make_alias(provider="nyse")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED
    assert res.instrument_id is None


def test_feed_mismatch_returns_unresolved():
    alias = _make_alias(feed="different_feed")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED
    assert res.instrument_id is None


def test_different_symbol_returns_unresolved():
    alias = _make_alias(symbol="MSFT")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED
    assert res.instrument_id is None


def test_available_at_after_query_time_is_invisible():
    # Alias is made available at T1, query time is T0 -> invisible
    alias = _make_alias(available_at=T1, valid_from=T0)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_available_at_equal_query_time_is_eligible():
    alias = _make_alias(available_at=T0, valid_from=T0)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_valid_from_after_effective_time_is_invisible():
    alias = _make_alias(available_at=T0, valid_from=T1)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_valid_from_equal_effective_time_is_eligible():
    alias = _make_alias(available_at=T0, valid_from=T0)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_effective_time_before_valid_to_is_eligible():
    alias = _make_alias(valid_from=T0, valid_to=T1)
    # Effective at T0 + 1 day < T1
    effective = T0 + timedelta(days=1)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=effective,
        query_time=effective,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_effective_time_equal_valid_to_is_not_eligible():
    # [valid_from, valid_to) is half-open: valid_to is exclusive
    alias = _make_alias(valid_from=T0, valid_to=T1)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T1,
        query_time=T1,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_open_ended_valid_to_none_is_eligible():
    alias = _make_alias(valid_from=T0, valid_to=None)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T2,
        query_time=T2,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_multiple_aliases_same_instrument_id_is_resolved():
    alias1 = _make_alias(instrument_id="inst-1", version=1)
    alias2 = _make_alias(instrument_id="inst-1", version=2)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias1, alias2],
    )
    assert res.status == IdentityStatus.RESOLVED
    assert res.instrument_id == "inst-1"


def test_multiple_eligible_distinct_instrument_ids_is_ambiguous():
    alias1 = _make_alias(instrument_id="inst-1")
    alias2 = _make_alias(instrument_id="inst-2")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias1, alias2],
    )
    assert res.status == IdentityStatus.AMBIGUOUS
    assert res.reason == IdentityReason.CONFLICTING_IDENTITIES


def test_ambiguous_result_has_none_instrument_id():
    alias1 = _make_alias(instrument_id="inst-1")
    alias2 = _make_alias(instrument_id="inst-2")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias1, alias2],
    )
    assert res.instrument_id is None


def test_future_alias_known_early_not_effective_yet_unresolved():
    # Known at T0, but valid starting at T1. At effective T0, unresolved.
    alias = _make_alias(available_at=T0, valid_from=T1, valid_to=None)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_delayed_alias_availability_prevents_historical_leakage():
    # Valid starting at T0, but recorded/available only at T2.
    # At query_time T1 < T2, cannot know about it yet.
    alias = _make_alias(valid_from=T0, available_at=T2)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T1,
        query_time=T1,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED

    # At query_time T2, now visible and resolved.
    res2 = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T1,
        query_time=T2,
        aliases=[alias],
    )
    assert res2.status == IdentityStatus.RESOLVED


def test_event_time_does_not_control_resolution():
    # event_time is ancient or in the future, only available_at and valid_from/to matter
    alias = _make_alias(
        available_at=T0,
        valid_from=T0,
        event_time=datetime(2099, 1, 1, tzinfo=UTC),
    )
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_naive_query_time_rejected():
    naive_qt = datetime(2025, 1, 1, 0, 0)
    with pytest.raises(ValueError):
        resolve_symbol_identity(
            symbol="AAPL",
            provider="nasdaq",
            feed="symbol_directory",
            effective_time=T0,
            query_time=naive_qt,
            aliases=[],
        )


def test_naive_effective_time_rejected():
    naive_eff = datetime(2025, 1, 1, 0, 0)
    with pytest.raises(ValueError):
        resolve_symbol_identity(
            symbol="AAPL",
            provider="nasdaq",
            feed="symbol_directory",
            effective_time=naive_eff,
            query_time=T0,
            aliases=[],
        )


def test_aware_non_utc_query_time_normalizes_correctly():
    # 05:00 UTC+5 is 00:00 UTC (T0)
    tz_plus5 = timezone(timedelta(hours=5))
    qt_aware = datetime(2025, 1, 1, 5, 0, tzinfo=tz_plus5)
    alias = _make_alias(available_at=T0)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=qt_aware,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_aware_non_utc_effective_time_normalizes_correctly():
    tz_minus5 = timezone(timedelta(hours=-5))
    # 2025-01-01 00:00 UTC is 2024-12-31 19:00 UTC-5
    eff_aware = datetime(2024, 12, 31, 19, 0, tzinfo=tz_minus5)
    alias = _make_alias(valid_from=T0)
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=eff_aware,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.RESOLVED


def test_similar_symbol_does_not_match():
    alias = _make_alias(symbol="ABCD")
    res = resolve_symbol_identity(
        symbol="ABC",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_security_company_name_is_not_part_of_resolution():
    alias = _make_alias(symbol="OTHER")
    res = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res.status == IdentityStatus.UNRESOLVED


def test_function_does_not_mutate_alias_inputs():
    alias = _make_alias()
    orig_sym = alias.symbol
    orig_id = alias.instrument_id
    orig_avail = alias.available_at
    alias_list = [alias]
    resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=alias_list,
    )
    assert alias.symbol == orig_sym
    assert alias.instrument_id == orig_id
    assert alias.available_at == orig_avail
    assert len(alias_list) == 1


def test_repeated_call_produces_equal_result():
    alias = _make_alias()
    res1 = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    res2 = resolve_symbol_identity(
        symbol="AAPL",
        provider="nasdaq",
        feed="symbol_directory",
        effective_time=T0,
        query_time=T0,
        aliases=[alias],
    )
    assert res1 == res2
