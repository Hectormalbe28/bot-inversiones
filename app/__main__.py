import sys

import uvicorn

from app.cli import refresh_nasdaq_universe, run_universe_show
from app.core.clock import utc_now
from app.core.config import Settings
from app.infrastructure.bootstrap import bootstrap
from app.infrastructure.providers.nasdaq_ingestion import NasdaqUniverseIngestionService
from app.infrastructure.providers.nasdaq_transport import NasdaqSymbolDirectoryHttpClient
from app.infrastructure.storage.raw import RawIngestionStore
from app.infrastructure.storage.sqlite import (
    SQLiteHistoricalUniverseWriteRepository,
    SQLiteIngestionResultRepository,
    SQLiteInstrumentVersionRepository,
    SQLiteSymbolAliasRepository,
)
from app.main import create_app


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:2] == ["universe", "show"]:
        settings = Settings()
        runtime = bootstrap(settings)
        return run_universe_show(
            args[2:], repository_factory=lambda: runtime.universes, output=sys.stdout
        )
    if args[:2] == ["universe", "refresh"]:
        if len(args) != 6 or args[2] != "--effective-time" or args[4] != "--source-timestamp":
            print(
                "Usage: python -m app universe refresh --effective-time ISO-8601 "
                "--source-timestamp ISO-8601"
            )
            return 2
        settings = Settings()
        runtime = bootstrap(settings)
        ingestor = NasdaqUniverseIngestionService(
            raw_store=RawIngestionStore(
                raw_root=settings.data_dir / "raw", sqlite_store=runtime.store
            ),
            aliases=SQLiteSymbolAliasRepository(runtime.store),
            instrument_versions=SQLiteInstrumentVersionRepository(runtime.store),
            universe_writer=SQLiteHistoricalUniverseWriteRepository(runtime.store),
            results=SQLiteIngestionResultRepository(runtime.store),
        )
        try:
            return refresh_nasdaq_universe(
                effective_time=args[3],
                source_timestamp=args[5],
                downloader=NasdaqSymbolDirectoryHttpClient(),
                ingestor=ingestor,
                clock=utc_now,
                output=sys.stdout,
            )
        except ValueError as exc:
            print(f"Invalid refresh request: {exc}")
            return 2
    if args:
        print(
            "Usage: python -m app [universe show --provider PROVIDER --feed FEED --as-of ISO-8601]"
        )
        return 2
    settings = Settings()
    uvicorn.run(
        create_app(settings), host=settings.app_host, port=settings.app_port, access_log=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
