"""Sprint 3 EOD identity gate.

Maps typed Massive grouped-daily evidence to stable canonical identity using the
provider-neutral PIT resolver from Sprint 2. No identity is synthesized here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from pydantic import ValidationError

from app.application.identity import IdentityResolution, IdentityStatus, resolve_symbol_identity
from app.domain.models import CanonicalDailyBar, SymbolAlias
from app.infrastructure.providers.massive import (
    MassiveDailyRawRecord,
    MassiveNormalizedDailyFile,
)

MASSIVE_PROVIDER = "massive"
MASSIVE_GROUPED_DAILY_FEED = "grouped_daily"


class DailyBarEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    PENDING_IDENTITY = "PENDING_IDENTITY"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    INVALID_DATA = "INVALID_DATA"


@dataclass(frozen=True, slots=True)
class MassiveDailyIdentityGateRecord:
    record: MassiveDailyRawRecord
    identity: IdentityResolution
    eligibility: DailyBarEligibility
    instrument_id: str | None
    canonical_bar: CanonicalDailyBar | None


@dataclass(frozen=True, slots=True)
class MassiveDailyIdentityGate:
    session_date: date
    request_id: str | None
    records: tuple[MassiveDailyIdentityGateRecord, ...]
    total_count: int
    eligible_count: int
    pending_identity_count: int
    conflict_count: int
    invalid_data_count: int


def build_massive_daily_identity_gate(
    normalized: MassiveNormalizedDailyFile,
    *,
    aliases: Sequence[SymbolAlias],
    query_time: datetime,
    received_at: datetime,
    processed_at: datetime,
    available_at: datetime,
    version: int = 1,
) -> MassiveDailyIdentityGate:
    """Resolve explicit Massive aliases and materialize only eligible canonical bars."""

    records: list[MassiveDailyIdentityGateRecord] = []
    eligible = pending = conflict = invalid = 0

    for record in normalized.records:
        identity = resolve_symbol_identity(
            symbol=record.symbol,
            provider=MASSIVE_PROVIDER,
            feed=MASSIVE_GROUPED_DAILY_FEED,
            effective_time=record.source_timestamp,
            query_time=query_time,
            aliases=aliases,
        )

        if identity.status == IdentityStatus.UNRESOLVED:
            records.append(
                MassiveDailyIdentityGateRecord(
                    record=record,
                    identity=identity,
                    eligibility=DailyBarEligibility.PENDING_IDENTITY,
                    instrument_id=None,
                    canonical_bar=None,
                )
            )
            pending += 1
            continue

        if identity.status == IdentityStatus.AMBIGUOUS:
            records.append(
                MassiveDailyIdentityGateRecord(
                    record=record,
                    identity=identity,
                    eligibility=DailyBarEligibility.IDENTITY_CONFLICT,
                    instrument_id=None,
                    canonical_bar=None,
                )
            )
            conflict += 1
            continue

        instrument_id = identity.instrument_id
        if instrument_id is None:
            raise AssertionError("RESOLVED identity must carry instrument_id")

        try:
            bar = CanonicalDailyBar(
                instrument_id=instrument_id,
                symbol=record.symbol,
                session_date=normalized.session_date,
                event_time=record.source_timestamp,
                source_timestamp=record.source_timestamp,
                received_at=received_at,
                processed_at=processed_at,
                available_at=available_at,
                provider=MASSIVE_PROVIDER,
                feed=MASSIVE_GROUPED_DAILY_FEED,
                version=version,
                open=record.open,
                high=record.high,
                low=record.low,
                close=record.close,
                volume=record.volume,
                vwap=record.vwap,
                trade_count=record.trade_count,
                adjustment_policy="raw",
                otc=record.otc,
            )
        except ValidationError:
            records.append(
                MassiveDailyIdentityGateRecord(
                    record=record,
                    identity=identity,
                    eligibility=DailyBarEligibility.INVALID_DATA,
                    instrument_id=instrument_id,
                    canonical_bar=None,
                )
            )
            invalid += 1
            continue

        records.append(
            MassiveDailyIdentityGateRecord(
                record=record,
                identity=identity,
                eligibility=DailyBarEligibility.ELIGIBLE,
                instrument_id=instrument_id,
                canonical_bar=bar,
            )
        )
        eligible += 1

    return MassiveDailyIdentityGate(
        session_date=normalized.session_date,
        request_id=normalized.request_id,
        records=tuple(records),
        total_count=len(records),
        eligible_count=eligible,
        pending_identity_count=pending,
        conflict_count=conflict,
        invalid_data_count=invalid,
    )
