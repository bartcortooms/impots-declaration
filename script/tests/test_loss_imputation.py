"""Tests for moins-values carry-forward imputation."""

from datetime import date
from decimal import Decimal

from impots.abattement import group_sales
from impots.sales import StockSale


def _sale(gain_eur: Decimal, abat_rate: Decimal = Decimal("0.65")) -> StockSale:
    """Build a minimal StockSale where the abattement_rate × gain_eur match
    the desired numbers (used for testing imputation, not parsing)."""
    # Pick USD numbers + FX such that gain_eur comes out right.
    # gain_eur = round(price × fx × qty, 0) - round(cost × fx, 0).
    # Simpler: set cost = 0, qty = 1, fx = 1, price_usd = gain.
    return StockSale(
        execution_date=date(2025, 5, 1),
        order_number=f"S-{int(gain_eur)}",
        plan="RSU",
        fund="ACMA - NASDAQ",
        quantity=1,
        sell_price_usd_per_share=gain_eur,
        cost_basis_usd=Decimal(0),
        fx_rate=Decimal(1),
        abattement_rate=abat_rate,
    )


def test_no_loss_keeps_grouping_unchanged():
    sales = [_sale(Decimal(1000)), _sale(Decimal(2000)), _sale(Decimal(3000))]
    g = group_sales(sales, prior_losses_eur=Decimal(0))
    assert g.gross_gain_eur == g.total_gain_eur == 6000
    assert g.total_abattement_eur == 6000 * 0.65
    assert g.loss_imputation.imputed_eur == 0
    assert g.loss_imputation.remaining_eur == 0


def test_loss_fully_absorbed():
    """Loss < gross PV → imputed = loss, net PV reduced."""
    sales = [_sale(Decimal(10000))]
    g = group_sales(sales, prior_losses_eur=Decimal(3000))
    assert g.gross_gain_eur == 10000
    assert g.total_gain_eur == 7000  # net after imputation
    assert g.loss_imputation.imputed_eur == 3000
    assert g.loss_imputation.remaining_eur == 0
    # Abattement is on the NET PV: 7000 × 0.65 = 4550
    assert g.total_abattement_eur == 4550


def test_loss_exceeds_pv_carries_forward():
    sales = [_sale(Decimal(5000))]
    g = group_sales(sales, prior_losses_eur=Decimal(8000))
    assert g.gross_gain_eur == 5000
    assert g.total_gain_eur == 0
    assert g.total_abattement_eur == 0
    assert g.loss_imputation.imputed_eur == 5000
    assert g.loss_imputation.remaining_eur == 3000


def test_loss_proportional_across_slots():
    """A loss of 30% of gross reduces each slot's net by 30% (approx, rounding)."""
    sales = [
        _sale(Decimal(1000)),
        _sale(Decimal(2000)),
        _sale(Decimal(3000)),
    ]  # gross 6000
    g = group_sales(sales, prior_losses_eur=Decimal(1800))  # 30% imputation
    assert g.gross_gain_eur == 6000
    assert g.total_gain_eur == 4200
    # Each slot should be ~70% of its original
    slot_gains = [s.total_gain_eur for s in g.slots]
    expected = [700, 1400, 2100]
    for got, want in zip(slot_gains, expected):
        assert abs(int(got) - want) <= 1, f"slot {got} vs {want}"


def test_negative_loss_treated_as_zero():
    sales = [_sale(Decimal(1000))]
    g = group_sales(sales, prior_losses_eur=Decimal(-500))
    assert g.loss_imputation.imputed_eur == 0
    assert g.total_gain_eur == 1000
