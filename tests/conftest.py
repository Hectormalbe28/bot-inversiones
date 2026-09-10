from datetime import UTC, datetime

import pytest


@pytest.fixture
def evidence():
    instant = datetime(2026, 9, 1, 20, tzinfo=UTC)
    return dict(
        event_time=instant,
        source_timestamp=instant,
        received_at=instant,
        processed_at=instant,
        available_at=instant,
        provider="fixture",
        feed="test",
        version=1,
    )


@pytest.fixture
def settings(tmp_path):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        artifact_dir=tmp_path / "artifacts",
        log_dir=tmp_path / "logs",
    )
