from datetime import UTC, date, datetime

from app.application.replay import (
    EOD_NEXT_CALENDAR_DAY_NY_V1,
    derive_replay_availability,
)


def test_replay_policy_identity_is_versioned():
    policy = EOD_NEXT_CALENDAR_DAY_NY_V1
    assert policy.policy_id == "eod-next-calendar-day-ny"
    assert policy.version == 1


def test_winter_session_becomes_available_at_next_new_york_midnight():
    result = derive_replay_availability(date(2026, 1, 2), EOD_NEXT_CALENDAR_DAY_NY_V1)
    assert result.replay_available_at == datetime(2026, 1, 3, 5, 0, tzinfo=UTC)


def test_summer_session_respects_dst():
    result = derive_replay_availability(date(2026, 7, 2), EOD_NEXT_CALENDAR_DAY_NY_V1)
    assert result.replay_available_at == datetime(2026, 7, 3, 4, 0, tzinfo=UTC)


def test_replay_availability_is_explicitly_derived_metadata():
    result = derive_replay_availability(date(2026, 10, 20), EOD_NEXT_CALENDAR_DAY_NY_V1)
    assert result.provenance == "derived"
    assert result.policy_id == EOD_NEXT_CALENDAR_DAY_NY_V1.policy_id
    assert result.policy_version == EOD_NEXT_CALENDAR_DAY_NY_V1.version
