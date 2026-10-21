"""Explicit, non-persistent filtering for a derived operational universe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationalUniverseCandidate:
    """A canonical member paired with provider quality evidence supplied by a caller."""

    instrument_id: str
    test_issue: bool
    financial_status: str


@dataclass(frozen=True, slots=True)
class OperationalUniversePolicy:
    """Caller-selected rules; this contract intentionally has no implicit default."""

    exclude_test_issues: bool
    allowed_financial_statuses: frozenset[str]
    policy_id: str
    version: int = 1

    def __post_init__(self) -> None:
        if not self.allowed_financial_statuses:
            raise ValueError("allowed_financial_statuses must not be empty")
        if not self.policy_id or self.version < 1:
            raise ValueError("policy_id and positive version are mandatory")


CONSERVATIVE_NASDAQ_OPERATIONAL_POLICY = OperationalUniversePolicy(
    policy_id="nasdaq-operational-conservative",
    version=1,
    exclude_test_issues=True,
    allowed_financial_statuses=frozenset({"N"}),
)


@dataclass(frozen=True, slots=True)
class OperationalUniverseDecision:
    instrument_id: str
    included: bool
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class OperationalUniverseResult:
    included_instrument_ids: tuple[str, ...]
    decisions: tuple[OperationalUniverseDecision, ...]


def derive_operational_universe(
    candidates: tuple[OperationalUniverseCandidate, ...], policy: OperationalUniversePolicy
) -> OperationalUniverseResult:
    """Derive a deterministic view without mutating historical provider membership."""
    seen: set[str] = set()
    decisions: list[OperationalUniverseDecision] = []
    for candidate in sorted(candidates, key=lambda item: item.instrument_id):
        if candidate.instrument_id in seen:
            raise ValueError("operational candidates must have unique instrument_id values")
        seen.add(candidate.instrument_id)
        reason = None
        if policy.exclude_test_issues and candidate.test_issue:
            reason = "TEST_ISSUE"
        elif candidate.financial_status not in policy.allowed_financial_statuses:
            reason = "FINANCIAL_STATUS"
        decisions.append(
            OperationalUniverseDecision(candidate.instrument_id, reason is None, reason)
        )
    return OperationalUniverseResult(
        tuple(item.instrument_id for item in decisions if item.included), tuple(decisions)
    )
