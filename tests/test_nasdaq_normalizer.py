"""Acceptance tests for Nasdaq record and file normalization.

Validates pure deterministic normalization of parsed Nasdaq Symbol Directory
DTOs into typed normalized records, strict domain boundaries, and absence of
identity inference or filtering.
"""

from pathlib import Path

import pytest

from app.infrastructure.providers.nasdaq import (
    NasdaqListedFile,
    NasdaqListedRawRecord,
    NasdaqNormalizationError,
    NasdaqNormalizedFile,
    NasdaqNormalizedRecord,
    normalize_nasdaq_record,
    normalize_nasdaqlisted,
    parse_nasdaqlisted,
)

FIXTURES_DIR = Path("tests/fixtures/nasdaq")


def _read_fixture(filename: str) -> bytes:
    return (FIXTURES_DIR / filename).read_bytes()


def _make_raw_record(
    symbol: str = "AAPL",
    security_name: str = "Apple Inc. - Common Stock",
    market_category: str = "Q",
    test_issue: str = "N",
    financial_status: str = "N",
    round_lot_size: str = "100",
    etf: str = "N",
    next_shares: str = "N",
) -> NasdaqListedRawRecord:
    return NasdaqListedRawRecord(
        symbol=symbol,
        security_name=security_name,
        market_category=market_category,
        test_issue=test_issue,
        financial_status=financial_status,
        round_lot_size=round_lot_size,
        etf=etf,
        next_shares=next_shares,
    )


def test_normal_provider_record_normalizes_successfully():
    raw = _make_raw_record()
    norm = normalize_nasdaq_record(raw)
    assert isinstance(norm, NasdaqNormalizedRecord)
    assert norm.symbol == "AAPL"
    assert norm.security_name == "Apple Inc. - Common Stock"
    assert norm.market_category == "Q"
    assert norm.test_issue is False
    assert norm.financial_status == "N"
    assert norm.round_lot_size == 100
    assert norm.is_etf is False
    assert norm.is_nextshares is False


def test_q_market_category_accepted():
    raw = _make_raw_record(market_category="Q")
    norm = normalize_nasdaq_record(raw)
    assert norm.market_category == "Q"


def test_g_market_category_accepted():
    raw = _make_raw_record(market_category="G")
    norm = normalize_nasdaq_record(raw)
    assert norm.market_category == "G"


def test_s_market_category_accepted():
    raw = _make_raw_record(market_category="S")
    norm = normalize_nasdaq_record(raw)
    assert norm.market_category == "S"


def test_unknown_market_category_rejected():
    raw = _make_raw_record(market_category="X")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_test_issue_n_to_false():
    raw = _make_raw_record(test_issue="N")
    norm = normalize_nasdaq_record(raw)
    assert norm.test_issue is False


def test_test_issue_y_to_true():
    raw = _make_raw_record(test_issue="Y")
    norm = normalize_nasdaq_record(raw)
    assert norm.test_issue is True


def test_invalid_test_issue_rejected():
    raw = _make_raw_record(test_issue="MAYBE")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_all_official_financial_status_codes_accepted():
    for code in ["N", "D", "E", "Q", "G", "H", "J", "K"]:
        raw = _make_raw_record(financial_status=code)
        norm = normalize_nasdaq_record(raw)
        assert norm.financial_status == code


def test_unknown_financial_status_rejected():
    raw = _make_raw_record(financial_status="Z")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_round_lot_size_parses_to_int():
    raw = _make_raw_record(round_lot_size="100")
    norm = normalize_nasdaq_record(raw)
    assert norm.round_lot_size == 100
    assert isinstance(norm.round_lot_size, int)


def test_zero_round_lot_rejected():
    raw = _make_raw_record(round_lot_size="0")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_negative_round_lot_rejected():
    raw = _make_raw_record(round_lot_size="-100")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_decimal_round_lot_rejected():
    raw = _make_raw_record(round_lot_size="100.0")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_nonnumeric_round_lot_rejected():
    raw = _make_raw_record(round_lot_size="ONE_HUNDRED")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_etf_y_n_maps_to_bool():
    norm_n = normalize_nasdaq_record(_make_raw_record(etf="N"))
    assert norm_n.is_etf is False
    norm_y = normalize_nasdaq_record(_make_raw_record(etf="Y"))
    assert norm_y.is_etf is True


def test_invalid_etf_value_rejected():
    raw = _make_raw_record(etf="TRUE")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_nextshares_y_n_maps_to_bool():
    norm_n = normalize_nasdaq_record(_make_raw_record(next_shares="N"))
    assert norm_n.is_nextshares is False
    norm_y = normalize_nasdaq_record(_make_raw_record(next_shares="Y"))
    assert norm_y.is_nextshares is True


def test_invalid_nextshares_rejected():
    raw = _make_raw_record(next_shares="X")
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(raw)


def test_security_name_cannot_be_empty():
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(_make_raw_record(security_name=""))
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaq_record(_make_raw_record(security_name="   "))


def test_approved_symbol_variants_accepted():
    variants = ["A", "AAPL", "MSFT", "GOOGL", "BRK.B", "ZXYZ.A"]
    for sym in variants:
        norm = normalize_nasdaq_record(_make_raw_record(symbol=sym))
        assert norm.symbol == sym


def test_invalid_symbol_rejected():
    invalid_symbols = ["", "  ", "aapl", "AAPL INC", "TOOLONGSYMBOLFORNASDAQ"]
    for sym in invalid_symbols:
        with pytest.raises(NasdaqNormalizationError):
            normalize_nasdaq_record(_make_raw_record(symbol=sym))


def test_no_instrument_id_exists():
    raw = _make_raw_record()
    norm = normalize_nasdaq_record(raw)
    assert not hasattr(norm, "instrument_id")


def test_result_is_not_instrument():
    from app.domain.models import Instrument

    raw = _make_raw_record()
    norm = normalize_nasdaq_record(raw)
    assert isinstance(norm, NasdaqNormalizedRecord)
    assert not isinstance(norm, Instrument)


def test_result_is_not_instrument_version():
    from app.domain.models import InstrumentVersion

    raw = _make_raw_record()
    norm = normalize_nasdaq_record(raw)
    assert isinstance(norm, NasdaqNormalizedRecord)
    assert not isinstance(norm, InstrumentVersion)


# ==================================================
# Phase B Tests: File / Batch Normalization
# ==================================================


def test_valid_parsed_file_normalizes_all_records():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    assert isinstance(norm_file, NasdaqNormalizedFile)
    assert len(norm_file.records) == len(raw_file.records)
    assert len(norm_file.records) == 5


def test_output_order_equals_parsed_order():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    raw_symbols = [r.symbol for r in raw_file.records]
    norm_symbols = [r.symbol for r in norm_file.records]
    assert norm_symbols == raw_symbols


def test_duplicate_symbols_remain_duplicated_in_file():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_duplicate_symbol.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    norm_symbols = [r.symbol for r in norm_file.records]
    assert norm_symbols.count("AAPL") == 2
    assert len(norm_file.records) == len(raw_file.records)


def test_test_issue_rows_remain_present_in_file():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_test_issue.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    test_issues = [r for r in norm_file.records if r.test_issue is True]
    assert len(test_issues) == 2
    assert {r.symbol for r in test_issues} == {"ZXYZ.A", "ZXZZT"}


def test_non_normal_financial_status_rows_remain_present_in_file():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_financial_status.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    statuses = {r.financial_status for r in norm_file.records}
    assert statuses == {"N", "D", "E", "Q", "G", "H", "J", "K"}


def test_empty_universe_normalizes_to_empty_tuple():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_empty_universe.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    assert norm_file.records == ()
    assert norm_file.file_creation_time_raw == raw_file.file_creation_time_raw


def test_footer_raw_text_is_preserved_exactly():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    assert norm_file.file_creation_time_raw == "0911202612:11"
    assert norm_file.file_creation_time_raw == raw_file.file_creation_time_raw


def test_invalid_middle_record_causes_whole_normalization_failure():
    valid_rec = _make_raw_record(symbol="AAPL")
    invalid_rec = _make_raw_record(symbol="BAD_LOT", round_lot_size="INVALID")
    file_with_bad_middle = NasdaqListedFile(
        records=(valid_rec, invalid_rec, valid_rec),
        file_creation_time_raw="0911202612:11",
    )
    with pytest.raises(NasdaqNormalizationError):
        normalize_nasdaqlisted(file_with_bad_middle)


def test_no_partial_result_is_returned_on_failure():
    valid_rec = _make_raw_record(symbol="AAPL")
    invalid_rec = _make_raw_record(symbol="INVALID", market_category="UNKNOWN")
    file_with_bad = NasdaqListedFile(
        records=(valid_rec, invalid_rec),
        file_creation_time_raw="0911202612:11",
    )
    try:
        normalize_nasdaqlisted(file_with_bad)
    except NasdaqNormalizationError:
        pass
    else:
        pytest.fail("Expected NasdaqNormalizationError to be raised")


def test_output_file_contains_no_instrument_id():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    assert not hasattr(norm_file, "instrument_id")
    for r in norm_file.records:
        assert not hasattr(r, "instrument_id")


def test_no_instrument_or_version_emitted():
    from app.domain.models import Instrument, InstrumentVersion

    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    norm_file = normalize_nasdaqlisted(raw_file)
    for r in norm_file.records:
        assert not isinstance(r, (Instrument, InstrumentVersion))


def test_repeated_normalization_returns_equal_result():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    res1 = normalize_nasdaqlisted(raw_file)
    res2 = normalize_nasdaqlisted(raw_file)
    assert res1 == res2
    assert res1.records == res2.records


def test_input_object_is_not_mutated():
    raw_file = parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt"))
    orig_records = raw_file.records
    orig_footer = raw_file.file_creation_time_raw
    normalize_nasdaqlisted(raw_file)
    assert raw_file.records == orig_records
    assert raw_file.file_creation_time_raw == orig_footer
