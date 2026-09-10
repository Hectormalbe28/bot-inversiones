from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.ids import generate_correlation_id

_SENSITIVE_EVIDENCE = re.compile(r"api[ _-]?key|token|password|secret", re.IGNORECASE)


@dataclass
class DomainError(Exception):
    code: str
    message: str
    retryable: bool = False
    dependency: str | None = None
    evidence: str | None = None
    correlation_id: str = field(default_factory=generate_correlation_id)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def as_public_payload(self, correlation_id: str | None = None) -> dict[str, str | bool | None]:
        evidence = self.evidence
        if evidence is not None and _SENSITIVE_EVIDENCE.search(evidence):
            evidence = None
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "dependency": self.dependency,
            "evidence": evidence,
            "correlation_id": correlation_id or self.correlation_id,
        }
