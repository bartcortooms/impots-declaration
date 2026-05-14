"""Per-sale lot attribution via prior-year-end vs current-year-end diff.

The broker statement doesn't tell us *which* lots each sale consumed, but if
we have last year's holdings AND this year's holdings, the diff per lot
tells us exactly how many shares of each lot were sold during the year.
We then attribute those consumed lots to the year's individual sales in
chronological FIFO order (oldest lot first).

This gives every sale an exact per-lot breakdown, so the abattement rate
(0% / 50% / 65%) can be applied at lot granularity rather than at the sale
or portfolio level.

Assumptions:
- Lots are identified by `lot_id`, which is stable across yearly
  statements (verified empirically: same Vest ID stays put as long as
  there are shares left in the lot).
- No new lots were vested during the year (i.e., no acquisition_date >
  prior year's statement period). If the user vested mid-year, those new
  lots won't appear in the prior-year statement and the diff math breaks.
  The validation step catches this by comparing consumed-share totals
  against sale-quantity totals.
- Lots are class-specific (GOOGL vs GOOG share class). The attribution
  respects fund/class — GOOGL sales only consume GOOGL lots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .sales import LotChunk, StockSale
from .statement import Lot


@dataclass(frozen=True)
class ConsumedLot:
    """A lot, with how many of its shares were consumed during the year."""

    lot_id: str
    fund: str
    acquisition_date: date
    cost_per_share_usd: Decimal
    shares_consumed: int


@dataclass(frozen=True)
class SaleAttribution:
    """A sale plus its FIFO-attributed lot chunks."""

    order_number: str
    execution_date: date
    fund: str
    quantity: int
    chunks: list[LotChunk]

    def __post_init__(self) -> None:
        chunk_qty = sum(c.shares for c in self.chunks)
        if chunk_qty != self.quantity:
            raise ValueError(
                f"Attribution mismatch for {self.order_number}: sale qty {self.quantity}, "
                f"chunks sum to {chunk_qty}"
            )


def compute_consumed_lots(
    prior_lots: list[Lot], current_lots: list[Lot]
) -> list[ConsumedLot]:
    """Return per-lot consumption between two yearly snapshots.

    Lots present in `prior_lots` but absent from `current_lots` count as
    fully consumed. Lots present in both with reduced share count count
    as partially consumed.
    """
    current_by_id = {lot.lot_id: lot for lot in current_lots}
    consumed: list[ConsumedLot] = []
    for prior in prior_lots:
        current = current_by_id.get(prior.lot_id)
        current_shares = current.shares if current else 0
        delta = prior.shares - current_shares
        if delta <= 0:
            continue
        if current and current.acquisition_date != prior.acquisition_date:
            raise ValueError(
                f"Lot {prior.lot_id} changed acquisition date between snapshots "
                f"({prior.acquisition_date} → {current.acquisition_date})"
            )
        consumed.append(
            ConsumedLot(
                lot_id=prior.lot_id,
                fund=prior.fund,
                acquisition_date=prior.acquisition_date,
                cost_per_share_usd=prior.cost_basis_per_share_usd,
                shares_consumed=delta,
            )
        )
    return consumed


def attribute_sales(
    *,
    sales: list[StockSale],
    consumed_lots: list[ConsumedLot],
) -> list[SaleAttribution]:
    """Walk sales chronologically, consuming oldest lots first per fund.

    Each sale of fund F draws from F's consumed lots in FIFO order. Sales
    spanning multiple lots produce multiple chunks; sales fitting within
    one lot produce one chunk.

    Raises if consumed-lots totals don't match sale totals (per fund) —
    a signal that the prior/current statements aren't a clean diff (e.g.,
    mid-year vest, transfer in/out, or wrong year files).
    """
    sorted_sales = sorted(sales, key=lambda s: (s.execution_date, s.order_number))

    # Index consumed lots by canonical fund, oldest first. Use mutable
    # [acq_date, shares_remaining, cost_per_share, lot_id] for in-place decrement.
    lots_by_fund: dict[str, list[list]] = {}
    for cl in consumed_lots:
        lots_by_fund.setdefault(cl.fund, []).append(
            [cl.acquisition_date, cl.shares_consumed, cl.cost_per_share_usd, cl.lot_id]
        )
    for lots in lots_by_fund.values():
        lots.sort(key=lambda x: x[0])

    # Per-fund quantity validation upfront — better error than running out mid-FIFO.
    sale_qty_by_fund: dict[str, int] = {}
    for s in sorted_sales:
        sale_qty_by_fund[s.fund] = sale_qty_by_fund.get(s.fund, 0) + int(s.quantity)
    for fund, qty in sale_qty_by_fund.items():
        lot_qty = sum(int(l[1]) for l in lots_by_fund.get(fund, []))
        if qty != lot_qty:
            raise ValueError(
                f"Fund '{fund}': sold {qty} shares this year but consumed-lot diff "
                f"shows {lot_qty} shares vanished from inventory. The prior/current "
                f"statements may not be a clean diff (mid-year vest, transfer, or "
                f"wrong files)."
            )

    attributions: list[SaleAttribution] = []
    for sale in sorted_sales:
        lots = lots_by_fund.get(sale.fund)
        if lots is None:
            raise ValueError(
                f"No consumed lots found for sale {sale.order_number} fund {sale.fund!r}."
            )
        chunks = _consume_fifo(int(sale.quantity), lots, sale.order_number)
        attributions.append(
            SaleAttribution(
                order_number=sale.order_number,
                execution_date=sale.execution_date,
                fund=sale.fund,
                quantity=int(sale.quantity),
                chunks=chunks,
            )
        )
    return attributions


def _consume_fifo(quantity: int, lots: list, order_number: str) -> list[LotChunk]:
    """Consume `quantity` shares from `lots` (oldest first), decrementing in place."""
    chunks: list[LotChunk] = []
    remaining = quantity
    for lot in lots:
        if remaining == 0:
            break
        acq_date, available, cost_per_share, _lot_id = lot
        if available <= 0:
            continue
        take = min(int(available), remaining)
        chunks.append(
            LotChunk(
                acquisition_date=acq_date,
                shares=take,
                cost_per_share_usd=cost_per_share,
            )
        )
        lot[1] = available - take
        remaining -= take
    if remaining > 0:
        raise ValueError(
            f"Not enough consumed lots to cover sale {order_number}: "
            f"{remaining} shares unattributed."
        )
    return chunks
