import pytest

from app.application.operational_universe import (
    CONSERVATIVE_NASDAQ_OPERATIONAL_POLICY,
    OperationalUniverseCandidate,
    OperationalUniversePolicy,
    derive_operational_universe,
)


def _policy() -> OperationalUniversePolicy:
    return CONSERVATIVE_NASDAQ_OPERATIONAL_POLICY


def test_explicit_policy_derives_view_and_retains_each_exclusion_reason():
    result = derive_operational_universe(
        (
            OperationalUniverseCandidate("inst-test", True, "N"),
            OperationalUniverseCandidate("inst-status", False, "D"),
            OperationalUniverseCandidate("inst-good", False, "N"),
        ),
        _policy(),
    )

    assert result.included_instrument_ids == ("inst-good",)
    assert [(item.instrument_id, item.reason_code) for item in result.decisions] == [
        ("inst-good", None),
        ("inst-status", "FINANCIAL_STATUS"),
        ("inst-test", "TEST_ISSUE"),
    ]


def test_contract_rejects_implicit_empty_policy_and_duplicate_identity():
    with pytest.raises(ValueError, match="must not be empty"):
        OperationalUniversePolicy(
            policy_id="test", exclude_test_issues=True, allowed_financial_statuses=frozenset()
        )

    with pytest.raises(ValueError, match="unique"):
        derive_operational_universe(
            (
                OperationalUniverseCandidate("inst-a", False, "N"),
                OperationalUniverseCandidate("inst-a", False, "N"),
            ),
            _policy(),
        )
