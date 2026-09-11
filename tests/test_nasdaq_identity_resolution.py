"""Acceptance tests for Nasdaq Symbol Directory file identity resolution.

Validates end-to-end resolution of normalized Nasdaq provider files against explicit
temporal SymbolAlias evidence, ticker change transitions, ticker reuses,
late-known evidence, and absence of name-based or backward leakage.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.application.identity import IdentityReason, IdentityStatus
from app.domain.models import SymbolAlias
from app.infrastructure.providers.nasdaq import (
    NasdaqIdentityResolutionFile,
    NasdaqNormalizedFile,
    NasdaqNormalizedRecord,
    normalize_nasdaqlisted,
    parse_nasdaqlisted,
    resolve_nasdaq_identities,
)

FIXTURES_DIR = Path("tests/fixtures/nasdaq")

T0 = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
T2 = datetime(2025, 12, 1, 0, 0, tzinfo=UTC)


def _read_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _make_alias(
    symbol: str,
    instrument_id: str,
    provider: str = "nasdaq",
    feed: str = "symbol_directory",
    available_at: datetime = T0,
    valid_from: datetime = T0,
    valid_to: datetime | None = None,
    event_time: datetime = T0,
    version: int = 1,
) -> SymbolAlias:
    return SymbolAlias(
        symbol=symbol,
        instrument_id=instrument_id,
        provider=provider,
        feed=feed,
        source_timestamp=available_at,
        received_at=available_at,
        processed_at=available_at,
        available_at=available_at,
        valid_from=valid_from,
        valid_to=valid_to,
        event_time=event_time,
        version=version,
    )


def test_fully_resolved_normalized_file():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    # Create aliases for all 5 valid symbols
    aliases = [
        _make_alias(symbol=r.symbol, instrument_id=f"inst-{r.symbol.lower()}")
        for r in norm_file.records
    ]

    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    assert isinstance(res_file, NasdaqIdentityResolutionFile)
    assert len(res_file.records) == 5
    for ir in res_file.records:
        assert ir.identity.status == IdentityStatus.RESOLVED
        assert ir.identity.instrument_id == f"inst-{ir.record.symbol.lower()}"


def test_fully_unresolved_file():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=(),
        effective_time=T0,
        query_time=T0,
    )
    assert len(res_file.records) == len(norm_file.records)
    for ir in res_file.records:
        assert ir.identity.status == IdentityStatus.UNRESOLVED
        assert ir.identity.instrument_id is None
        assert ir.identity.reason == IdentityReason.NO_ELIGIBLE_ALIAS


def test_mixed_resolved_unresolved_ambiguous():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    # AAPL -> resolved (inst-apple)
    # MSFT -> ambiguous (inst-msft-1 and inst-msft-2)
    # AMZN, ACAD, QQQ -> unresolved
    aliases = [
        _make_alias(symbol="AAPL", instrument_id="inst-apple"),
        _make_alias(symbol="MSFT", instrument_id="inst-msft-1"),
        _make_alias(symbol="MSFT", instrument_id="inst-msft-2"),
    ]

    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    statuses = {ir.record.symbol: ir.identity.status for ir in res_file.records}
    assert statuses["AAPL"] == IdentityStatus.RESOLVED
    assert statuses["MSFT"] == IdentityStatus.AMBIGUOUS
    assert statuses["AMZN"] == IdentityStatus.UNRESOLVED
    assert statuses["ACAD"] == IdentityStatus.UNRESOLVED
    assert statuses["QQQ"] == IdentityStatus.UNRESOLVED


def test_original_row_order_preserved():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    aliases = [
        _make_alias(symbol=r.symbol, instrument_id=f"inst-{r.symbol}") for r in norm_file.records
    ]
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    assert [ir.record.symbol for ir in res_file.records] == [r.symbol for r in norm_file.records]


def test_duplicate_symbols_preserved():
    norm_file = normalize_nasdaqlisted(
        parse_nasdaqlisted(_read_fixture("nasdaqlisted_duplicate_symbol.txt"))
    )
    aliases = [_make_alias(symbol="AAPL", instrument_id="inst-apple")]
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    assert len(res_file.records) == 3
    symbols = [ir.record.symbol for ir in res_file.records]
    assert symbols.count("AAPL") == 2
    for ir in res_file.records:
        if ir.record.symbol == "AAPL":
            assert ir.identity.status == IdentityStatus.RESOLVED
            assert ir.identity.instrument_id == "inst-apple"


def test_empty_normalized_file_returns_empty_result():
    norm_file = normalize_nasdaqlisted(
        parse_nasdaqlisted(_read_fixture("nasdaqlisted_empty_universe.txt"))
    )
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=(),
        effective_time=T0,
        query_time=T0,
    )
    assert res_file.records == ()
    assert res_file.file_creation_time_raw == norm_file.file_creation_time_raw


def test_file_creation_time_raw_preserved_exactly():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=(),
        effective_time=T0,
        query_time=T0,
    )
    assert res_file.file_creation_time_raw == "0911202612:11"
    assert res_file.file_creation_time_raw == norm_file.file_creation_time_raw


def test_unresolved_record_receives_no_instrument_id():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=(),
        effective_time=T0,
        query_time=T0,
    )
    for ir in res_file.records:
        assert ir.identity.instrument_id is None


def test_ambiguous_record_receives_no_instrument_id():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    aliases = [
        _make_alias(symbol="AAPL", instrument_id="inst-1"),
        _make_alias(symbol="AAPL", instrument_id="inst-2"),
    ]
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    aapl_record = next(ir for ir in res_file.records if ir.record.symbol == "AAPL")
    assert aapl_record.identity.status == IdentityStatus.AMBIGUOUS
    assert aapl_record.identity.instrument_id is None


def test_normalized_record_remains_unchanged():
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    orig_record = norm_file.records[0]
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=[_make_alias(symbol=orig_record.symbol, instrument_id="inst-1")],
        effective_time=T0,
        query_time=T0,
    )
    assert res_file.records[0].record == orig_record
    assert res_file.records[0].record is orig_record


def test_ticker_change_scenario():
    # Alias 1: INST-1, OLD, [T0, T1)
    # Alias 2: INST-1, NEW, [T1, None)
    alias_old = _make_alias(symbol="OLD", instrument_id="INST-1", valid_from=T0, valid_to=T1)
    alias_new = _make_alias(symbol="NEW", instrument_id="INST-1", valid_from=T1, valid_to=None)
    aliases = [alias_old, alias_new]

    # At effective_time before T1 (T0): OLD -> INST-1, NEW -> UNRESOLVED
    norm_rec_old = NasdaqNormalizedRecord(
        symbol="OLD",
        security_name="Company 1",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    norm_rec_new = NasdaqNormalizedRecord(
        symbol="NEW",
        security_name="Company 1",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_both = NasdaqNormalizedFile(
        records=(norm_rec_old, norm_rec_new),
        file_creation_time_raw="0911202612:11",
    )

    res_before = resolve_nasdaq_identities(
        file_both,
        aliases=aliases,
        effective_time=T0,
        query_time=T1,
    )
    by_symbol_before = {ir.record.symbol: ir.identity for ir in res_before.records}
    assert by_symbol_before["OLD"].status == IdentityStatus.RESOLVED
    assert by_symbol_before["OLD"].instrument_id == "INST-1"
    assert by_symbol_before["NEW"].status == IdentityStatus.UNRESOLVED

    # At effective_time == T1: OLD -> UNRESOLVED, NEW -> INST-1
    res_at_t1 = resolve_nasdaq_identities(
        file_both,
        aliases=aliases,
        effective_time=T1,
        query_time=T1,
    )
    by_symbol_at_t1 = {ir.record.symbol: ir.identity for ir in res_at_t1.records}
    assert by_symbol_at_t1["OLD"].status == IdentityStatus.UNRESOLVED
    assert by_symbol_at_t1["NEW"].status == IdentityStatus.RESOLVED
    assert by_symbol_at_t1["NEW"].instrument_id == "INST-1"


def test_future_known_ticker_change():
    # Alias NEW known early (available_at T0), but only valid_from T1
    alias_new = _make_alias(symbol="NEW", instrument_id="INST-1", available_at=T0, valid_from=T1)
    norm_rec = NasdaqNormalizedRecord(
        symbol="NEW",
        security_name="Company 1",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    # Before valid_from: UNRESOLVED
    res_early = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_new],
        effective_time=T0,
        query_time=T0,
    )
    assert res_early.records[0].identity.status == IdentityStatus.UNRESOLVED

    # At valid_from: RESOLVED
    res_effective = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_new],
        effective_time=T1,
        query_time=T0,
    )
    assert res_effective.records[0].identity.status == IdentityStatus.RESOLVED
    assert res_effective.records[0].identity.instrument_id == "INST-1"


def test_late_known_ticker_change():
    # Valid starting at T1, but only available at T2
    alias_new = _make_alias(symbol="NEW", instrument_id="INST-1", valid_from=T1, available_at=T2)
    norm_rec = NasdaqNormalizedRecord(
        symbol="NEW",
        security_name="Company 1",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    # effective_time T1, query_time T1 < T2 -> UNRESOLVED
    res_past = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_new],
        effective_time=T1,
        query_time=T1,
    )
    assert res_past.records[0].identity.status == IdentityStatus.UNRESOLVED

    # effective_time T1, query_time T2 -> RESOLVED
    res_now = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_new],
        effective_time=T1,
        query_time=T2,
    )
    assert res_now.records[0].identity.status == IdentityStatus.RESOLVED


def test_ticker_reuse_scenario():
    # ABC -> INST-1 validity [T0, T1)
    # ABC -> INST-2 validity [T1, None)
    alias_inst1 = _make_alias(symbol="ABC", instrument_id="INST-1", valid_from=T0, valid_to=T1)
    alias_inst2 = _make_alias(symbol="ABC", instrument_id="INST-2", valid_from=T1, valid_to=None)
    aliases = [alias_inst1, alias_inst2]

    norm_rec = NasdaqNormalizedRecord(
        symbol="ABC",
        security_name="Company ABC",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    # At old effective time: INST-1
    res_old = resolve_nasdaq_identities(
        file_single,
        aliases=aliases,
        effective_time=T0,
        query_time=T2,
    )
    assert res_old.records[0].identity.status == IdentityStatus.RESOLVED
    assert res_old.records[0].identity.instrument_id == "INST-1"

    # At later effective time: INST-2
    res_new = resolve_nasdaq_identities(
        file_single,
        aliases=aliases,
        effective_time=T1,
        query_time=T2,
    )
    assert res_new.records[0].identity.status == IdentityStatus.RESOLVED
    assert res_new.records[0].identity.instrument_id == "INST-2"


def test_ambiguous_overlap_scenario():
    # Simultaneous distinct IDs for ABC at same time
    alias_inst1 = _make_alias(symbol="ABC", instrument_id="INST-1", valid_from=T0, valid_to=None)
    alias_inst2 = _make_alias(symbol="ABC", instrument_id="INST-2", valid_from=T0, valid_to=None)

    norm_rec = NasdaqNormalizedRecord(
        symbol="ABC",
        security_name="Company ABC",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    res = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_inst1, alias_inst2],
        effective_time=T0,
        query_time=T0,
    )
    assert res.records[0].identity.status == IdentityStatus.AMBIGUOUS
    assert res.records[0].identity.instrument_id is None


def test_current_state_does_not_leak_backward():
    # Only later alias exists: NEW -> INST-1 valid_from T1
    alias_new = _make_alias(symbol="NEW", instrument_id="INST-1", valid_from=T1, valid_to=None)
    norm_rec = NasdaqNormalizedRecord(
        symbol="NEW",
        security_name="Company 1",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    # Historical query at T0 < T1
    res = resolve_nasdaq_identities(
        file_single,
        aliases=[alias_new],
        effective_time=T0,
        query_time=T2,
    )
    assert res.records[0].identity.status == IdentityStatus.UNRESOLVED


def test_no_name_matching():
    # Alias covers symbol "OLD" for INST-1 with name "Example Holdings Inc"
    alias = _make_alias(symbol="OLD", instrument_id="INST-1")
    # Normalized record has symbol "NEW" but identical name
    norm_rec = NasdaqNormalizedRecord(
        symbol="NEW",
        security_name="Example Holdings Inc",
        market_category="Q",
        test_issue=False,
        financial_status="N",
        round_lot_size=100,
        is_etf=False,
        is_nextshares=False,
    )
    file_single = NasdaqNormalizedFile(records=(norm_rec,), file_creation_time_raw="0911202612:11")

    res = resolve_nasdaq_identities(
        file_single,
        aliases=[alias],
        effective_time=T0,
        query_time=T0,
    )
    # Must be UNRESOLVED; name matching is forbidden
    assert res.records[0].identity.status == IdentityStatus.UNRESOLVED


def test_no_corporate_action_inferred():
    from app.domain.models import CorporateAction

    alias = _make_alias(symbol="AAPL", instrument_id="inst-apple")
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    res_file = resolve_nasdaq_identities(
        norm_file,
        aliases=[alias],
        effective_time=T0,
        query_time=T0,
    )
    for ir in res_file.records:
        assert not isinstance(ir, CorporateAction)
        assert not isinstance(ir.identity, CorporateAction)


def test_no_symbol_alias_created():
    aliases = [_make_alias(symbol="AAPL", instrument_id="inst-apple")]
    aliases_count_before = len(aliases)
    norm_file = normalize_nasdaqlisted(parse_nasdaqlisted(_read_fixture("nasdaqlisted_valid.txt")))
    resolve_nasdaq_identities(
        norm_file,
        aliases=aliases,
        effective_time=T0,
        query_time=T0,
    )
    assert len(aliases) == aliases_count_before
