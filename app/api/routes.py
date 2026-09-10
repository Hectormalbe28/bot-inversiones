from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AwareDatetime

from app import __version__
from app.application.ports import InstrumentStore
from app.domain.models import Instrument, ProviderStatus

router = APIRouter()


def instrument_store(request: Request) -> InstrumentStore:
    return request.app.state.runtime.instruments


@router.get("/healthz", tags=["system"])
def liveness():
    return {"status": "alive", "version": __version__}


@router.get("/v1/system/health", tags=["system"])
@router.get("/readyz", tags=["system"])
def readiness(request: Request, response: Response):
    status, capabilities = request.app.state.runtime.health()
    if status == "DOWN":
        response.status_code = 503
    return {
        "status": status,
        "version": __version__,
        "spec_version": "6.4",
        "stage": 1,
        "sprint": 1,
        "live_trading_enabled": False,
        "live_approved": False,
        "capabilities": capabilities,
    }


@router.get("/v1/system/capabilities", tags=["system"])
def capabilities(request: Request):
    return request.app.state.runtime.health()[1]


@router.get("/v1/system/providers", response_model=tuple[ProviderStatus, ...], tags=["system"])
def providers(request: Request):
    return request.app.state.runtime.providers.list()


@router.get("/v1/instruments/{symbol}", response_model=Instrument, tags=["instruments"])
def get_instrument(
    symbol: str,
    as_of: Annotated[
        AwareDatetime, Query(description="Fecha de corte con zona horaria obligatoria")
    ],
    repository: Annotated[InstrumentStore, Depends(instrument_store)],
):
    try:
        instrument = repository.get_as_of(symbol, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if instrument is None:
        raise HTTPException(
            status_code=404, detail="No instrument available at the requested as_of"
        )
    return instrument
