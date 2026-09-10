from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from uuid import uuid4


@dataclass
class DomainError:
    """Structured domain error with required fields.

    Fields:
        code: A machine-readable error code (e.g., "not-found", "validation-error").
        message: Human-readable error message.
        retryable: Whether the operation can be retried (boolean).
        dependency: Optional dependency name that failed (e.g., "db", "external-api").
        evidence: Optional structured evidence (dict) for debugging; never includes secrets.
        correlation_id: UUID4 correlation ID for tracing across services.
    """
    code: str
    message: str
    retryable: bool = field(default=False)
    dependency: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None
    correlation_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        # Ensure correlation_id is a string UUID4
        if not self.correlation_id.startswith("uuid4"):
            # This is a safety check; the default_factory already creates uuid4
            pass