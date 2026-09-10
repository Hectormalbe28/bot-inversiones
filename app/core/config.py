from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

    app_env: Literal["local", "test"] = "local"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path = Path("data")
    artifact_dir: Path = Path("artifacts")
    log_dir: Path = Path("logs")
    tz: Literal["UTC"] = "UTC"
    ai_enabled: bool = False
    live_trading_enabled: bool = False
    live_approved_default: bool = False
    paper_broker_enabled: bool = False
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    alpaca_feed: Literal["iex", "sip"] = "iex"
    alpaca_tier: Literal["basic", "plus"] = "basic"
    massive_tier: Literal["basic", "advanced"] = "basic"

    @model_validator(mode="after")
    def enforce_stage_scope(self):
        if self.live_trading_enabled or self.live_approved_default:
            raise ValueError("Live trading is unavailable in this research application")
        if self.paper_broker_enabled:
            raise ValueError("Paper broker is not implemented in Sprint 1")
        if self.alpaca_feed == "sip" and self.alpaca_tier == "basic":
            raise ValueError("SIP requires an explicit non-basic entitlement")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "metadata.sqlite3"
