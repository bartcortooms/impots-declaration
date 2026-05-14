"""Form 2074-ABT line 1133 grouping.

The form has 3 abattement slots ("Titres A / B / C"). With N sales:
  N ≤ 3: each sale gets its own slot
  N > 3: first 2 sales (by date) get their own slots; remaining are summed
         into slot C, with a composition table listing the constituent sales.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .sales import StockSale


@dataclass(frozen=True)
class AbattementSlot:
    """One slot row on Form 2074-ABT line 1133 (Titres A/B/C)."""

    name: str  # 'Titres A' / 'Titres B' / 'Titres C'
    description: str  # composite description if grouped
    constituent_sales: list[StockSale]
    total_gain_eur: Decimal
    total_abattement_eur: Decimal


@dataclass(frozen=True)
class AbattementGrouping:
    slots: list[AbattementSlot]
    total_gain_eur: Decimal  # sum of slot total_gain_eur (matches form 'Totaux col E')
    total_abattement_eur: Decimal  # sum of slot total_abattement_eur ('Totaux col F')


def group_sales(sales: list[StockSale]) -> AbattementGrouping:
    """Sort sales by date, then bucket: first N-individual, rest grouped into Titres C."""
    sorted_sales = sorted(sales, key=lambda s: s.execution_date)
    slots: list[AbattementSlot] = []
    n = len(sorted_sales)

    if n == 0:
        pass
    elif n == 1:
        slots.append(_singleton_slot("Titres A", sorted_sales[0]))
    elif n == 2:
        slots.append(_singleton_slot("Titres A", sorted_sales[0]))
        slots.append(_singleton_slot("Titres B", sorted_sales[1]))
    elif n == 3:
        slots.append(_singleton_slot("Titres A", sorted_sales[0]))
        slots.append(_singleton_slot("Titres B", sorted_sales[1]))
        slots.append(_singleton_slot("Titres C", sorted_sales[2]))
    else:
        slots.append(_singleton_slot("Titres A", sorted_sales[0]))
        slots.append(_singleton_slot("Titres B", sorted_sales[1]))
        slots.append(_grouped_slot("Titres C", sorted_sales[2:]))

    total_gain = sum((s.total_gain_eur for s in slots), Decimal(0))
    total_abat = sum((s.total_abattement_eur for s in slots), Decimal(0))
    return AbattementGrouping(
        slots=slots,
        total_gain_eur=total_gain,
        total_abattement_eur=total_abat,
    )


def _singleton_slot(name: str, sale: StockSale) -> AbattementSlot:
    return AbattementSlot(
        name=name,
        description=sale.description,
        constituent_sales=[sale],
        total_gain_eur=sale.gain_eur,
        total_abattement_eur=sale.abattement_eur,
    )


def _grouped_slot(name: str, sales: list[StockSale]) -> AbattementSlot:
    # Description summarizes the mix of tickers.
    tickers = sorted({
        s.fund.split(" - ")[0] if " - " in s.fund else s.fund
        for s in sales
    })
    desc = f"Actions {' + '.join(tickers)} (groupé)"
    total_gain = sum((s.gain_eur for s in sales), Decimal(0))
    total_abat = sum((s.abattement_eur for s in sales), Decimal(0))
    return AbattementSlot(
        name=name,
        description=desc,
        constituent_sales=list(sales),
        total_gain_eur=total_gain,
        total_abattement_eur=total_abat,
    )
