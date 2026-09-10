from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp requires an explicit timezone")
    return value.astimezone(UTC)


def utc_key(value: datetime) -> str:
    """Fixed-width keys preserve temporal ordering in SQLite TEXT comparisons."""
    return require_utc(value).isoformat(timespec="microseconds")
