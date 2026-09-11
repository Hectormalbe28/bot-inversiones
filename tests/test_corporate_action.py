from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.models import CorporateAction, InstrumentVersion, SymbolAlias


def test_valid_corporate_action(evidence):
    """CASE 1: Valid corporate action creation with required fields."""
    effective_at = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)
    ca = CorporateAction(
        action_id="act-101",
        instrument_id="inst-1",
        action_type="split",
        effective_at=effective_at,
        **evidence,
    )
    assert ca.action_id == "act-101"
    assert ca.instrument_id == "inst-1"
    assert ca.action_type == "split"
    assert ca.effective_at == effective_at


@pytest.mark.parametrize(
    "action_type",
    [
        "ticker_change",
        "split",
        "reverse_split",
        "dividend",
        "merger",
        "acquisition",
        "spin_off",
        "delisting",
    ],
)
def test_every_supported_action_type_accepted(evidence, action_type):
    """CASE 2: All 8 supported baseline action types accepted."""
    ca = CorporateAction(
        action_id=f"act-{action_type}",
        instrument_id="inst-1",
        action_type=action_type,
        effective_at=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        **evidence,
    )
    assert ca.action_type == action_type


def test_invalid_action_type_rejected(evidence):
    """CASE 3: Invalid action type rejected."""
    with pytest.raises(ValidationError):
        CorporateAction(
            action_id="act-invalid",
            instrument_id="inst-1",
            action_type="unknown_action",
            effective_at=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
            **evidence,
        )


def test_naive_effective_at_rejected(evidence):
    """CASE 4: Naïve effective_at rejected."""
    naive_dt = datetime(2026, 9, 20, 12, 0)
    with pytest.raises(ValidationError, match="timezone"):
        CorporateAction(
            action_id="act-1",
            instrument_id="inst-1",
            action_type="dividend",
            effective_at=naive_dt,
            **evidence,
        )


def test_aware_non_utc_effective_at_normalized(evidence):
    """CASE 5: Aware non-UTC effective_at normalized to UTC."""
    offset_dt = datetime(2026, 9, 15, 9, 0, tzinfo=timezone(timedelta(hours=-5)))
    ca = CorporateAction(
        action_id="act-1",
        instrument_id="inst-1",
        action_type="delisting",
        effective_at=offset_dt,
        **evidence,
    )
    assert ca.effective_at == datetime(2026, 9, 15, 14, 0, tzinfo=UTC)
    assert ca.effective_at.tzinfo == UTC


def test_future_effective_corporate_action_allowed(evidence):
    """CASE 6: Future-effective corporate action allowed (available_at < effective_at)."""
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    effective_at = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    data = evidence | {
        "event_time": t0,
        "source_timestamp": t0,
        "received_at": t0,
        "processed_at": t0,
        "available_at": t0,
    }
    ca = CorporateAction(
        action_id="act-future-split",
        instrument_id="inst-1",
        action_type="split",
        effective_at=effective_at,
        **data,
    )
    assert ca.available_at < ca.effective_at


def test_provenance_preserved(evidence):
    """CASE 7: Provenance preserved through inherited TemporalEvidence."""
    ca = CorporateAction(
        action_id="act-1",
        instrument_id="inst-1",
        action_type="merger",
        effective_at=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        **evidence,
    )
    assert ca.provider == evidence["provider"]
    assert ca.feed == evidence["feed"]
    assert ca.version == evidence["version"]
    assert ca.available_at == evidence["available_at"]
    assert ca.source_timestamp == evidence["source_timestamp"]
    assert ca.received_at == evidence["received_at"]
    assert ca.processed_at == evidence["processed_at"]
    assert ca.event_time == evidence["event_time"]


def test_stable_identity_no_inference(evidence):
    """CASE 8: Stable identity referenced without inference or mutation."""
    ca = CorporateAction(
        action_id="act-ticker-chg",
        instrument_id="inst-meta",
        action_type="ticker_change",
        effective_at=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        **evidence,
    )
    # The action only references the stable instrument_id; no mutation or inference
    assert ca.instrument_id == "inst-meta"
    assert ca.action_type == "ticker_change"


def test_extra_fields_rejected(evidence):
    """CASE 9: Extra/unknown fields rejected according to Contract behavior."""
    with pytest.raises(ValidationError):
        CorporateAction(
            action_id="act-1",
            instrument_id="inst-1",
            action_type="spin_off",
            effective_at=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
            ratio="2:1",  # Extra field
            **evidence,
        )


def test_existing_contracts_coexist_without_regression(evidence):
    """CASE 10: Coexistence of CorporateAction, InstrumentVersion, and SymbolAlias."""
    t0 = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)

    iv = InstrumentVersion(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=t0,
        **evidence,
    )
    alias = SymbolAlias(
        instrument_id="inst-1",
        symbol="AAPL",
        valid_from=t0,
        **evidence,
    )
    ca = CorporateAction(
        action_id="act-split",
        instrument_id="inst-1",
        action_type="split",
        effective_at=t1,
        **evidence,
    )

    assert iv.instrument_id == alias.instrument_id == ca.instrument_id == "inst-1"
    assert iv.symbol == alias.symbol == "AAPL"
    assert ca.action_type == "split"
