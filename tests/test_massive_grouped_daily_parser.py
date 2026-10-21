import json
from datetime import UTC, date, datetime

import pytest

from app.infrastructure.providers.massive import (
    MassiveGroupedDailyNormalizationError,
    MassiveGroupedDailyParseError,
    normalize_massive_grouped_daily,
    parse_massive_grouped_daily,
)


SESSION = date(2026, 10, 20)


def _payload(results, **overrides):
    body = {
        "adjusted": False,
        "queryCount": len(results),
        "request_id": "req-123",
        "results": results,
        "resultsCount": len(results),
        "status": "OK",
    }
    body.update(overrides)
    return json.dumps(body, separators=(",", ":")).encode()


def _row(ticker="AAPL", **overrides):
    row = {
        "T": ticker,
        "o": 100.0,
        "h": 110.0,
        "l": 95.0,
        "c": 105.0,
        "v": 1_000_000.0,
        "vw": 103.5,
        "n": 12_345,
        "t": 1_792_454_400_000,
    }
    row.update(overrides)
    return row


def test_parse_clean_payload_preserves_provider_evidence():
    parsed = parse_massive_grouped_daily(_payload([_row()]), session_date=SESSION)

    assert parsed.adjusted is False
    assert parsed.request_id == "req-123"
    assert parsed.declared_results_count == 1
    assert parsed.query_count == 1
    assert parsed.session_date == SESSION
    assert parsed.records[0].symbol == "AAPL"
    assert parsed.records[0].open == 100.0
    assert parsed.records[0].source_timestamp.tzinfo == UTC


def test_adjusted_true_is_rejected_for_canonical_sprint3_path():
    with pytest.raises(MassiveGroupedDailyParseError, match="adjusted=false"):
        parse_massive_grouped_daily(
            _payload([_row()], adjusted=True),
            session_date=SESSION,
        )


def test_malformed_json_is_rejected():
    with pytest.raises(MassiveGroupedDailyParseError, match="JSON"):
        parse_massive_grouped_daily(b"{not-json", session_date=SESSION)


def test_non_ok_status_is_rejected():
    with pytest.raises(MassiveGroupedDailyParseError, match="status"):
        parse_massive_grouped_daily(
            _payload([], status="ERROR"),
            session_date=SESSION,
        )


def test_missing_required_ohlc_field_is_rejected():
    row = _row()
    del row["c"]
    with pytest.raises(MassiveGroupedDailyParseError, match="close"):
        parse_massive_grouped_daily(_payload([row]), session_date=SESSION)


def test_inconsistent_ohlc_is_rejected():
    with pytest.raises(MassiveGroupedDailyParseError, match="OHLC"):
        parse_massive_grouped_daily(
            _payload([_row(h=99.0)]),
            session_date=SESSION,
        )


def test_negative_volume_is_rejected():
    with pytest.raises(MassiveGroupedDailyParseError, match="volume"):
        parse_massive_grouped_daily(
            _payload([_row(v=-1)]),
            session_date=SESSION,
        )


def test_missing_optional_vwap_and_trade_count_are_preserved_as_none():
    row = _row()
    row.pop("vw")
    row.pop("n")
    parsed = parse_massive_grouped_daily(_payload([row]), session_date=SESSION)

    assert parsed.records[0].vwap is None
    assert parsed.records[0].trade_count is None


def test_normalization_orders_by_symbol_deterministically():
    parsed = parse_massive_grouped_daily(
        _payload([_row("MSFT"), _row("AAPL")]),
        session_date=SESSION,
    )
    normalized = normalize_massive_grouped_daily(parsed)

    assert [item.symbol for item in normalized.records] == ["AAPL", "MSFT"]


def test_identical_duplicate_ticker_is_deduplicated_deterministically():
    row = _row("AAPL")
    parsed = parse_massive_grouped_daily(
        _payload([row, dict(row)]),
        session_date=SESSION,
    )
    normalized = normalize_massive_grouped_daily(parsed)

    assert len(normalized.records) == 1
    assert normalized.duplicate_identical_count == 1


def test_divergent_duplicate_ticker_is_never_silently_selected():
    parsed = parse_massive_grouped_daily(
        _payload([_row("AAPL"), _row("AAPL", c=106.0)]),
        session_date=SESSION,
    )

    with pytest.raises(MassiveGroupedDailyNormalizationError, match="AAPL"):
        normalize_massive_grouped_daily(parsed)


def test_result_count_mismatch_is_explicit_metadata_not_silently_rewritten():
    parsed = parse_massive_grouped_daily(
        _payload([_row()], resultsCount=2),
        session_date=SESSION,
    )
    normalized = normalize_massive_grouped_daily(parsed)

    assert normalized.declared_results_count == 2
    assert normalized.parsed_results_count == 1
    assert normalized.result_count_mismatch is True


def test_otc_flag_is_preserved_when_provider_supplies_it():
    parsed = parse_massive_grouped_daily(
        _payload([_row(otc=True)]),
        session_date=SESSION,
    )
    assert parsed.records[0].otc is True


def test_normalizer_does_not_create_instrument_identity():
    parsed = parse_massive_grouped_daily(_payload([_row()]), session_date=SESSION)
    normalized = normalize_massive_grouped_daily(parsed)

    record = normalized.records[0]
    assert not hasattr(record, "instrument_id")


def test_timestamp_is_converted_from_provider_milliseconds_to_utc():
    parsed = parse_massive_grouped_daily(
        _payload([_row(t=0)]),
        session_date=SESSION,
    )
    assert parsed.records[0].source_timestamp == datetime(1970, 1, 1, tzinfo=UTC)
