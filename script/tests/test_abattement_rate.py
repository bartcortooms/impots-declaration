"""Tests for the per-sale abattement rate computation (Tier 1 cutoff flag)."""

from datetime import date
from decimal import Decimal

import pytest

from impots.sales import (
    ABATTEMENT_RATE_8YR,
    ABATTEMENT_RATE_2YR,
    ABATTEMENT_RATE_NONE,
    abattement_rate_for,
    years_held_date_to_date,
)


@pytest.mark.parametrize(
    "acquisition,sale,expected_years",
    [
        # Exact anniversary → counts as N years
        (date(2017, 6, 25), date(2025, 6, 25), 8),
        # One day short → counts as N-1
        (date(2017, 6, 25), date(2025, 6, 24), 7),
        # Same day-of-year, year+1 → 1 year
        (date(2020, 3, 15), date(2021, 3, 15), 1),
        # Year wrap (sale in earlier month)
        (date(2018, 11, 30), date(2025, 1, 15), 6),
        # Same-year impossible? Just one full year difference
        (date(2010, 1, 1), date(2025, 12, 31), 15),
    ],
)
def test_years_held_de_date_a_date(acquisition, sale, expected_years):
    assert years_held_date_to_date(acquisition, sale) == expected_years


@pytest.mark.parametrize(
    "years,expected",
    [
        (0, ABATTEMENT_RATE_NONE),
        (1, ABATTEMENT_RATE_NONE),
        (2, ABATTEMENT_RATE_2YR),
        (7, ABATTEMENT_RATE_2YR),
        (8, ABATTEMENT_RATE_8YR),
        (15, ABATTEMENT_RATE_8YR),
    ],
)
def test_rate_brackets(years, expected):
    assert abattement_rate_for(years) == expected


def test_rate_values():
    """The three rates match the droit-commun figures from notice 2074-ABT."""
    assert ABATTEMENT_RATE_NONE == Decimal("0")
    assert ABATTEMENT_RATE_2YR == Decimal("0.50")
    assert ABATTEMENT_RATE_8YR == Decimal("0.65")
