from datetime import UTC, date, datetime

from app.application.eod import (
    DailyBarEligibility,
    build_massive_daily_identity_gate,
)
from app.domain.models import SymbolAlias
from app.infrastructure.providers.massive import (
    normalize_massive_grouped_daily,
    parse_massive_grouped_daily,
)

SESSION = date(2026, 10, 20)
SOURCE_TIME = datetime(2026, 10, 20, 13, 30, tzinfo=UTC)
RECEIVED = datetime(2026, 10, 21, 14, 0, tzinfo=UTC)
PROCESSED = datetime(2026, 10, 21, 14, 0, 1, tzinfo=UTC)
AVAILABLE = datetime(2026, 10, 21, 14, 0, 2, tzinfo=UTC)


def _normalized(symbol="AAPL"):
    raw = (
        '{"adjusted":false,"queryCount":1,"request_id":"req-1",'
        '"results":[{"T":"' + symbol + '","o":100,"h":110,"l":95,"c":105,"v":1000,'
        '"vw":103.5,"n":100,"t":1792503000000}],'
        '"resultsCount":1,"status":"OK"}'
    ).encode()
    return normalize_massive_grouped_daily(parse_massive_grouped_daily(raw, session_date=SESSION))


def _alias(
    *,
    symbol="AAPL",
    instrument_id="inst-aapl",
    provider="massive",
    feed="grouped_daily",
    available_at=datetime(2026, 1, 1, tzinfo=UTC),
    valid_from=datetime(2020, 1, 1, tzinfo=UTC),
    valid_to=None,
    version=1,
):
    return SymbolAlias(
        instrument_id=instrument_id,
        symbol=symbol,
        valid_from=valid_from,
        valid_to=valid_to,
        event_time=valid_from,
        source_timestamp=available_at,
        received_at=available_at,
        processed_at=available_at,
        available_at=available_at,
        provider=provider,
        feed=feed,
        version=version,
    )


def _gate(normalized, aliases, *, query_time=AVAILABLE):
    return build_massive_daily_identity_gate(
        normalized,
        aliases=aliases,
        query_time=query_time,
        received_at=RECEIVED,
        processed_at=PROCESSED,
        available_at=AVAILABLE,
    )


def test_explicit_massive_alias_materializes_canonical_daily_bar():
    gate = _gate(_normalized(), [_alias()])

    assert gate.eligible_count == 1
    item = gate.records[0]
    assert item.eligibility == DailyBarEligibility.ELIGIBLE
    assert item.instrument_id == "inst-aapl"
    assert item.canonical_bar is not None
    assert item.canonical_bar.instrument_id == "inst-aapl"
    assert item.canonical_bar.symbol == "AAPL"
    assert item.canonical_bar.adjustment_policy == "raw"
    assert item.canonical_bar.provider == "massive"
    assert item.canonical_bar.feed == "grouped_daily"


def test_unknown_symbol_stays_pending_without_synthetic_identity():
    gate = _gate(_normalized("ZZZZ"), [])

    item = gate.records[0]
    assert item.eligibility == DailyBarEligibility.PENDING_IDENTITY
    assert item.instrument_id is None
    assert item.canonical_bar is None


def test_conflicting_aliases_are_quarantined_not_selected():
    aliases = [
        _alias(instrument_id="inst-1"),
        _alias(instrument_id="inst-2", version=2),
    ]
    gate = _gate(_normalized(), aliases)

    item = gate.records[0]
    assert item.eligibility == DailyBarEligibility.IDENTITY_CONFLICT
    assert item.instrument_id is None
    assert item.canonical_bar is None
    assert gate.conflict_count == 1


def test_nasdaq_alias_does_not_authorize_massive_identity():
    gate = _gate(
        _normalized(),
        [_alias(provider="nasdaq", feed="symbol_directory")],
    )

    assert gate.records[0].eligibility == DailyBarEligibility.PENDING_IDENTITY


def test_late_known_alias_is_invisible_before_its_available_at():
    alias = _alias(available_at=datetime(2026, 10, 22, tzinfo=UTC))
    gate = _gate(_normalized(), [alias], query_time=AVAILABLE)

    assert gate.records[0].eligibility == DailyBarEligibility.PENDING_IDENTITY


def test_ticker_reuse_resolves_by_record_effective_time():
    old_alias = _alias(
        instrument_id="inst-old",
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 10, 21, tzinfo=UTC),
    )
    new_alias = _alias(
        instrument_id="inst-new",
        valid_from=datetime(2026, 10, 21, tzinfo=UTC),
        version=2,
    )
    gate = _gate(_normalized(), [old_alias, new_alias])

    assert gate.records[0].instrument_id == "inst-old"


def test_canonical_bar_preserves_real_ingestion_provenance():
    gate = _gate(_normalized(), [_alias()])
    bar = gate.records[0].canonical_bar

    assert bar is not None
    assert bar.received_at == RECEIVED
    assert bar.processed_at == PROCESSED
    assert bar.available_at == AVAILABLE
    assert bar.source_timestamp == gate.records[0].record.source_timestamp
    assert bar.event_time == gate.records[0].record.source_timestamp


def test_gate_summary_counts_are_complete_and_deterministic():
    normalized = _normalized()
    gate = _gate(normalized, [])

    assert gate.total_count == 1
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 1
    assert gate.conflict_count == 0
    assert gate.invalid_data_count == 0
    assert gate.total_count == (
        gate.eligible_count
        + gate.pending_identity_count
        + gate.conflict_count
        + gate.invalid_data_count
    )


def test_gate_does_not_mutate_normalized_provider_evidence():
    normalized = _normalized()
    before = normalized.records
    _gate(normalized, [_alias()])

    assert normalized.records == before
