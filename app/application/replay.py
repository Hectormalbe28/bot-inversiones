from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from app.domain.models import Contract, Identifier


class ReplayAvailabilityPolicy(Contract):
    """Versioned rule for reconstructing conservative EOD replay availability.

    This policy never rewrites real ingestion timestamps. It only produces
    derived metadata for historical EOD replay.
    """

    policy_id: Identifier
    version: int = Field(ge=1)
    timezone: str


class ReplayAvailability(Contract):
    policy_id: Identifier
    policy_version: int = Field(ge=1)
    replay_available_at: datetime
    provenance: Literal["derived"] = "derived"


EOD_NEXT_CALENDAR_DAY_NY_V1 = ReplayAvailabilityPolicy(
    policy_id="eod-next-calendar-day-ny",
    version=1,
    timezone="America/New_York",
)


def derive_replay_availability(
    session_date: date,
    policy: ReplayAvailabilityPolicy,
) -> ReplayAvailability:
    """Return next-calendar-day midnight in the policy timezone, normalized to UTC."""

    local_zone = ZoneInfo(policy.timezone)
    next_day = session_date + timedelta(days=1)
    local_midnight = datetime.combine(next_day, time.min, tzinfo=local_zone)

    return ReplayAvailability(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        replay_available_at=local_midnight.astimezone(UTC),
    )
