from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.domain.models import CanonicalDailyBar


def _bar(**overrides):
    values = {
        "instrument_id": "inst-aapl",
        "symbol": "AAPL",
        "session_date": date(2026, 10, 20),
        "event_time": datetime(2026, 10, 20, 20, 0, tzinfo=UTC),
        "source_timestamp": datetime(2026, 10, 20, 20, 1, tzinfo=UTC),
        "received_at": datetime(2026, 10, 21, 14, 0, tzinfo=UTC),
        "processed_at": datetime(2026, 10, 21, 14, 0, 1, tzinfo=UTC),
        "available_at": datetime(2026, 10, 21, 14, 0, 2, tzinfo=UTC),
        "provider": "massive",
        "feed": "grouped_daily",
        "version": 1,
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 1_000_000.0,
        "vwap": 103.5,
        "trade_count": 12345,
        "adjustment_policy": "raw",
        "otc": False,
    }
    values.update(overrides)
    return CanonicalDailyBar(**values)


def test_daily_bar_requires_stable_instrument_identity():
    bar = _bar()
    assert bar.instrument_id == "inst-aapl"
    assert bar.symbol == "AAPL"
    assert bar.timeframe == "1d"


def test_daily_bar_is_raw_only_in_sprint_3():
    with pytest.raises(ValidationError):
        _bar(adjustment_policy="split_adjusted")


def test_daily_bar_keeps_real_ingestion_availability():
    bar = _bar()
    assert bar.available_at == datetime(2026, 10, 21, 14, 0, 2, tzinfo=UTC)
    assert bar.event_time < bar.available_at


def test_daily_bar_rejects_inconsistent_ohlc():
    with pytest.raises(ValidationError):
        _bar(high=99.0)


def test_daily_bar_rejects_non_daily_timeframe():
    with pytest.raises(ValidationError):
        _bar(timeframe="5m")
