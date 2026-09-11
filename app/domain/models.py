from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.clock import require_utc

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Symbol = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9.\-/^]*$")]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TemporalEvidence(Contract):
    event_time: datetime
    published_at: datetime | None = None
    source_timestamp: datetime
    received_at: datetime
    processed_at: datetime
    available_at: datetime
    provider: Identifier
    feed: Identifier
    version: int = Field(ge=1)

    @field_validator(
        "event_time",
        "published_at",
        "source_timestamp",
        "received_at",
        "processed_at",
        "available_at",
    )
    @classmethod
    def normalize_utc(cls, value: datetime | None):
        return None if value is None else require_utc(value)

    @model_validator(mode="after")
    def validate_availability(self):
        if not self.received_at <= self.processed_at <= self.available_at:
            raise ValueError("Require received_at <= processed_at <= available_at")
        for value in (self.source_timestamp, self.published_at):
            if value is not None and value > self.available_at:
                raise ValueError(
                    "Evidence cannot be available before its source or publication time"
                )
        return self


class Instrument(TemporalEvidence):
    instrument_id: Identifier
    symbol: Symbol
    name: Annotated[str, Field(min_length=1)]
    exchange: str | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    asset_class: Literal["equity", "etf"] = "equity"
    active: bool = True
    cik: str | None = None


class MarketObservation(TemporalEvidence):
    @model_validator(mode="after")
    def validate_observation_time(self):
        if self.event_time > self.available_at:
            raise ValueError("Market observation cannot be available before its event time")
        return self


class CanonicalBar(MarketObservation):
    symbol: Symbol
    timeframe: Literal["1m", "5m", "15m", "1h", "1d"]
    open: NonNegative
    high: NonNegative
    low: NonNegative
    close: NonNegative
    volume: NonNegative
    vwap: NonNegative | None = None
    trade_count: Annotated[int, Field(ge=0)] | None = None
    adjustment_policy: Literal["raw", "split_adjusted", "total_return"] = "raw"

    @model_validator(mode="after")
    def consistent_ohlc(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("Inconsistent OHLC range")
        return self


class CanonicalQuote(MarketObservation):
    symbol: Symbol
    bid: NonNegative
    ask: NonNegative
    bid_size: NonNegative | None = None
    ask_size: NonNegative | None = None

    @model_validator(mode="after")
    def uncrossed(self):
        if self.ask < self.bid:
            raise ValueError("Crossed quote must be quarantined by the provider normalizer")
        return self

    @property
    def spread(self) -> float:
        return self.ask - self.bid


class CanonicalTrade(MarketObservation):
    symbol: Symbol
    trade_id: Identifier
    price: NonNegative
    size: NonNegative


class ActualityEvent(TemporalEvidence):
    event_id: Identifier
    source_type: Literal["official", "news", "social", "product", "regulatory"]
    source_trust: Literal["A", "B", "C", "D"]
    title: str
    text_excerpt: str | None = None
    url: str | None = None
    event_type: str
    entities: tuple[str, ...] = ()
    symbols: tuple[Symbol, ...] = ()
    sectors: tuple[str, ...] = ()
    novelty: Annotated[float, Field(ge=0, le=1)] | None = None
    relevance: Annotated[float, Field(ge=0, le=1)] | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class ScheduledEvent(TemporalEvidence):
    event_id: Identifier
    event_type: str
    symbol: Symbol | None = None
    scheduled_at: datetime
    importance: int = Field(ge=1, le=5)
    status: Literal["scheduled", "near", "active", "released", "cancelled"] = "scheduled"
    expected_value: float | None = None
    previous_value: float | None = None

    @field_validator("scheduled_at")
    @classmethod
    def schedule_utc(cls, value):
        return require_utc(value)


class Capability(Contract):
    name: str
    required: bool
    status: Literal["AVAILABLE", "DEGRADED", "DISABLED", "DOWN"]
    version: str | None = None
    latency_ms: NonNegative | None = None
    reason: str | None = None
    checked_at: datetime


class ProviderStatus(Contract):
    provider: str
    tier: str
    feed: str
    enabled: bool = False
    status: Literal["AVAILABLE", "DEGRADED", "DISABLED", "DOWN"] = "DISABLED"
    last_success: datetime | None = None
    latency_ms: NonNegative | None = None
    quota_remaining: Annotated[int, Field(ge=0)] | None = None
    reason: str = "Adapter pending implementation; no connection attempted"

    @computed_field
    @property
    def health(self) -> str:
        return self.status
