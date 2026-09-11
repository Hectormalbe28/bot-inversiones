"""Tests for Nasdaq raw fixture integrity.

Verifies that raw provider fixtures exist, adhere to expected raw structures,
and do not contain normalized domain entities or identity concepts.
"""

from pathlib import Path

FIXTURES_DIR = Path("tests/fixtures/nasdaq")

MANDATORY_FIXTURES = [
    "nasdaqlisted_valid.txt",
    "nasdaqlisted_test_issue.txt",
    "nasdaqlisted_financial_status.txt",
    "nasdaqlisted_empty_universe.txt",
    "nasdaqlisted_missing_footer.txt",
    "nasdaqlisted_bad_header.txt",
    "nasdaqlisted_malformed_row.txt",
    "nasdaqlisted_duplicate_symbol.txt",
    "nasdaqlisted_symbol_variants.txt",
    "nasdaqlisted_schema_extension.txt",
]

OFFICIAL_HEADER = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)


def test_all_mandatory_fixtures_exist():
    for name in MANDATORY_FIXTURES:
        p = FIXTURES_DIR / name
        assert p.exists(), f"Missing mandatory fixture: {name}"
        assert p.is_file(), f"Fixture is not a file: {name}"


def test_all_fixtures_non_empty():
    for name in MANDATORY_FIXTURES:
        p = FIXTURES_DIR / name
        assert p.stat().st_size > 0, f"Fixture is empty: {name}"


def test_valid_fixture_uses_exact_official_header():
    lines = (FIXTURES_DIR / "nasdaqlisted_valid.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    assert lines[0] == OFFICIAL_HEADER


def test_valid_fixture_contains_file_creation_time():
    lines = (FIXTURES_DIR / "nasdaqlisted_valid.txt").read_text(encoding="utf-8").splitlines()
    footer = lines[-1]
    assert footer.startswith("File Creation Time: ")
    assert footer.count("|") == 7


def test_empty_universe_fixture():
    lines = (
        (FIXTURES_DIR / "nasdaqlisted_empty_universe.txt").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 2
    assert lines[0] == OFFICIAL_HEADER
    assert lines[1].startswith("File Creation Time: ")
    security_rows = lines[1:-1]
    assert len(security_rows) == 0


def test_missing_footer_fixture_lacks_footer():
    lines = (
        (FIXTURES_DIR / "nasdaqlisted_missing_footer.txt").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) > 1
    assert lines[0] == OFFICIAL_HEADER
    for line in lines[1:]:
        assert not line.startswith("File Creation Time:")


def test_bad_header_fixture_differs_from_official_header():
    lines = (FIXTURES_DIR / "nasdaqlisted_bad_header.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] != OFFICIAL_HEADER


def test_malformed_row_fixture_has_inconsistent_field_count():
    lines = (
        (FIXTURES_DIR / "nasdaqlisted_malformed_row.txt").read_text(encoding="utf-8").splitlines()
    )
    expected_field_count = len(OFFICIAL_HEADER.split("|"))
    row_counts = [len(row.split("|")) for row in lines[1:-1]]
    assert any(count != expected_field_count for count in row_counts)


def test_duplicate_symbol_fixture_contains_duplicates():
    lines = (
        (FIXTURES_DIR / "nasdaqlisted_duplicate_symbol.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    symbols = [row.split("|")[0] for row in lines[1:-1]]
    assert len(symbols) > len(set(symbols)), "Expected duplicate symbols in fixture"


def test_schema_extension_fixture_has_extra_column():
    lines = (
        (FIXTURES_DIR / "nasdaqlisted_schema_extension.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    header_fields = lines[0].split("|")
    expected_fields = OFFICIAL_HEADER.split("|")
    assert len(header_fields) == len(expected_fields) + 1
    assert header_fields[:-1] == expected_fields


def test_fixtures_contain_no_instrument_id():
    for name in MANDATORY_FIXTURES:
        content = (FIXTURES_DIR / name).read_text(encoding="utf-8")
        assert "instrument_id" not in content.lower(), f"Fixture {name} contains instrument_id"


def test_fixtures_contain_no_normalized_domain_json():
    for name in MANDATORY_FIXTURES:
        content = (FIXTURES_DIR / name).read_text(encoding="utf-8")
        assert not content.strip().startswith("{"), f"Fixture {name} appears to be JSON"
        assert not content.strip().startswith("["), f"Fixture {name} appears to be JSON"
        assert "InstrumentVersion" not in content
        assert "HistoricalUniverseSnapshot" not in content
