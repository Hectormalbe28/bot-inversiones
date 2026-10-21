"""Non-destructive quality signals for Nasdaq Symbol Directory evidence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.infrastructure.providers.nasdaq import NasdaqNormalizedFile


@dataclass(frozen=True, slots=True)
class NasdaqQualityReport:
    """Operational-quality counts; never a membership or identity filter."""

    total_records: int
    test_issue_count: int
    non_normal_financial_status_count: int
    financial_status_counts: tuple[tuple[str, int], ...]

    @property
    def warning_count(self) -> int:
        return self.test_issue_count + self.non_normal_financial_status_count


def assess_nasdaq_quality(normalized: NasdaqNormalizedFile) -> NasdaqQualityReport:
    """Count provider signals while retaining every normalized row unchanged."""
    statuses = Counter(record.financial_status for record in normalized.records)
    return NasdaqQualityReport(
        total_records=len(normalized.records),
        test_issue_count=sum(record.test_issue for record in normalized.records),
        non_normal_financial_status_count=sum(
            count for status, count in statuses.items() if status != "N"
        ),
        financial_status_counts=tuple(sorted(statuses.items())),
    )
