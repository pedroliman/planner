"""Tests for osparse module."""

import pytest
from datetime import datetime

from osparse.extract_cpos_projects import (
    parse_date,
    calculate_remaining_days,
    normalize_title,
)


class TestDateParsing:
    """Test date parsing functions."""

    def test_parse_date_mm_yyyy_first_day(self):
        """Test MM/YYYY format with first day of month."""
        assert parse_date("12/2026", default_day=1) == "2026-12-01"
        assert parse_date("01/2027", default_day=1) == "2027-01-01"

    def test_parse_date_mm_yyyy_last_day(self):
        """Test MM/YYYY format with last day of month."""
        assert parse_date("12/2026", default_day=-1) == "2026-12-31"
        assert parse_date("02/2027", default_day=-1) == "2027-02-28"
        assert parse_date("02/2028", default_day=-1) == "2028-02-29"  # leap year

    def test_parse_date_mm_dd_yyyy(self):
        """Test MM/DD/YYYY format."""
        assert parse_date("12/15/2026") == "2026-12-15"
        assert parse_date("01/01/2027") == "2027-01-01"

    def test_parse_date_yyyy_mm_dd(self):
        """Test YYYY-MM-DD format."""
        assert parse_date("2026-12-15") == "2026-12-15"
        assert parse_date("2027-01-01") == "2027-01-01"

    def test_parse_date_invalid(self):
        """Test invalid date strings."""
        assert parse_date("") is None
        assert parse_date("invalid") is None
        assert parse_date(None) is None


class TestCalculateRemainingDays:
    """Test remaining days calculation."""

    def test_calculate_remaining_days_single_year(self):
        """Test with single year of person months."""
        person_months = [{"year": 2027, "months": 2.38}]
        result = calculate_remaining_days(person_months, "2026-12-01")
        expected = round(226 * 2.38 / 12, 1)
        assert result == expected
        assert result == 44.8

    def test_calculate_remaining_days_multiple_years(self):
        """Test with multiple years - should use first year only."""
        person_months = [
            {"year": 2026, "months": 1.0},
            {"year": 2027, "months": 2.0},
            {"year": 2028, "months": 3.0},
        ]
        result = calculate_remaining_days(person_months, "2026-01-01")
        expected = round(226 * 1.0 / 12, 1)
        assert result == expected
        assert result == 18.8

    def test_calculate_remaining_days_uses_earliest_year(self):
        """Test that it uses earliest year with person months."""
        # Project starts in 2026 but person months start in 2027
        person_months = [
            {"year": 2027, "months": 2.38},
            {"year": 2028, "months": 2.38},
        ]
        result = calculate_remaining_days(person_months, "2026-12-01")
        expected = round(226 * 2.38 / 12, 1)
        assert result == expected
        assert result == 44.8

    def test_calculate_remaining_days_empty(self):
        """Test with no person months."""
        assert calculate_remaining_days([], "2026-01-01") == 0.0
        assert calculate_remaining_days(None, "2026-01-01") == 0.0


class TestNormalizeTitle:
    """Test title normalization."""

    def test_normalize_title_basic(self):
        """Test basic normalization."""
        assert normalize_title("Test Project") == "test project"
        assert normalize_title("TEST PROJECT") == "test project"

    def test_normalize_title_whitespace(self):
        """Test whitespace normalization."""
        assert normalize_title("Test  Project  Name") == "test project name"
        assert normalize_title("  Test Project  ") == "test project"
        assert normalize_title("Test\nProject\tName") == "test project name"

    def test_normalize_title_matching(self):
        """Test that similar titles match."""
        title1 = "Comparative Modeling to Inform Colorectal Cancer Control Policies"
        title2 = "Comparative Modeling to Inform Colorectal Cancer Control Pol"
        # These won't match because one is truncated, but that's expected
        assert normalize_title(title1) != normalize_title(title2)

        # But exact matches should work
        title3 = "Comparative  Modeling  to  Inform"
        title4 = "Comparative Modeling to Inform"
        assert normalize_title(title3) == normalize_title(title4)
