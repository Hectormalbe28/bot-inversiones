import importlib.metadata
import sqlite3
import tempfile
from dataclasses import dataclass
from time import perf_counter

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from app.application.registry import ProviderRegistry
from app.core.clock import utc_now
from app.core.config import Settings
from app.domain.models import Capability, ProviderStatus
from app.infrastructure.storage.sqlite import InstrumentRepository, SQLiteStore


@dataclass
class Runtime:
    store: SQLiteStore
    instruments: InstrumentRepository
    providers: ProviderRegistry
    capabilities: tuple[Capability, ...]

    def health(self) -> tuple[str, tuple[Capability, ...]]:
        capabilities = list(self.capabilities)
        started = perf_counter()
        try:
            self.store.probe()
            status, reason = "AVAILABLE", None
        except (OSError, sqlite3.Error, RuntimeError) as exc:
            status, reason = "DOWN", type(exc).__name__
        for index, capability in enumerate(capabilities):
            if capability.name in {"sqlite", "fts5"}:
                capabilities[index] = capability.model_copy(
                    update={
                        "status": status,
                        "reason": reason,
                        "checked_at": utc_now(),
                        "latency_ms": (perf_counter() - started) * 1000,
                    }
                )
        overall = "AVAILABLE"
        if any(c.required and c.status != "AVAILABLE" for c in capabilities):
            overall = "DOWN"
        elif any(c.status in {"DEGRADED", "DOWN"} for c in capabilities):
            overall = "DEGRADED"
        return overall, tuple(capabilities)


def bootstrap(settings: Settings) -> Runtime:
    capabilities = []

    def available(name, started, version=None):
        capabilities.append(
            Capability(
                name=name,
                required=True,
                status="AVAILABLE",
                version=version,
                latency_ms=(perf_counter() - started) * 1000,
                checked_at=utc_now(),
            )
        )

    started = perf_counter()
    for path in (settings.data_dir, settings.artifact_dir, settings.log_dir):
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path) as probe:
            probe.write(b"probe")
            probe.flush()
    available("directories", started)
    started = perf_counter()
    store = SQLiteStore(settings.database_path, settings.sqlite_busy_timeout_ms)
    store.initialize()
    store.probe()
    available("sqlite", started, sqlite3.sqlite_version)
    available("fts5", started, sqlite3.sqlite_version)

    started = perf_counter()
    parquet_path = settings.data_dir / "market" / "daily"
    parquet_path.mkdir(parents=True, exist_ok=True)
    # An isolated roundtrip verifies storage and query engines without seeding market data.
    with tempfile.TemporaryDirectory(prefix="bootstrap-", dir=parquet_path) as directory:
        from pathlib import Path

        probe_path = Path(directory) / "probe.parquet"
        pq.write_table(pa.table({"value": [1, 2, 3]}), probe_path, compression="zstd")
        if pq.read_table(probe_path).column("value").to_pylist() != [1, 2, 3]:
            raise RuntimeError("Parquet roundtrip failed")
        available("parquet", started, pa.__version__)
        started = perf_counter()
        with duckdb.connect(":memory:") as connection:
            result = connection.execute(
                "SELECT sum(value) FROM read_parquet(?)", [str(probe_path)]
            ).fetchone()
            if result != (6,):
                raise RuntimeError("DuckDB Parquet query failed")
        available("duckdb", started, importlib.metadata.version("duckdb"))
    available("clock", perf_counter(), "UTC")

    providers = ProviderRegistry(
        (
            ProviderStatus(provider="nasdaq", tier="public", feed="symbol_directory"),
            ProviderStatus(provider="alpaca", tier=settings.alpaca_tier, feed=settings.alpaca_feed),
            ProviderStatus(provider="massive", tier=settings.massive_tier, feed="eod"),
            ProviderStatus(provider="sec", tier="public", feed="edgar"),
            ProviderStatus(provider="fred", tier="public", feed="macro"),
            ProviderStatus(provider="bls", tier="public", feed="macro"),
            ProviderStatus(provider="alpha_vantage", tier="free", feed="earnings"),
            ProviderStatus(provider="gdelt", tier="public", feed="news"),
            ProviderStatus(
                provider="ai",
                tier="unconfigured",
                feed="research",
                enabled=settings.ai_enabled,
                status="DEGRADED" if settings.ai_enabled else "DISABLED",
            ),
        )
    )
    for provider in providers.list():
        capabilities.append(
            Capability(
                name=f"provider:{provider.provider}",
                required=False,
                status=provider.status,
                reason=provider.reason,
                checked_at=utc_now(),
            )
        )
    return Runtime(store, InstrumentRepository(store), providers, tuple(capabilities))
