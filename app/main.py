import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api.routes import router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.infrastructure.bootstrap import bootstrap

logger = logging.getLogger("bot_inversiones")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = settings if settings is not None else Settings()
        configure_logging(config.log_level)
        app.state.runtime = await run_in_threadpool(bootstrap, config)
        logger.info("application_started")
        try:
            yield
        finally:
            logger.info("application_stopped")

    app = FastAPI(
        title="Bot de Inversiones",
        description="Sprint 1 — infraestructura local y contratos de datos para research.",
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed", extra={"request_id": request_id})
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal error",
                    "request_id": request_id,
                },
            )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        return response

    app.include_router(router)
    return app
