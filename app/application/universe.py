"""Application-layer domain structures and exceptions for historical universe persistence.

Defines the application-level member reference pointing to existing canonical instrument
versions, and conflict exceptions for historical universe write operations.
Does not allocate identity or discover instruments.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HistoricalUniverseMemberRef:
    """Application-level reference to an existing canonical instrument version.

    Represents the exact instrument version evidence backing a universe membership.
    Does not allocate identity, create instruments, or define domain entities.
    """

    instrument_id: str
    provider: str
    feed: str
    instrument_version: int
    symbol: str


class HistoricalUniverseWriteConflict(Exception):
    """Raised when attempting to save a snapshot with an existing snapshot_id whose
    persisted metadata or membership conflicts with the provided snapshot.
    """
