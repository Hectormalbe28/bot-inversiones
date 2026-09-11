from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.models import CanonicalBar, CanonicalQuote, CanonicalTrade, Instrument
from app.infrastructure.storage.sqlite import InstrumentRepository, SQLiteStore
from app.main import create_app


def test_bootstrap_offline_and_api(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        health = client.get("/v1/system/health").json()
        assert health["status"] == "AVAILABLE"
        assert health["live_trading_enabled"] is False
        capabilities = {c["name"]: c for c in health["capabilities"]}
        for name in ("sqlite", "fts5", "duckdb", "parquet", "clock"):
            assert capabilities[name]["status"] == "AVAILABLE"
        assert all(p["status"] == "DISABLED" for p in client.get("/v1/system/providers").json())
        assert client.get("/readyz").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert not any("order" in p or "trade" in p for p in paths)


@pytest.mark.parametrize("flag", ["live_trading_enabled", "live_approved_default"])
def test_live_flags_cannot_be_enabled(flag):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{flag: True})


def test_migrations_idempotent_and_tampering_detected(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    store.initialize()
    with store.connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2
        conn.execute(
            "INSERT INTO knowledge_index(source_id, title, body) VALUES ('1','UTC','replay')"
        )
        assert (
            conn.execute(
                "SELECT source_id FROM knowledge_index WHERE knowledge_index MATCH 'replay'"
            ).fetchone()[0]
            == "1"
        )
        conn.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(RuntimeError, match="checksum"):
        store.initialize()


def test_revision_point_in_time_and_restart(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)
    t0 = evidence["event_time"]
    first = Instrument(instrument_id="test-1", symbol="ABC", name="Before", **evidence)
    assert repo.save(first) is True
    assert repo.save(first) is False
    second = first.model_dump() | {
        "name": "After",
        "version": 2,
        "received_at": t0 + timedelta(days=1),
        "processed_at": t0 + timedelta(days=1),
        "available_at": t0 + timedelta(days=1),
    }
    repo.save(Instrument(**second))
    reopened = SQLiteStore(settings.database_path)
    reopened.initialize()
    repo = InstrumentRepository(reopened)
    assert repo.get_as_of("ABC", t0 - timedelta(seconds=1)) is None
    assert repo.get_as_of("ABC", t0).name == "Before"
    assert repo.get_as_of("ABC", t0 + timedelta(days=1)).name == "After"
    with pytest.raises(ValueError, match="conflict"):
        repo.save(Instrument(**(first.model_dump() | {"name": "overwrite"})))
    with pytest.raises(ValueError, match="timezone"):
        repo.get_as_of("ABC", datetime(2026, 9, 1))
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/instruments/ABC").status_code == 422
        assert (
            client.get("/v1/instruments/ABC", params={"as_of": "2026-09-01T20:00:00"}).status_code
            == 422
        )
        response = client.get("/v1/instruments/ABC", params={"as_of": t0.isoformat()})
        assert response.json()["name"] == "Before"
        assert (
            client.get("/v1/instruments/XYZ", params={"as_of": t0.isoformat()}).status_code == 404
        )


def test_symbol_change_does_not_resurrect_old_alias(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)
    old = Instrument(instrument_id="stable-id", symbol="OLD", name="Company", **evidence)
    repo.save(old)
    later = evidence["available_at"] + timedelta(days=1)
    new = old.model_dump() | {
        "symbol": "NEW",
        "version": 2,
        "event_time": later,
        "source_timestamp": later,
        "received_at": later,
        "processed_at": later,
        "available_at": later,
    }
    repo.save(Instrument(**new))
    assert repo.get_as_of("OLD", later) is None
    assert repo.get_as_of("NEW", later).instrument_id == "stable-id"


@pytest.mark.parametrize("field", ["event_time", "source_timestamp", "received_at", "available_at"])
def test_naive_timestamps_rejected(field, evidence):
    with pytest.raises(ValidationError):
        Instrument(
            instrument_id="1", symbol="A", name="A", **(evidence | {field: datetime(2026, 1, 1)})
        )


def test_temporal_order_and_utc(evidence):
    with pytest.raises(ValidationError):
        Instrument(
            instrument_id="1",
            symbol="A",
            name="A",
            **(evidence | {"available_at": evidence["received_at"] - timedelta(seconds=1)}),
        )
    data = evidence | {"event_time": "2026-09-01T15:00:00-05:00"}
    assert Instrument(instrument_id="1", symbol="A", name="A", **data).event_time.tzinfo == UTC


@pytest.mark.parametrize(
    "changes",
    [
        {"high": 9},
        {"low": 11},
        {"volume": -1},
        {"open": float("nan")},
        {"close": float("inf")},
        {"trade_count": -1},
        {"close": -1},
    ],
)
def test_bad_bars_rejected(changes, evidence):
    bar = dict(symbol="A", timeframe="1d", open=10, high=12, low=9, close=11, volume=100)
    with pytest.raises(ValidationError):
        CanonicalBar(**(bar | evidence | changes))


@given(
    bid=st.floats(min_value=0.01, max_value=100000, allow_nan=False, allow_infinity=False),
    spread=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
def test_quote_spread_property(bid, spread):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    quote = CanonicalQuote(
        symbol="TEST",
        bid=bid,
        ask=bid + spread,
        provider="fixture",
        feed="iex",
        version=1,
        event_time=now,
        source_timestamp=now,
        received_at=now,
        processed_at=now,
        available_at=now,
    )
    assert quote.spread >= 0


def test_crossed_quote_and_negative_trade(evidence):
    with pytest.raises(ValidationError):
        CanonicalQuote(symbol="A", bid=11, ask=10, **evidence)
    with pytest.raises(ValidationError):
        CanonicalTrade(symbol="A", trade_id="1", price=10, size=-1, **evidence)


def test_required_storage_failure_blocks_startup(settings):
    settings.data_dir.parent.mkdir(exist_ok=True, parents=True)
    settings.data_dir.write_text("not a directory", encoding="utf-8")
    with pytest.raises(OSError), TestClient(create_app(settings)):
        pass


def test_readiness_detects_database_failure(settings, monkeypatch):
    app = create_app(settings)
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.runtime.store, "probe", lambda: (_ for _ in ()).throw(OSError())
        )
        assert client.get("/readyz").status_code == 503
        assert client.get("/healthz").status_code == 200
