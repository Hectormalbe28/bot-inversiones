"""S2.11A - Identity Persistence Gate: acceptance tests.

Tests for build_identity_persistence_gate(), which maps a NasdaqIdentityResolutionFile
to a NasdaqIdentityPersistenceGate.

Mapping:
    RESOLVED   -> PersistenceEligibility.ELIGIBLE       (instrument_id populated)
    UNRESOLVED -> PersistenceEligibility.PENDING_IDENTITY (instrument_id=None)
    AMBIGUOUS  -> PersistenceEligibility.IDENTITY_CONFLICT (instrument_id=None)

Invariant:
    total_count == eligible_count + pending_identity_count + conflict_count
"""

from datetime import UTC, datetime

import pytest

from app.application.identity import (
    IdentityReason,
    IdentityResolution,
    IdentityStatus,
    NasdaqIdentityGateRecord,
    NasdaqIdentityPersistenceGate,
    PersistenceEligibility,
    build_identity_persistence_gate,
)
from app.infrastructure.providers.nasdaq import (
    NasdaqIdentityRecord,
    NasdaqIdentityResolutionFile,
    NasdaqNormalizedRecord,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = UTC
_T0 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=_UTC)
_T_SRC = datetime(2024, 1, 14, 22, 0, 0, tzinfo=_UTC)
_PROVIDER = "nasdaq"
_FEED = "symbol_directory"
_FCT = "01152024120000"


def _norm(symbol: str, name: str = "Test Corp") -> NasdaqNormalizedRecord:
    return NasdaqNormalizedRecord(
        symbol=symbol,
        security_name=name,
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )


def _resolved_record(symbol: str, instrument_id: str) -> NasdaqIdentityRecord:
    return NasdaqIdentityRecord(
        record=_norm(symbol),
        identity=IdentityResolution(
            status=IdentityStatus.RESOLVED,
            symbol=symbol,
            provider=_PROVIDER,
            feed=_FEED,
            instrument_id=instrument_id,
            reason=IdentityReason.EXPLICIT_ALIAS,
        ),
    )


def _unresolved_record(symbol: str) -> NasdaqIdentityRecord:
    return NasdaqIdentityRecord(
        record=_norm(symbol),
        identity=IdentityResolution(
            status=IdentityStatus.UNRESOLVED,
            symbol=symbol,
            provider=_PROVIDER,
            feed=_FEED,
            instrument_id=None,
            reason=IdentityReason.NO_ELIGIBLE_ALIAS,
        ),
    )


def _ambiguous_record(symbol: str) -> NasdaqIdentityRecord:
    return NasdaqIdentityRecord(
        record=_norm(symbol),
        identity=IdentityResolution(
            status=IdentityStatus.AMBIGUOUS,
            symbol=symbol,
            provider=_PROVIDER,
            feed=_FEED,
            instrument_id=None,
            reason=IdentityReason.CONFLICTING_IDENTITIES,
        ),
    )


def _make_file(records: list) -> NasdaqIdentityResolutionFile:
    return NasdaqIdentityResolutionFile(
        records=tuple(records),
        file_creation_time_raw=_FCT,
    )


# ---------------------------------------------------------------------------
# PersistenceEligibility enum
# ---------------------------------------------------------------------------


def test_eligibility_values_are_strings():
    assert PersistenceEligibility.ELIGIBLE == "ELIGIBLE"
    assert PersistenceEligibility.PENDING_IDENTITY == "PENDING_IDENTITY"
    assert PersistenceEligibility.IDENTITY_CONFLICT == "IDENTITY_CONFLICT"


def test_eligibility_str():
    assert str(PersistenceEligibility.ELIGIBLE) == "ELIGIBLE"
    assert str(PersistenceEligibility.PENDING_IDENTITY) == "PENDING_IDENTITY"
    assert str(PersistenceEligibility.IDENTITY_CONFLICT) == "IDENTITY_CONFLICT"


def test_eligibility_has_exactly_three_members():
    assert len(PersistenceEligibility) == 3


# ---------------------------------------------------------------------------
# NasdaqIdentityGateRecord structure
# ---------------------------------------------------------------------------


def test_gate_record_eligible_has_instrument_id():
    rec = _resolved_record("AAPL", "instr-001")
    gate_rec = NasdaqIdentityGateRecord(
        record=rec.record,
        identity=rec.identity,
        eligibility=PersistenceEligibility.ELIGIBLE,
        instrument_id="instr-001",
    )
    assert gate_rec.instrument_id == "instr-001"
    assert gate_rec.eligibility == PersistenceEligibility.ELIGIBLE


def test_gate_record_pending_has_no_instrument_id():
    rec = _unresolved_record("AAPL")
    gate_rec = NasdaqIdentityGateRecord(
        record=rec.record,
        identity=rec.identity,
        eligibility=PersistenceEligibility.PENDING_IDENTITY,
        instrument_id=None,
    )
    assert gate_rec.instrument_id is None


def test_gate_record_conflict_has_no_instrument_id():
    rec = _ambiguous_record("AAPL")
    gate_rec = NasdaqIdentityGateRecord(
        record=rec.record,
        identity=rec.identity,
        eligibility=PersistenceEligibility.IDENTITY_CONFLICT,
        instrument_id=None,
    )
    assert gate_rec.instrument_id is None


def test_gate_record_is_immutable():
    rec = _resolved_record("AAPL", "instr-001")
    gate_rec = NasdaqIdentityGateRecord(
        record=rec.record,
        identity=rec.identity,
        eligibility=PersistenceEligibility.ELIGIBLE,
        instrument_id="instr-001",
    )
    with pytest.raises((AttributeError, TypeError)):
        gate_rec.instrument_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NasdaqIdentityPersistenceGate structure
# ---------------------------------------------------------------------------


def test_gate_is_immutable():
    f = _make_file([])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    with pytest.raises((AttributeError, TypeError)):
        gate.records = ()  # type: ignore[misc]


def test_gate_preserves_source_timestamps():
    f = _make_file([_resolved_record("AAPL", "instr-001")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.source_timestamp == _T_SRC
    assert gate.received_at == _T0
    assert gate.processed_at == _T0
    assert gate.available_at == _T0


def test_gate_preserves_provider_and_feed():
    f = _make_file([_resolved_record("AAPL", "instr-001")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.provider == _PROVIDER
    assert gate.feed == _FEED


# ---------------------------------------------------------------------------
# build_identity_persistence_gate - empty file
# ---------------------------------------------------------------------------


def test_empty_file_produces_empty_gate():
    f = _make_file([])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert isinstance(gate, NasdaqIdentityPersistenceGate)
    assert len(gate.records) == 0


def test_empty_file_all_counts_zero():
    f = _make_file([])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.total_count == 0
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 0
    assert gate.conflict_count == 0


def test_empty_file_invariant():
    f = _make_file([])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.total_count == (
        gate.eligible_count + gate.pending_identity_count + gate.conflict_count
    )


# ---------------------------------------------------------------------------
# Single-record mappings
# ---------------------------------------------------------------------------


def test_resolved_maps_to_eligible():
    f = _make_file([_resolved_record("AAPL", "instr-001")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 1
    assert gate.pending_identity_count == 0
    assert gate.conflict_count == 0
    assert gate.total_count == 1


def test_resolved_gate_record_carries_instrument_id():
    f = _make_file([_resolved_record("AAPL", "instr-001")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    rec = gate.records[0]
    assert rec.eligibility == PersistenceEligibility.ELIGIBLE
    assert rec.instrument_id == "instr-001"


def test_unresolved_maps_to_pending():
    f = _make_file([_unresolved_record("GOOG")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 1
    assert gate.conflict_count == 0
    assert gate.total_count == 1


def test_unresolved_gate_record_has_no_instrument_id():
    f = _make_file([_unresolved_record("GOOG")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    rec = gate.records[0]
    assert rec.eligibility == PersistenceEligibility.PENDING_IDENTITY
    assert rec.instrument_id is None


def test_ambiguous_maps_to_conflict():
    f = _make_file([_ambiguous_record("MSFT")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 0
    assert gate.conflict_count == 1
    assert gate.total_count == 1


def test_ambiguous_gate_record_has_no_instrument_id():
    f = _make_file([_ambiguous_record("MSFT")])
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    rec = gate.records[0]
    assert rec.eligibility == PersistenceEligibility.IDENTITY_CONFLICT
    assert rec.instrument_id is None


# ---------------------------------------------------------------------------
# Mixed file
# ---------------------------------------------------------------------------


def test_mixed_file_counts():
    records = [
        _resolved_record("AAPL", "instr-001"),
        _resolved_record("AMZN", "instr-002"),
        _unresolved_record("GOOG"),
        _ambiguous_record("MSFT"),
    ]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.total_count == 4
    assert gate.eligible_count == 2
    assert gate.pending_identity_count == 1
    assert gate.conflict_count == 1


def test_mixed_file_invariant():
    records = [
        _resolved_record("AAPL", "instr-001"),
        _unresolved_record("GOOG"),
        _ambiguous_record("MSFT"),
    ]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.total_count == (
        gate.eligible_count + gate.pending_identity_count + gate.conflict_count
    )


def test_order_preserved():
    records = [
        _resolved_record("AAPL", "instr-001"),
        _unresolved_record("GOOG"),
        _ambiguous_record("MSFT"),
    ]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.records[0].identity.symbol == "AAPL"
    assert gate.records[1].identity.symbol == "GOOG"
    assert gate.records[2].identity.symbol == "MSFT"


def test_all_resolved():
    records = [
        _resolved_record("AAPL", "instr-001"),
        _resolved_record("AMZN", "instr-002"),
        _resolved_record("TSLA", "instr-003"),
    ]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 3
    assert gate.pending_identity_count == 0
    assert gate.conflict_count == 0
    assert gate.total_count == 3


def test_all_unresolved():
    records = [_unresolved_record(s) for s in ["A", "B", "C"]]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 3
    assert gate.conflict_count == 0


def test_all_ambiguous():
    records = [_ambiguous_record(s) for s in ["X", "Y", "Z"]]
    f = _make_file(records)
    gate = build_identity_persistence_gate(
        f,
        source_timestamp=_T_SRC,
        received_at=_T0,
        processed_at=_T0,
        available_at=_T0,
        provider=_PROVIDER,
        feed=_FEED,
    )
    assert gate.eligible_count == 0
    assert gate.pending_identity_count == 0
    assert gate.conflict_count == 3
