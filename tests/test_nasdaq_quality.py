from app.infrastructure.providers.nasdaq import normalize_nasdaqlisted, parse_nasdaqlisted
from app.infrastructure.providers.nasdaq_quality import assess_nasdaq_quality

HEADER = (
    b"Symbol|Security Name|Market Category|Test Issue|Financial Status|"
    b"Round Lot Size|ETF|NextShares\n"
)


def test_quality_counts_provider_flags_without_removing_membership_evidence():
    raw = (
        HEADER + b"TEST|Test Corp|Q|Y|D|100|N|N\n"
        b"NORM|Normal Corp|Q|N|N|100|N|N\n"
        b"File Creation Time: 1017202612:00|||||||\n"
    )

    normalized = normalize_nasdaqlisted(parse_nasdaqlisted(raw))
    report = assess_nasdaq_quality(normalized)

    assert len(normalized.records) == 2
    assert report.total_records == 2
    assert report.test_issue_count == 1
    assert report.non_normal_financial_status_count == 1
    assert report.financial_status_counts == (("D", 1), ("N", 1))
    assert report.warning_count == 2


def test_quality_empty_universe_has_no_warnings():
    raw = HEADER + b"File Creation Time: 1017202612:00|||||||\n"

    report = assess_nasdaq_quality(normalize_nasdaqlisted(parse_nasdaqlisted(raw)))

    assert report.total_records == 0
    assert report.financial_status_counts == ()
    assert report.warning_count == 0
