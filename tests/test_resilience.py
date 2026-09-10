import json
import logging
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.application.registry import ProviderRegistry
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.domain.models import ActualityEvent, Instrument, ProviderStatus, ScheduledEvent
from app.infrastructure.storage.sqlite import InstrumentRepository, SQLiteStore
from app.main import create_app


def test_optional_ai_request_does_not_block_core(settings):
    config = Settings(**(settings.model_dump() | {"ai_enabled": True}), _env_file=None)
    with TestClient(create_app(config)) as client:
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "DEGRADED"
        providers = {p["provider"]: p for p in client.get("/v1/system/providers").json()}
        assert providers["ai"]["last_success"] is None
        assert providers["ai"]["status"] == "DEGRADED"


def test_settings_env_and_entitlement(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, alpaca_feed="sip", alpaca_tier="basic")


def test_events_distinguish_announcement_and_future_schedule(evidence):
    scheduled = ScheduledEvent(
        **evidence,
        event_id="earnings-1",
        event_type="earnings",
        importance=3,
        scheduled_at=evidence["event_time"] + timedelta(days=10),
    )
    assert scheduled.scheduled_at > scheduled.available_at
    with pytest.raises(ValidationError):
        ActualityEvent(
            **evidence,
            event_id="news-1",
            event_type="filing",
            source_type="official",
            source_trust="A",
            title="Release",
            confidence=1.1,
        )


def test_registry_rejects_duplicate_providers():
    provider = ProviderStatus(provider="x", tier="test", feed="test")
    with pytest.raises(ValueError, match="Duplicate"):
        ProviderRegistry((provider, provider))


def test_future_schema_rejected(settings):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    with store.connection() as conn:
        conn.execute("INSERT INTO schema_migrations VALUES ('999_future.sql', 'x', 'x')")
    with pytest.raises(RuntimeError, match="newer"):
        store.initialize()


def test_failed_migration_is_atomic(settings, tmp_path, monkeypatch):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_bad.sql").write_text(
        "CREATE TABLE partial (id INTEGER);\nINVALID SQL;\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.infrastructure.storage.sqlite.files", lambda _: migration_dir)
    store = SQLiteStore(settings.database_path)
    with pytest.raises(sqlite3.OperationalError):
        store.initialize()
    with store.connection() as conn:
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('partial', 'schema_migrations')"
            ).fetchall()
            == []
        )


def test_ambiguous_provenance_is_not_silently_merged(settings, evidence):
    store = SQLiteStore(settings.database_path)
    store.initialize()
    repo = InstrumentRepository(store)
    instrument = Instrument(instrument_id="id", symbol="ABC", name="Example", **evidence)
    repo.save(instrument)
    repo.save(Instrument(**(instrument.model_dump() | {"provider": "another"})))
    with TestClient(create_app(settings)) as client:
        assert (
            client.get(
                "/v1/instruments/ABC", params={"as_of": evidence["available_at"].isoformat()}
            ).status_code
            == 409
        )


def test_request_logs_and_errors_do_not_expose_query_or_exception(settings, capsys, monkeypatch):
    app = create_app(settings)
    with TestClient(app) as client:

        def broken_probe():
            raise RuntimeError("SECRET_TEST_KEY")

        monkeypatch.setattr(app.state.runtime.providers, "list", broken_probe)
        response = client.get("/v1/system/providers?token=SECRET_TEST_KEY")
        assert response.status_code == 500
        assert "SECRET_TEST_KEY" not in response.text
        assert response.headers["X-Request-ID"] == response.json()["request_id"]
    assert "SECRET_TEST_KEY" not in capsys.readouterr().err
    record = logging.LogRecord("bot_inversiones", logging.INFO, "", 0, "test_event", (), None)
    assert json.loads(JsonFormatter().format(record))["event"] == "test_event"
