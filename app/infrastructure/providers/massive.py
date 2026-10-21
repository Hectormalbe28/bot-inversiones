"""Strict parser and deterministic normalization for Massive grouped daily evidence.

Provider rows remain provider evidence here. This module never allocates or infers
canonical instrument identity and never persists data.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any


class MassiveGroupedDailyParseError(ValueError):
    """Malformed or canonically unusable grouped-daily provider payload."""


class MassiveGroupedDailyNormalizationError(ValueError):
    """Ambiguous provider evidence that cannot be normalized deterministically."""


@dataclass(frozen=True, slots=True)
class MassiveDailyRawRecord:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None
    trade_count: int | None
    source_timestamp: datetime
    otc: bool | None = None


@dataclass(frozen=True, slots=True)
class MassiveGroupedDailyFile:
    session_date: date
    adjusted: bool
    status: str
    request_id: str | None
    query_count: int | None
    declared_results_count: int | None
    records: tuple[MassiveDailyRawRecord, ...]


@dataclass(frozen=True, slots=True)
class MassiveNormalizedDailyFile:
    session_date: date
    request_id: str | None
    query_count: int | None
    declared_results_count: int | None
    parsed_results_count: int
    result_count_mismatch: bool
    duplicate_identical_count: int
    records: tuple[MassiveDailyRawRecord, ...]


def parse_massive_grouped_daily(
    raw: bytes,
    *,
    session_date: date,
) -> MassiveGroupedDailyFile:
    """Parse one raw grouped-daily JSON response without identity inference."""

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise MassiveGroupedDailyParseError("Invalid grouped-daily JSON payload") from exc

    if not isinstance(payload, dict):
        raise MassiveGroupedDailyParseError("Grouped-daily JSON root must be an object")

    status = payload.get("status")
    if status != "OK":
        raise MassiveGroupedDailyParseError("Grouped-daily status must be OK")

    adjusted = payload.get("adjusted")
    if adjusted is not False:
        raise MassiveGroupedDailyParseError("Sprint 3 canonical path requires adjusted=false")

    results = payload.get("results")
    if not isinstance(results, list):
        raise MassiveGroupedDailyParseError("Grouped-daily results must be an array")

    request_id = payload.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise MassiveGroupedDailyParseError("request_id must be a string when present")

    query_count = _optional_nonnegative_int(payload.get("queryCount"), "queryCount")
    results_count = _optional_nonnegative_int(payload.get("resultsCount"), "resultsCount")

    records = tuple(_parse_record(item, index) for index, item in enumerate(results))

    return MassiveGroupedDailyFile(
        session_date=session_date,
        adjusted=False,
        status=status,
        request_id=request_id,
        query_count=query_count,
        declared_results_count=results_count,
        records=records,
    )


def normalize_massive_grouped_daily(
    parsed: MassiveGroupedDailyFile,
) -> MassiveNormalizedDailyFile:
    """Deduplicate exact provider repeats and reject divergent ticker collisions."""

    by_symbol: dict[str, MassiveDailyRawRecord] = {}
    identical_duplicates = 0

    for record in parsed.records:
        existing = by_symbol.get(record.symbol)
        if existing is None:
            by_symbol[record.symbol] = record
            continue
        if existing == record:
            identical_duplicates += 1
            continue
        raise MassiveGroupedDailyNormalizationError(
            f"Divergent duplicate ticker {record.symbol} in grouped-daily response"
        )

    records = tuple(by_symbol[symbol] for symbol in sorted(by_symbol))
    parsed_count = len(parsed.records)
    mismatch = parsed.declared_results_count is not None and (
        parsed.declared_results_count != parsed_count
    )

    return MassiveNormalizedDailyFile(
        session_date=parsed.session_date,
        request_id=parsed.request_id,
        query_count=parsed.query_count,
        declared_results_count=parsed.declared_results_count,
        parsed_results_count=parsed_count,
        result_count_mismatch=mismatch,
        duplicate_identical_count=identical_duplicates,
        records=records,
    )


def _parse_record(item: Any, index: int) -> MassiveDailyRawRecord:
    if not isinstance(item, dict):
        raise MassiveGroupedDailyParseError(f"results[{index}] must be an object")

    symbol = item.get("T")
    if not isinstance(symbol, str) or not symbol.strip():
        raise MassiveGroupedDailyParseError(f"results[{index}] ticker is required")
    symbol = symbol.strip()

    open_price = _required_nonnegative_number(item, "o", "open", index)
    high = _required_nonnegative_number(item, "h", "high", index)
    low = _required_nonnegative_number(item, "l", "low", index)
    close = _required_nonnegative_number(item, "c", "close", index)
    volume = _required_nonnegative_number(item, "v", "volume", index)

    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise MassiveGroupedDailyParseError(
            f"results[{index}] has inconsistent OHLC range"
        )

    vwap = _optional_nonnegative_number(item.get("vw"), "vwap", index)
    trade_count = _optional_nonnegative_int(item.get("n"), f"results[{index}] trade_count")

    timestamp_ms = item.get("t")
    if (
        isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, (int, float))
        or not math.isfinite(float(timestamp_ms))
        or timestamp_ms < 0
    ):
        raise MassiveGroupedDailyParseError(
            f"results[{index}] timestamp must be nonnegative milliseconds"
        )
    try:
        source_timestamp = datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise MassiveGroupedDailyParseError(
            f"results[{index}] timestamp is outside supported range"
        ) from exc

    otc = item.get("otc")
    if otc is not None and not isinstance(otc, bool):
        raise MassiveGroupedDailyParseError(
            f"results[{index}] otc must be boolean when present"
        )

    return MassiveDailyRawRecord(
        symbol=symbol,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        vwap=vwap,
        trade_count=trade_count,
        source_timestamp=source_timestamp,
        otc=otc,
    )


def _required_nonnegative_number(
    item: dict[str, Any],
    provider_key: str,
    field_name: str,
    index: int,
) -> float:
    if provider_key not in item:
        raise MassiveGroupedDailyParseError(
            f"results[{index}] {field_name} is required"
        )
    value = item[provider_key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise MassiveGroupedDailyParseError(
            f"results[{index}] {field_name} must be a finite nonnegative number"
        )
    return float(value)


def _optional_nonnegative_number(
    value: Any,
    field_name: str,
    index: int,
) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise MassiveGroupedDailyParseError(
            f"results[{index}] {field_name} must be a finite nonnegative number"
        )
    return float(value)


def _optional_nonnegative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MassiveGroupedDailyParseError(
            f"{field_name} must be a nonnegative integer when present"
        )
    return value
