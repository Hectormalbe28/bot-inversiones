"""S2.11B - RawIngestionStore: acceptance tests.

Tests for RawIngestionStore and save_raw_ingestion(), which:
- Writes raw bytes to content-addressed filesystem storage:
      <raw_root>/<provider>/<feed>/<sha256>.raw
- Inserts a provenance record into source_ingestions (idempotent).
- Idempotency key: (provider, feed, source_name, sha256)
- Computes SHA256 internally (never from caller).
- Returns RawIngestionResult with ingestion_id.
"""

import hashlib
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.infrastructure.storage.raw import RawIngestionResult, RawIngestionStore, save_raw_ingestion
from app.infrastructure.storage.sqlite import SQLiteStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_UTC = UTC
_T_SRC = datetime(2024, 1, 14, 20, 0, 0, tzinfo=_UTC)
_T_RECV = datetime(2024, 1, 14, 22, 0, 0, tzinfo=_UTC)
_T_PROC = datetime(2024, 1, 14, 22, 5, 0, tzinfo=_UTC)
_T_AVAIL = datetime(2024, 1, 15, 0, 0, 0, tzinfo=_UTC)

_PROVIDER = "nasdaq"
_FEED = "symbol_directory"
_SOURCE_NAME = "nasdaqlisted.txt"
_RAW_CONTENT = b"Symbol|Security Name\nAAPL|Apple Inc\n"

# ---------------------------------------------------------------------------
# Fixtures - using explicit mkdtemp to avoid Windows tmp_path permission issue
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_env():
    """Creates raw_root dir and initialised SQLite DB using explicit tempfile."""
    with tempfile.TemporaryDirectory() as base:
        base_path = Path(base)
        raw_root = base_path / "raw"
        raw_root.mkdir()
        db_path = base_path / "test.db"
        sqlite_store = SQLiteStore(db_path)
        sqlite_store.initialize()
        raw_store = RawIngestionStore(raw_root=raw_root, sqlite_store=sqlite_store)
        yield raw_root, db_path, sqlite_store, raw_store


def _save(
    raw_store,
    raw=_RAW_CONTENT,
    source_name=_SOURCE_NAME,
    source_timestamp=_T_SRC,
    record_count=1,
    status="SUCCESS",
):
    return save_raw_ingestion(
        store=raw_store,
        raw=raw,
        provider=_PROVIDER,
        feed=_FEED,
        source_name=source_name,
        source_timestamp=source_timestamp,
        received_at=_T_RECV,
        processed_at=_T_PROC,
        available_at=_T_AVAIL,
        record_count=record_count,
        status=status,
    )


# ---------------------------------------------------------------------------
# RawIngestionResult structure
# ---------------------------------------------------------------------------


def test_result_has_ingestion_id(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    assert result.ingestion_id is not None
    assert isinstance(result.ingestion_id, str)
    assert len(result.ingestion_id) > 0


def test_result_ingestion_id_is_valid_uuid(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    parsed = uuid.UUID(result.ingestion_id)
    assert parsed.version == 4


def test_result_has_sha256(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    expected = hashlib.sha256(_RAW_CONTENT).hexdigest()
    assert result.sha256 == expected


def test_result_sha256_is_64_hex_chars(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    assert len(result.sha256) == 64
    assert all(c in "0123456789abcdef" for c in result.sha256)


def test_result_raw_path_is_set(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    assert result.raw_path is not None
    assert isinstance(result.raw_path, str)
    assert len(result.raw_path) > 0


# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------


def test_raw_file_created_at_expected_path(store_env):
    raw_root, _, _, raw_store = store_env
    result = _save(raw_store)
    expected_path = raw_root / _PROVIDER / _FEED / f"{result.sha256}.raw"
    assert expected_path.exists()


def test_raw_file_content_matches_input(store_env):
    raw_root, _, _, raw_store = store_env
    result = _save(raw_store)
    expected_path = raw_root / _PROVIDER / _FEED / f"{result.sha256}.raw"
    assert expected_path.read_bytes() == _RAW_CONTENT


def test_raw_path_in_result_matches_filesystem_path(store_env):
    raw_root, _, _, raw_store = store_env
    result = _save(raw_store)
    expected_path = raw_root / _PROVIDER / _FEED / f"{result.sha256}.raw"
    assert result.raw_path == str(expected_path)


# ---------------------------------------------------------------------------
# Database record
# ---------------------------------------------------------------------------


def test_db_record_inserted(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row is not None


def test_db_record_provider_and_feed(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["provider"] == _PROVIDER
    assert row["feed"] == _FEED


def test_db_record_source_name(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["source_name"] == _SOURCE_NAME


def test_db_record_sha256(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["sha256"] == result.sha256


def test_db_record_status_success(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store, status="SUCCESS")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["status"] == "SUCCESS"


def test_db_record_status_pending(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store, status="PENDING")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["status"] == "PENDING"


def test_db_record_record_count(store_env):
    _, db_path, _, raw_store = store_env
    result = _save(raw_store, record_count=42)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM source_ingestions WHERE ingestion_id = ?", (result.ingestion_id,)
    ).fetchone()
    conn.close()
    assert row["record_count"] == 42


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_second_call_returns_same_ingestion_id(store_env):
    _, _, _, raw_store = store_env
    r1 = _save(raw_store)
    r2 = _save(raw_store)
    assert r1.ingestion_id == r2.ingestion_id


def test_idempotent_second_call_same_sha256(store_env):
    _, _, _, raw_store = store_env
    r1 = _save(raw_store)
    r2 = _save(raw_store)
    assert r1.sha256 == r2.sha256


def test_idempotent_only_one_db_row(store_env):
    _, db_path, _, raw_store = store_env
    for _ in range(3):
        _save(raw_store)
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM source_ingestions").fetchone()[0]
    conn.close()
    assert count == 1


def test_different_source_name_same_content_creates_new_row(store_env):
    _, db_path, _, raw_store = store_env
    r1 = _save(raw_store, source_name="file_a.txt")
    r2 = _save(raw_store, source_name="file_b.txt")
    assert r1.ingestion_id != r2.ingestion_id


def test_different_content_creates_new_row(store_env):
    _, db_path, _, raw_store = store_env
    r1 = save_raw_ingestion(
        store=raw_store,
        raw=b"content_a",
        provider=_PROVIDER,
        feed=_FEED,
        source_name=_SOURCE_NAME,
        source_timestamp=_T_SRC,
        received_at=_T_RECV,
        processed_at=_T_PROC,
        available_at=_T_AVAIL,
        record_count=1,
        status="SUCCESS",
    )
    r2 = save_raw_ingestion(
        store=raw_store,
        raw=b"content_b",
        provider=_PROVIDER,
        feed=_FEED,
        source_name=_SOURCE_NAME,
        source_timestamp=_T_SRC,
        received_at=_T_RECV,
        processed_at=_T_PROC,
        available_at=_T_AVAIL,
        record_count=1,
        status="SUCCESS",
    )
    assert r1.ingestion_id != r2.ingestion_id
    assert r1.sha256 != r2.sha256


# ---------------------------------------------------------------------------
# Temporal validation
# ---------------------------------------------------------------------------


def test_naive_received_at_raises(store_env):
    _, _, _, raw_store = store_env
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=_T_SRC,
            received_at=datetime(2024, 1, 14, 22, 0, 0),  # naive
            processed_at=_T_PROC,
            available_at=_T_AVAIL,
            record_count=1,
            status="SUCCESS",
        )


def test_naive_available_at_raises(store_env):
    _, _, _, raw_store = store_env
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=_T_SRC,
            received_at=_T_RECV,
            processed_at=_T_PROC,
            available_at=datetime(2024, 1, 15, 0, 0, 0),  # naive
            record_count=1,
            status="SUCCESS",
        )


def test_processed_after_available_raises(store_env):
    _, _, _, raw_store = store_env
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=_T_SRC,
            received_at=_T_RECV,
            processed_at=_T_AVAIL,
            available_at=_T_PROC,  # available before processed
            record_count=1,
            status="SUCCESS",
        )


def test_received_after_processed_raises(store_env):
    _, _, _, raw_store = store_env
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=_T_SRC,
            received_at=_T_PROC,  # received after processed
            processed_at=_T_RECV,
            available_at=_T_AVAIL,
            record_count=1,
            status="SUCCESS",
        )


def test_source_timestamp_after_available_raises(store_env):
    _, _, _, raw_store = store_env
    future = datetime(2025, 1, 1, tzinfo=_UTC)
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=future,
            received_at=_T_RECV,
            processed_at=_T_PROC,
            available_at=_T_AVAIL,
            record_count=1,
            status="SUCCESS",
        )


# ---------------------------------------------------------------------------
# Invalid status
# ---------------------------------------------------------------------------


def test_invalid_status_raises(store_env):
    _, _, _, raw_store = store_env
    with pytest.raises(ValueError):
        save_raw_ingestion(
            store=raw_store,
            raw=_RAW_CONTENT,
            provider=_PROVIDER,
            feed=_FEED,
            source_name=_SOURCE_NAME,
            source_timestamp=_T_SRC,
            received_at=_T_RECV,
            processed_at=_T_PROC,
            available_at=_T_AVAIL,
            record_count=1,
            status="INVALID_STATUS",
        )


# ---------------------------------------------------------------------------
# RawIngestionStore class interface
# ---------------------------------------------------------------------------


def test_raw_ingestion_store_is_constructible(store_env):
    raw_root, _, sqlite_store, _ = store_env
    ris = RawIngestionStore(raw_root=raw_root, sqlite_store=sqlite_store)
    assert ris is not None


def test_save_raw_ingestion_module_level_function():
    from app.infrastructure.storage import raw as raw_module

    assert hasattr(raw_module, "save_raw_ingestion")
    assert callable(raw_module.save_raw_ingestion)


def test_result_is_a_dataclass(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    assert isinstance(result, RawIngestionResult)


def test_result_is_immutable(store_env):
    _, _, _, raw_store = store_env
    result = _save(raw_store)
    with pytest.raises((AttributeError, TypeError)):
        result.ingestion_id = "other"  # type: ignore[misc]
