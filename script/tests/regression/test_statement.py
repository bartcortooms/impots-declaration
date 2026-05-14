"""Regression tests for the broker statement.pdf parser.

These tests verify the parser against real statements stored in
personal-data/. They skip when those files aren't present, so the public
test run on a fresh checkout sees zero tests here.

Assertions check structural invariants (counts, ratios, date ranges) — not
specific dollar amounts — so this file doesn't leak any personal values
even when the personal-data PDFs are present.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from impots.statement import parse


REPO_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "personal-data"
STATEMENT_2024 = DATA_DIR / "2024" / "input" / "statement.pdf"
STATEMENT_2025 = DATA_DIR / "2025" / "input" / "statement.pdf"

pytestmark = pytest.mark.skipif(
    not (STATEMENT_2024.exists() and STATEMENT_2025.exists()),
    reason=(
        "Regression tests require statement PDFs at "
        "personal-data/{2024,2025}/input/statement.pdf — skip when not present."
    ),
)


@pytest.fixture(scope="module")
def s2024():
    return parse(STATEMENT_2024)


@pytest.fixture(scope="module")
def s2025():
    return parse(STATEMENT_2025)


def test_2024_period(s2024):
    assert s2024.period_start == date(2024, 1, 1)
    assert s2024.period_end == date(2024, 12, 31)


def test_2024_parser_returns_sales(s2024):
    """The parser extracts at least one sale and each has positive cost basis."""
    assert len(s2024.sales) > 0
    for sale in s2024.sales:
        assert sale.cost_basis_usd > 0
        assert sale.date.year == 2024


def test_2024_dividend_withholding_is_15_percent(s2024):
    """Foreign withholding should be exactly 15% of each US-source dividend.

    This is a parser invariant (gross + withholding fields align with the
    treaty rate) — independent of the specific dollar values.
    """
    assert len(s2024.dividends) > 0
    for d in s2024.dividends:
        ratio = d.withholding_usd / d.gross_usd
        assert ratio == Decimal("0.15"), f"{d.date} {d.fund}: ratio {ratio}"


def test_2024_lots_predate_cutoff(s2024):
    """All year-end lots should be acquired before some sensible cutoff,
    confirming the parser is reading vest dates as proper dates."""
    assert len(s2024.lots) > 0
    for lot in s2024.lots:
        assert lot.acquisition_date.year >= 2000
        assert lot.acquisition_date.year <= 2024


def test_2024_withdrawal_blocks_link_to_order_numbers(s2024):
    """Every withdrawal block has a parseable reference number — the join key
    between the CSV's order_number and the statement's cost-basis data."""
    refs = [w.reference_number for w in s2024.withdrawals]
    assert len(refs) > 0
    assert all(ref for ref in refs)
    assert len(set(refs)) == len(refs)  # no duplicate keys


def test_2025_period(s2025):
    assert s2025.period_start == date(2025, 1, 1)
    assert s2025.period_end == date(2025, 12, 31)


def test_2025_dividend_withholding_is_15_percent(s2025):
    assert len(s2025.dividends) > 0
    for d in s2025.dividends:
        ratio = d.withholding_usd / d.gross_usd
        assert ratio == Decimal("0.15"), f"{d.date} {d.fund}: ratio {ratio}"


def test_2025_sales_have_cost_basis(s2025):
    assert len(s2025.sales) > 0
    for sale in s2025.sales:
        assert sale.cost_basis_usd > 0
        assert sale.date.year == 2025
