"""Regression tests for the sales-report CSV parser.

Structural assertions only — no specific dollar amounts or order numbers
that could identify the user. Skips when personal-data/ inputs aren't
present.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from impots.withdrawals import parse, share_sales


REPO_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "personal-data"
CSV_2024 = DATA_DIR / "2024" / "input" / "Withdrawals Report.csv"
CSV_2025 = DATA_DIR / "2025" / "input" / "Withdrawals Report.csv"

pytestmark = pytest.mark.skipif(
    not (CSV_2024.exists() and CSV_2025.exists()),
    reason=(
        "Regression tests require sales-report CSVs at "
        "personal-data/{2024,2025}/input/ — skip when not present."
    ),
)


def test_2024_has_both_share_sales_and_cash_rows():
    rows = parse(CSV_2024)
    shares = share_sales(rows)
    cash = [r for r in rows if r.plan == "Cash"]
    assert len(shares) > 0
    assert len(cash) > 0
    assert len(shares) + len(cash) == len(rows)


def test_2024_rows_are_in_target_year():
    rows = parse(CSV_2024)
    for r in rows:
        assert r.execution_date.year == 2024


def test_2024_cash_row_attributes():
    rows = parse(CSV_2024)
    cash = next(r for r in rows if r.plan == "Cash")
    assert not cash.is_share_sale
    assert cash.fund == "Cash - USD"
    assert cash.price_usd == Decimal("1.00")


def test_2025_rows_are_in_target_year():
    rows = parse(CSV_2025)
    for r in rows:
        assert r.execution_date.year == 2025


def test_share_sale_invariants():
    """Every share-sale row has positive quantity and price."""
    for year_csv in (CSV_2024, CSV_2025):
        for r in share_sales(parse(year_csv)):
            assert r.quantity > 0
            assert r.price_usd > 0
            assert r.is_share_sale
