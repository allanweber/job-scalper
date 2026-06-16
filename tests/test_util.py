"""Offline tests for the shared salary/timezone parsing helpers (Phase 5)."""

from scalper.sources._util import extract_timezone, parse_salary


def test_parse_salary_range_with_symbol_and_commas():
    assert parse_salary("$90,000 - $120,000") == (90000.0, 120000.0, "USD")


def test_parse_salary_k_suffix_and_euro():
    assert parse_salary("€80k – €100k") == (80000.0, 100000.0, "EUR")


def test_parse_salary_single_amount_is_floor():
    assert parse_salary("$110,000") == (110000.0, None, "USD")


def test_parse_salary_up_to_is_ceiling():
    assert parse_salary("Up to $150k") == (None, 150000.0, "USD")


def test_parse_salary_three_letter_code():
    assert parse_salary("USD 120000") == (120000.0, None, "USD")


def test_parse_salary_ignores_hourly_and_401k_noise():
    # Small numbers (hourly) are below the annual window and dropped; "401(k)"
    # without a k-magnitude on a bare 401 is < 1000 and ignored too.
    assert parse_salary("$25 - $40 / hour") == (None, None, "USD")
    assert parse_salary("great 401(k) match") == (None, None, None)


def test_parse_salary_empty_or_unparseable():
    assert parse_salary("") == (None, None, None)
    assert parse_salary("competitive") == (None, None, None)


def test_extract_timezone_explicit_offset_normalized():
    assert extract_timezone("Remote (UTC+2)") == "UTC+2"
    assert extract_timezone("GMT -5") == "UTC-5"
    assert extract_timezone("UTC+05:30 only") == "UTC+5:30"


def test_extract_timezone_named_abbreviation():
    assert extract_timezone("Remote — CET working hours") == "CET"
    assert extract_timezone("US, EST preferred") == "EST"


def test_extract_timezone_region_bucket():
    assert extract_timezone("Europe") == "Europe"
    assert extract_timezone("Anywhere in EMEA") == "EMEA"
    assert extract_timezone("United States") == "Americas"


def test_extract_timezone_none_when_no_signal():
    assert extract_timezone("Anywhere") is None
    assert extract_timezone(None) is None
