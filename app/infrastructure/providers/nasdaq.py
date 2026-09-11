"""Deterministic parser and normalizer for Nasdaq Trader Symbol Directory.

This module parses raw bytes from the Nasdaq Trader Symbol Directory (nasdaqlisted.txt)
into raw provider DTOs and normalizes them into typed provider records.
It enforces strict schema validation and preserves provider evidence without performing
identity inference, entity resolution, domain normalization, or trading eligibility filtering.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.application.identity import IdentityResolution, resolve_symbol_identity
from app.domain.models import SymbolAlias

EXPECTED_HEADER: Final[str] = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)
EXPECTED_FIELD_COUNT: Final[int] = 8
FOOTER_PREFIX: Final[str] = "File Creation Time: "

VALID_MARKET_CATEGORIES: Final[frozenset[str]] = frozenset({"Q", "G", "S"})
VALID_FINANCIAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"N", "D", "E", "Q", "G", "H", "J", "K"}
)
_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9.]{1,14}$")


class NasdaqSymbolDirectoryError(Exception):
    """Base exception for all Nasdaq Symbol Directory errors."""


class NasdaqDecodingError(NasdaqSymbolDirectoryError):
    """Raised when raw provider bytes cannot be decoded as UTF-8."""


class NasdaqSchemaError(NasdaqSymbolDirectoryError):
    """Raised when the provider header or schema does not match the frozen specification."""


class NasdaqMalformedRowError(NasdaqSymbolDirectoryError):
    """Raised when a data row or footer does not contain the expected field count."""


class NasdaqNormalizationError(NasdaqSymbolDirectoryError):
    """Raised when a provider field cannot be deterministically normalized."""


@dataclass(frozen=True, slots=True)
class NasdaqListedRawRecord:
    """Raw provider record representing one row of nasdaqlisted.txt.

    Preserves provider fields essentially as received.
    Contains no domain identity (instrument_id) or temporal semantics.
    """

    symbol: str
    security_name: str
    market_category: str
    test_issue: str
    financial_status: str
    round_lot_size: str
    etf: str
    next_shares: str


@dataclass(frozen=True, slots=True)
class NasdaqListedFile:
    """Parsed representation of a complete nasdaqlisted.txt file.

    Contains a sequence of raw records and provider-level metadata.
    """

    records: tuple[NasdaqListedRawRecord, ...]
    file_creation_time_raw: str


@dataclass(frozen=True, slots=True)
class NasdaqNormalizedRecord:
    """Typed normalized provider record representing one Nasdaq security.

    Contains validated, typed provider fields.
    Does not contain instrument_id, domain models, or trading eligibility rules.
    """

    symbol: str
    security_name: str
    market_category: str
    test_issue: bool
    financial_status: str
    round_lot_size: int
    is_etf: bool
    is_nextshares: bool


@dataclass(frozen=True, slots=True)
class NasdaqNormalizedFile:
    """Normalized representation of a complete nasdaqlisted.txt file.

    Contains a sequence of typed normalized records and provider-level metadata.
    Does not contain instrument_id, domain models, or trading eligibility rules.
    """

    records: tuple[NasdaqNormalizedRecord, ...]
    file_creation_time_raw: str


@dataclass(frozen=True, slots=True)
class NasdaqIdentityRecord:
    """Pairing of a normalized provider record with its resolved identity evidence.

    Preserves the unchanged provider record alongside the explicit IdentityResolution.
    """

    record: NasdaqNormalizedRecord
    identity: IdentityResolution


@dataclass(frozen=True, slots=True)
class NasdaqIdentityResolutionFile:
    """Representation of a complete Nasdaq file whose records have undergone identity resolution.

    Contains the resolved identity records and unchanged file creation timestamp metadata.
    """

    records: tuple[NasdaqIdentityRecord, ...]
    file_creation_time_raw: str


def parse_nasdaqlisted(raw: bytes) -> NasdaqListedFile:
    """Parse raw bytes of a nasdaqlisted.txt file into a NasdaqListedFile DTO.

    Args:
        raw: Raw bytes of the pipe-delimited file.

    Returns:
        NasdaqListedFile containing immutable parsed records and footer metadata.

    Raises:
        NasdaqDecodingError: If bytes cannot be decoded as UTF-8.
        NasdaqSchemaError: If header does not match expected schema.
        NasdaqMalformedRowError: If any row has an invalid field count.
        NasdaqSymbolDirectoryError: If footer is missing, duplicated, or trailing data exists.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NasdaqDecodingError(f"Failed to decode nasdaqlisted file as UTF-8: {exc}") from exc

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise NasdaqSchemaError("Empty file content; missing required header.")

    header = lines[0]
    if header != EXPECTED_HEADER:
        raise NasdaqSchemaError(f"Invalid header. Expected: '{EXPECTED_HEADER}', got: '{header}'")

    records: list[NasdaqListedRawRecord] = []
    file_creation_time_raw: str | None = None
    footer_seen = False

    for line_idx, line in enumerate(lines[1:], start=2):
        if footer_seen:
            raise NasdaqSymbolDirectoryError(
                f"Data row found after footer at line {line_idx}: {line[:30]}"
            )

        if line.startswith("File Creation Time"):
            if not line.startswith(FOOTER_PREFIX):
                raise NasdaqMalformedRowError(
                    f"Malformed footer prefix at line {line_idx}: {line[:30]}"
                )
            footer_parts = line.split("|")
            if len(footer_parts) != EXPECTED_FIELD_COUNT:
                raise NasdaqMalformedRowError(
                    f"Footer field count mismatch at line {line_idx}: "
                    f"expected {EXPECTED_FIELD_COUNT}, got {len(footer_parts)}"
                )
            if footer_seen:
                raise NasdaqSymbolDirectoryError(f"Duplicate footer encountered at line {line_idx}")
            footer_seen = True
            file_creation_time_raw = footer_parts[0].removeprefix(FOOTER_PREFIX).strip()
            continue

        parts = line.split("|")
        if len(parts) != EXPECTED_FIELD_COUNT:
            raise NasdaqMalformedRowError(
                f"Malformed row at line {line_idx}: "
                f"expected {EXPECTED_FIELD_COUNT} fields, got {len(parts)}"
            )

        record = NasdaqListedRawRecord(
            symbol=parts[0],
            security_name=parts[1],
            market_category=parts[2],
            test_issue=parts[3],
            financial_status=parts[4],
            round_lot_size=parts[5],
            etf=parts[6],
            next_shares=parts[7],
        )
        records.append(record)

    if not footer_seen or file_creation_time_raw is None:
        raise NasdaqSymbolDirectoryError("Missing required 'File Creation Time' footer row.")

    return NasdaqListedFile(
        records=tuple(records),
        file_creation_time_raw=file_creation_time_raw,
    )


def normalize_nasdaq_record(record: NasdaqListedRawRecord) -> NasdaqNormalizedRecord:
    """Normalize a raw Nasdaq record into a typed, validated normalized record.

    Args:
        record: Raw parsed provider record.

    Returns:
        NasdaqNormalizedRecord with typed fields.

    Raises:
        NasdaqNormalizationError: If any field fails validation.
    """
    if not _SYMBOL_PATTERN.match(record.symbol):
        raise NasdaqNormalizationError(
            f"Invalid provider symbol: {record.symbol!r}. Must match {_SYMBOL_PATTERN.pattern}"
        )

    clean_security_name = record.security_name.strip()
    if not clean_security_name:
        raise NasdaqNormalizationError("Security name cannot be empty.")

    if record.market_category not in VALID_MARKET_CATEGORIES:
        raise NasdaqNormalizationError(
            f"Invalid market category: {record.market_category!r}. "
            f"Expected one of {sorted(VALID_MARKET_CATEGORIES)}"
        )

    if record.test_issue == "Y":
        test_issue = True
    elif record.test_issue == "N":
        test_issue = False
    else:
        raise NasdaqNormalizationError(
            f"Invalid Test Issue value: {record.test_issue!r}. Expected 'Y' or 'N'."
        )

    if record.financial_status not in VALID_FINANCIAL_STATUSES:
        raise NasdaqNormalizationError(
            f"Invalid Financial Status code: {record.financial_status!r}. "
            f"Expected one of {sorted(VALID_FINANCIAL_STATUSES)}"
        )

    if not record.round_lot_size.isdigit():
        raise NasdaqNormalizationError(
            f"Round Lot Size must be a decimal integer, got {record.round_lot_size!r}"
        )
    round_lot_size = int(record.round_lot_size)
    if round_lot_size < 1:
        raise NasdaqNormalizationError(f"Round Lot Size must be >= 1, got {round_lot_size}")

    if record.etf == "Y":
        is_etf = True
    elif record.etf == "N":
        is_etf = False
    else:
        raise NasdaqNormalizationError(f"Invalid ETF flag: {record.etf!r}. Expected 'Y' or 'N'.")

    if record.next_shares == "Y":
        is_nextshares = True
    elif record.next_shares == "N":
        is_nextshares = False
    else:
        raise NasdaqNormalizationError(
            f"Invalid NextShares flag: {record.next_shares!r}. Expected 'Y' or 'N'."
        )

    return NasdaqNormalizedRecord(
        symbol=record.symbol,
        security_name=clean_security_name,
        market_category=record.market_category,
        test_issue=test_issue,
        financial_status=record.financial_status,
        round_lot_size=round_lot_size,
        is_etf=is_etf,
        is_nextshares=is_nextshares,
    )


def normalize_nasdaqlisted(parsed: NasdaqListedFile) -> NasdaqNormalizedFile:
    """Normalize a parsed NasdaqListedFile into a typed NasdaqNormalizedFile DTO.

    Args:
        parsed: Parsed provider file DTO containing raw records and footer metadata.

    Returns:
        NasdaqNormalizedFile with all records deterministically normalized.

    Raises:
        NasdaqNormalizationError: If any record in the file fails normalization (all-or-nothing).
    """
    normalized_records: list[NasdaqNormalizedRecord] = []
    for record in parsed.records:
        normalized_records.append(normalize_nasdaq_record(record))

    return NasdaqNormalizedFile(
        records=tuple(normalized_records),
        file_creation_time_raw=parsed.file_creation_time_raw,
    )


def resolve_nasdaq_identities(
    normalized: NasdaqNormalizedFile,
    *,
    aliases: Sequence[SymbolAlias],
    effective_time: datetime,
    query_time: datetime,
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
) -> NasdaqIdentityResolutionFile:
    """Resolve identities for all records in a normalized Nasdaq file.

    Preserves provider row order and duplicates. Records whose identity cannot be
    unambiguously resolved are assigned UNRESOLVED or AMBIGUOUS status with None ID.

    Args:
        normalized: NasdaqNormalizedFile with typed provider records.
        aliases: Sequence of explicit SymbolAlias domain records.
        effective_time: Point in time for which identity is being resolved.
        query_time: Knowledge cutoff point in time.
        provider: Exact provider identifier (defaults to 'nasdaq').
        feed: Exact provider feed identifier (defaults to 'symbol_directory').

    Returns:
        NasdaqIdentityResolutionFile with resolved identity records.
    """
    resolution_records: list[NasdaqIdentityRecord] = []
    for rec in normalized.records:
        identity = resolve_symbol_identity(
            symbol=rec.symbol,
            provider=provider,
            feed=feed,
            effective_time=effective_time,
            query_time=query_time,
            aliases=aliases,
        )
        resolution_records.append(
            NasdaqIdentityRecord(
                record=rec,
                identity=identity,
            )
        )

    return NasdaqIdentityResolutionFile(
        records=tuple(resolution_records),
        file_creation_time_raw=normalized.file_creation_time_raw,
    )
