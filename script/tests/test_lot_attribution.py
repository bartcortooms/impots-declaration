"""Tests for prior-year vs current-year lot reconciliation and FIFO attribution."""

from datetime import date
from decimal import Decimal

import pytest

from impots.lot_attribution import (
    ConsumedLot,
    attribute_sales,
    compute_consumed_lots,
)
from impots.sales import LotChunk, StockSale
from impots.statement import Lot


# Test fixtures ---------------------------------------------------------------

def _lot(lot_id, acq_year, acq_month, shares, fund="X - NASDAQ", cost=Decimal("10")):
    return Lot(
        fund=fund,
        acquisition_date=date(acq_year, acq_month, 15),
        lot_id=lot_id,
        cost_basis_usd=Decimal(shares) * cost,
        cost_basis_per_share_usd=cost,
        shares=shares,
    )


def _sale(order, qty, exec_date, fund="X - NASDAQ"):
    return StockSale(
        execution_date=exec_date,
        order_number=order,
        plan="RSU",
        fund=fund,
        quantity=qty,
        sell_price_usd_per_share=Decimal("100"),
        cost_basis_usd=Decimal("0"),  # unused for these tests
        fx_rate=Decimal("0.9"),
    )


# compute_consumed_lots -------------------------------------------------------

def test_fully_consumed_lot_when_missing_from_current():
    prior = [_lot("A1", 2010, 1, 100)]
    consumed = compute_consumed_lots(prior, [])
    assert len(consumed) == 1
    assert consumed[0].lot_id == "A1"
    assert consumed[0].shares_consumed == 100


def test_partial_consumption():
    prior = [_lot("A1", 2010, 1, 100)]
    current = [_lot("A1", 2010, 1, 40)]  # 60 consumed
    consumed = compute_consumed_lots(prior, current)
    assert len(consumed) == 1
    assert consumed[0].shares_consumed == 60


def test_untouched_lot_not_reported():
    prior = [_lot("A1", 2010, 1, 100)]
    current = [_lot("A1", 2010, 1, 100)]
    assert compute_consumed_lots(prior, current) == []


def test_acquisition_date_change_rejected():
    """A lot_id can't change its acquisition date between snapshots
    (only checked when the lot is still partially present)."""
    prior = [_lot("A1", 2010, 1, 100)]
    current = [_lot("A1", 2011, 1, 40)]  # partial + date mismatch
    with pytest.raises(ValueError, match="changed acquisition date"):
        compute_consumed_lots(prior, current)


# attribute_sales -------------------------------------------------------------

def test_single_sale_drawn_from_single_lot():
    consumed = [ConsumedLot("A1", "X - NASDAQ", date(2010, 1, 15), Decimal("10"), 50)]
    sales = [_sale("S1", 50, date(2025, 5, 1))]
    attrs = attribute_sales(sales=sales, consumed_lots=consumed)
    assert len(attrs) == 1
    assert attrs[0].chunks == [
        LotChunk(acquisition_date=date(2010, 1, 15), shares=50, cost_per_share_usd=Decimal("10"))
    ]


def test_single_sale_spans_multiple_lots_fifo():
    """Sale of 120 from two lots — oldest fully consumed first."""
    consumed = [
        ConsumedLot("A1", "X - NASDAQ", date(2010, 1, 15), Decimal("10"), 100),
        ConsumedLot("A2", "X - NASDAQ", date(2012, 1, 15), Decimal("20"), 20),
    ]
    sales = [_sale("S1", 120, date(2025, 5, 1))]
    attrs = attribute_sales(sales=sales, consumed_lots=consumed)
    chunks = attrs[0].chunks
    assert len(chunks) == 2
    assert chunks[0].acquisition_date == date(2010, 1, 15)
    assert chunks[0].shares == 100
    assert chunks[1].acquisition_date == date(2012, 1, 15)
    assert chunks[1].shares == 20


def test_multi_sale_chronological_fifo():
    """Two sales: oldest sale gets oldest lots."""
    consumed = [
        ConsumedLot("A1", "X - NASDAQ", date(2010, 1, 15), Decimal("10"), 50),
        ConsumedLot("A2", "X - NASDAQ", date(2012, 1, 15), Decimal("20"), 50),
    ]
    sales = [
        _sale("S2", 50, date(2025, 8, 1)),
        _sale("S1", 50, date(2025, 3, 1)),
    ]
    attrs = attribute_sales(sales=sales, consumed_lots=consumed)
    by_order = {a.order_number: a for a in attrs}
    # Earlier sale gets oldest lot
    assert by_order["S1"].chunks[0].acquisition_date == date(2010, 1, 15)
    assert by_order["S2"].chunks[0].acquisition_date == date(2012, 1, 15)


def test_funds_are_isolated():
    """A GOOGL sale never draws from a GOOG lot."""
    consumed = [
        ConsumedLot("A1", "GOOGL - NASDAQ", date(2010, 1, 15), Decimal("10"), 50),
        ConsumedLot("B1", "GOOG - NASDAQ", date(2008, 1, 15), Decimal("5"), 50),
    ]
    sales = [
        _sale("S1", 50, date(2025, 5, 1), fund="GOOGL - NASDAQ"),
        _sale("S2", 50, date(2025, 5, 1), fund="GOOG - NASDAQ"),
    ]
    attrs = attribute_sales(sales=sales, consumed_lots=consumed)
    by_order = {a.order_number: a for a in attrs}
    assert by_order["S1"].chunks[0].acquisition_date == date(2010, 1, 15)
    assert by_order["S2"].chunks[0].acquisition_date == date(2008, 1, 15)


def test_quantity_mismatch_rejected():
    """If sales total != consumed-lot total per fund, error."""
    consumed = [ConsumedLot("A1", "X - NASDAQ", date(2010, 1, 15), Decimal("10"), 100)]
    sales = [_sale("S1", 50, date(2025, 5, 1))]  # sold only 50 but 100 vanished
    with pytest.raises(ValueError, match="vanished from inventory"):
        attribute_sales(sales=sales, consumed_lots=consumed)


# Bracket split through StockSale --------------------------------------------

def test_bracket_split_single_rate():
    """All chunks ≥ 8 years → one slice at 65%."""
    sale = _sale("S1", 100, date(2025, 5, 1))
    sale = StockSale(
        **{**sale.__dict__,
           "lot_breakdown": (
               LotChunk(date(2010, 1, 1), 60, Decimal("10")),
               LotChunk(date(2012, 1, 1), 40, Decimal("20")),
           )},
    )
    slices = sale.bracket_split
    assert len(slices) == 1
    assert slices[0].rate == Decimal("0.65")
    assert slices[0].quantity == 100


def test_bracket_split_mixed_rates():
    """Mix of 8yr+ and <8yr lots → two slices."""
    sale = _sale("S1", 100, date(2020, 5, 1))  # earlier sale date to span brackets
    sale = StockSale(
        **{**sale.__dict__,
           "lot_breakdown": (
               LotChunk(date(2010, 1, 1), 60, Decimal("10")),  # ~10.3 years → 65%
               LotChunk(date(2015, 1, 1), 40, Decimal("20")),  # ~5.3 years → 50%
           )},
    )
    slices = sale.bracket_split
    rates = sorted({sl.rate for sl in slices}, reverse=True)
    assert rates == [Decimal("0.65"), Decimal("0.50")]
