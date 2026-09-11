"""Acceptance tests for the Nasdaq Symbol Directory parser (nasdaqlisted.txt).

Validates pure deterministic parsing of raw provider bytes into provider DTOs,
strict schema enforcement, and absence of identity inference or domain normalization.
"""

from pathlib import Path

import pytest

from app.infrastructure.providers.nasdaq import (
    NasdaqDecodingError,
    NasdaqListedFile,
    NasdaqListedRawRecord,
    NasdaqMalformedRowError,
    NasdaqSchemaError,
    NasdaqSymbolDirectoryError,
    parse_nasdaqlisted,
)

FIXTURES_DIR = Path("tests/fixtures/nasdaq")


def _read_fixture(filename: str) -> bytes:
    return (FIXTURES_DIR / filename).read_bytes()


def test_valid_fixture_parses_successfully():
    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    assert isinstance(result, NasdaqListedFile)


def test_parsed_record_count_is_correct():
    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    assert len(result.records) == 5


def test_all_provider_columns_are_preserved():
    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    first = result.records[0]
    assert first.symbol == "AAPL"
    assert first.security_name == "Apple Inc. - Common Stock"
    assert first.market_category == "Q"
    assert first.test_issue == "N"
    assert first.financial_status == "N"
    assert first.round_lot_size == "100"
    assert first.etf == "N"
    assert first.next_shares == "N"


def test_footer_is_separated_from_securities():
    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    assert result.file_creation_time_raw == "0911202612:11"
    symbols = [r.symbol for r in result.records]
    assert not any("File Creation Time" in s for s in symbols)


def test_empty_universe_returns_empty_tuple():
    raw = _read_fixture("nasdaqlisted_empty_universe.txt")
    result = parse_nasdaqlisted(raw)
    assert result.records == ()
    assert result.file_creation_time_raw == "0911202612:11"


def test_test_issue_y_preserved():
    raw = _read_fixture("nasdaqlisted_test_issue.txt")
    result = parse_nasdaqlisted(raw)
    test_issues = [r for r in result.records if r.test_issue == "Y"]
    assert len(test_issues) == 2
    assert {r.symbol for r in test_issues} == {"ZXYZ.A", "ZXZZT"}


def test_non_normal_financial_status_preserved():
    raw = _read_fixture("nasdaqlisted_financial_status.txt")
    result = parse_nasdaqlisted(raw)
    statuses = {r.financial_status for r in result.records}
    assert "D" in statuses
    assert "E" in statuses
    assert "Q" in statuses
    assert "G" in statuses
    assert "H" in statuses
    assert "J" in statuses
    assert "K" in statuses
    assert "N" in statuses


def test_duplicate_symbols_remain_duplicated():
    raw = _read_fixture("nasdaqlisted_duplicate_symbol.txt")
    result = parse_nasdaqlisted(raw)
    symbols = [r.symbol for r in result.records]
    assert symbols.count("AAPL") == 2
    assert len(result.records) == 3


def test_symbol_variants_parse_without_identity_inference():
    raw = _read_fixture("nasdaqlisted_symbol_variants.txt")
    result = parse_nasdaqlisted(raw)
    symbols = [r.symbol for r in result.records]
    assert "A" in symbols
    assert "GOOG" in symbols
    assert "GOOGL" in symbols
    assert "BRK.B" in symbols
    assert "ZXYZ.A" in symbols


def test_missing_footer_fails():
    raw = _read_fixture("nasdaqlisted_missing_footer.txt")
    with pytest.raises(NasdaqSymbolDirectoryError):
        parse_nasdaqlisted(raw)


def test_bad_header_fails():
    raw = _read_fixture("nasdaqlisted_bad_header.txt")
    with pytest.raises(NasdaqSchemaError):
        parse_nasdaqlisted(raw)


def test_malformed_field_count_fails():
    raw = _read_fixture("nasdaqlisted_malformed_row.txt")
    with pytest.raises(NasdaqMalformedRowError):
        parse_nasdaqlisted(raw)


def test_schema_extension_fails():
    raw = _read_fixture("nasdaqlisted_schema_extension.txt")
    with pytest.raises(NasdaqSchemaError):
        parse_nasdaqlisted(raw)


def test_second_footer_fails():
    valid = _read_fixture("nasdaqlisted_valid.txt")
    extra_footer = b"File Creation Time: 0911202612:12|||||||\n"
    raw = valid + extra_footer
    with pytest.raises(NasdaqSymbolDirectoryError):
        parse_nasdaqlisted(raw)


def test_data_row_after_footer_fails():
    valid = _read_fixture("nasdaqlisted_valid.txt")
    trailing_row = b"MSFT|Microsoft Corporation - Common Stock|Q|N|N|100|N|N\n"
    raw = valid + trailing_row
    with pytest.raises(NasdaqSymbolDirectoryError):
        parse_nasdaqlisted(raw)


def test_invalid_encoding_fails():
    raw = bytes([0xFF, 0xFE, 0x80])
    with pytest.raises((NasdaqDecodingError, NasdaqSymbolDirectoryError)):
        parse_nasdaqlisted(raw)


def test_parser_does_not_emit_instrument_id():
    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    assert not hasattr(result, "instrument_id")
    for r in result.records:
        assert not hasattr(r, "instrument_id")


def test_parser_does_not_create_domain_instrument():
    from app.domain.models import Instrument, InstrumentVersion

    raw = _read_fixture("nasdaqlisted_valid.txt")
    result = parse_nasdaqlisted(raw)
    for r in result.records:
        assert isinstance(r, NasdaqListedRawRecord)
        assert not isinstance(r, (Instrument, InstrumentVersion))
