"""Provider-neutral temporal identity resolver.

Resolves symbol identity to a canonical stable instrument_id using explicit
SymbolAlias evidence across two independent temporal axes:
- query_time (knowledge cutoff): available_at <= query_time
- effective_time (validity interval): valid_from <= effective_time < valid_to

Does not infer identity from symbols, names, similarity, or current state.
Does not allocate new identifiers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.clock import require_utc
from app.domain.models import SymbolAlias

if TYPE_CHECKING:
    from app.infrastructure.providers.nasdaq import (
        NasdaqIdentityResolutionFile,
        NasdaqNormalizedRecord,
    )


class IdentityStatus(StrEnum):
    """Status of an identity resolution attempt."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class IdentityReason(StrEnum):
    """Deterministic reason for the identity resolution status."""

    EXPLICIT_ALIAS = "EXPLICIT_ALIAS"
    NO_ELIGIBLE_ALIAS = "NO_ELIGIBLE_ALIAS"
    CONFLICTING_IDENTITIES = "CONFLICTING_IDENTITIES"


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    """Result of a symbol identity resolution query.

    Immutable structure capturing the resolution status, matched canonical identifier
    (or None if unresolved/ambiguous), and audit reason.
    """

    status: IdentityStatus
    symbol: str
    provider: str
    feed: str
    instrument_id: str | None
    reason: IdentityReason


def resolve_symbol_identity(
    *,
    symbol: str,
    provider: str,
    feed: str,
    effective_time: datetime,
    query_time: datetime,
    aliases: Sequence[SymbolAlias],
) -> IdentityResolution:
    """Resolve a symbol to a stable canonical instrument_id using explicit SymbolAlias evidence.

    Args:
        symbol: The exact ticker / symbol to resolve.
        provider: Exact provider identifier (e.g., 'nasdaq').
        feed: Exact provider feed identifier (e.g., 'symbol_directory').
        effective_time: The point in time for which identity is being queried.
        query_time: Knowledge cutoff time; evidence available after this is invisible.
        aliases: Sequence of explicit SymbolAlias domain records to query against.

    Returns:
        IdentityResolution with status RESOLVED, UNRESOLVED, or AMBIGUOUS.

    Raises:
        ValueError: If either effective_time or query_time lacks timezone info.
    """
    eff_utc = require_utc(effective_time)
    qry_utc = require_utc(query_time)

    eligible_aliases: list[SymbolAlias] = []
    for alias in aliases:
        if alias.provider != provider:
            continue
        if alias.feed != feed:
            continue
        if alias.symbol != symbol:
            continue
        # Knowledge eligibility
        if alias.available_at > qry_utc:
            continue
        # Effective validity: [valid_from, valid_to)
        if alias.valid_from > eff_utc:
            continue
        if alias.valid_to is not None and eff_utc >= alias.valid_to:
            continue
        eligible_aliases.append(alias)

    distinct_ids = sorted({alias.instrument_id for alias in eligible_aliases})

    if not distinct_ids:
        return IdentityResolution(
            status=IdentityStatus.UNRESOLVED,
            symbol=symbol,
            provider=provider,
            feed=feed,
            instrument_id=None,
            reason=IdentityReason.NO_ELIGIBLE_ALIAS,
        )

    if len(distinct_ids) == 1:
        return IdentityResolution(
            status=IdentityStatus.RESOLVED,
            symbol=symbol,
            provider=provider,
            feed=feed,
            instrument_id=distinct_ids[0],
            reason=IdentityReason.EXPLICIT_ALIAS,
        )

    return IdentityResolution(
        status=IdentityStatus.AMBIGUOUS,
        symbol=symbol,
        provider=provider,
        feed=feed,
        instrument_id=None,
        reason=IdentityReason.CONFLICTING_IDENTITIES,
    )


# ---------------------------------------------------------------------------
# S2.11A — Identity Persistence Gate
# ---------------------------------------------------------------------------


class PersistenceEligibility(StrEnum):
    """Gate classification for a resolved identity record.

    ELIGIBLE:          Resolution was RESOLVED — instrument_id is known and populated.
    PENDING_IDENTITY:  Resolution was UNRESOLVED — no eligible alias found; instrument_id=None.
    IDENTITY_CONFLICT: Resolution was AMBIGUOUS — conflicting aliases; instrument_id=None.
    """

    ELIGIBLE = "ELIGIBLE"
    PENDING_IDENTITY = "PENDING_IDENTITY"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"


@dataclass(frozen=True, slots=True)
class NasdaqIdentityGateRecord:
    """A single record after passing through the identity persistence gate.

    Mirrors NasdaqIdentityRecord, adding the gate classification and the
    resolved instrument_id (None unless ELIGIBLE).
    """

    record: NasdaqNormalizedRecord
    identity: IdentityResolution
    eligibility: PersistenceEligibility
    instrument_id: str | None


@dataclass(frozen=True, slots=True)
class NasdaqIdentityPersistenceGate:
    """Result of applying the persistence gate to a NasdaqIdentityResolutionFile.

    Immutable; carries provenance timestamps and summary counts.
    Invariant: total_count == eligible_count + pending_identity_count + conflict_count.
    """

    records: tuple[NasdaqIdentityGateRecord, ...]
    source_timestamp: datetime
    received_at: datetime
    processed_at: datetime
    available_at: datetime
    provider: str
    feed: str
    total_count: int
    eligible_count: int
    pending_identity_count: int
    conflict_count: int


def build_identity_persistence_gate(
    resolved: NasdaqIdentityResolutionFile,
    *,
    source_timestamp: datetime,
    received_at: datetime,
    processed_at: datetime,
    available_at: datetime,
    provider: str,
    feed: str,
) -> NasdaqIdentityPersistenceGate:
    """Map a NasdaqIdentityResolutionFile through the persistence eligibility gate.

    Pure function — no DB, FS, or network access.

    Mapping:
        RESOLVED   -> ELIGIBLE       (instrument_id carried through)
        UNRESOLVED -> PENDING_IDENTITY (instrument_id=None)
        AMBIGUOUS  -> IDENTITY_CONFLICT (instrument_id=None)

    Args:
        resolved: A fully resolved NasdaqIdentityResolutionFile from S2.10.
        source_timestamp: Timestamp of the original provider source file.
        received_at: When the raw bytes were received.
        processed_at: When processing completed.
        available_at: Knowledge cutoff at which this gate result is visible.
        provider: Exact provider identifier (e.g., 'nasdaq').
        feed: Exact provider feed identifier (e.g., 'symbol_directory').

    Returns:
        NasdaqIdentityPersistenceGate with classified records and summary counts.
    """
    gate_records: list[NasdaqIdentityGateRecord] = []
    eligible = 0
    pending = 0
    conflict = 0

    _map = {
        IdentityStatus.RESOLVED: PersistenceEligibility.ELIGIBLE,
        IdentityStatus.UNRESOLVED: PersistenceEligibility.PENDING_IDENTITY,
        IdentityStatus.AMBIGUOUS: PersistenceEligibility.IDENTITY_CONFLICT,
    }

    for rec in resolved.records:
        eligibility = _map[rec.identity.status]
        inst_id = (
            rec.identity.instrument_id if eligibility == PersistenceEligibility.ELIGIBLE else None
        )
        gate_records.append(
            NasdaqIdentityGateRecord(
                record=rec.record,
                identity=rec.identity,
                eligibility=eligibility,
                instrument_id=inst_id,
            )
        )
        if eligibility == PersistenceEligibility.ELIGIBLE:
            eligible += 1
        elif eligibility == PersistenceEligibility.PENDING_IDENTITY:
            pending += 1
        else:
            conflict += 1

    return NasdaqIdentityPersistenceGate(
        records=tuple(gate_records),
        source_timestamp=source_timestamp,
        received_at=received_at,
        processed_at=processed_at,
        available_at=available_at,
        provider=provider,
        feed=feed,
        total_count=eligible + pending + conflict,
        eligible_count=eligible,
        pending_identity_count=pending,
        conflict_count=conflict,
    )
