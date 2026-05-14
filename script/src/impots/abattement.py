"""Form 2074-ABT line 1133 grouping.

The form has 3 abattement slots ("Titres A / B / C"). With N sales:
  N ≤ 3: each sale gets its own slot
  N > 3: first 2 sales (by date) get their own slots; remaining are summed
         into slot C, with a composition table listing the constituent sales.

Moins-values carry-forward: per notice 2074-ABT, prior-year carry-forward
losses must be imputed against the gross plus-value BEFORE the abattement
is applied. The `prior_losses_eur` argument to `group_sales` applies the
imputation proportionally across slots; the resulting `loss_imputation`
field records what was used and what (if anything) is unused (rolls
forward to N+1).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .sales import StockSale


@dataclass(frozen=True)
class AbattementSlot:
    """One slot row on Form 2074-ABT line 1133 (Titres A/B/C)."""

    name: str  # 'Titres A' / 'Titres B' / 'Titres C'
    description: str  # composite description if grouped
    constituent_sales: list[StockSale]
    total_gain_eur: Decimal       # col E: net of prior-losses imputation
    total_abattement_eur: Decimal  # col F: abattement on the net gain
    gross_gain_eur: Decimal       # col E pre-imputation, kept for transparency


@dataclass(frozen=True)
class LossImputation:
    """How much of the user-declared carry-forward loss got used this year."""

    prior_losses_declared_eur: Decimal
    imputed_eur: Decimal       # min(declared, total gross PV)
    remaining_eur: Decimal     # carries forward to N+1 (case 3VH next year)


@dataclass(frozen=True)
class AbattementGrouping:
    slots: list[AbattementSlot]
    total_gain_eur: Decimal       # sum of slot.total_gain_eur (= net col E total)
    total_abattement_eur: Decimal  # sum of slot.total_abattement_eur (col F total)
    gross_gain_eur: Decimal       # sum of slot.gross_gain_eur (pre-imputation)
    loss_imputation: LossImputation


def _round(value: Decimal, places: int = 0) -> Decimal:
    q = Decimal(10) ** -places
    return value.quantize(q, rounding=ROUND_HALF_UP)


def group_sales(
    sales: list[StockSale],
    prior_losses_eur: Decimal = Decimal(0),
) -> AbattementGrouping:
    """Sort sales by date, bucket into 3 bloc-1133 slots, then optionally
    impute prior-year carry-forward losses proportionally across slots."""
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

    gross_total = sum((s.total_gain_eur for s in slots), Decimal(0))
    losses = max(prior_losses_eur, Decimal(0))
    imputed = min(losses, gross_total) if gross_total > 0 else Decimal(0)
    remaining = losses - imputed

    if imputed > 0 and gross_total > 0:
        # Scale each slot's gain & abattement by the imputation factor.
        # This reduces both proportionally and preserves the slot's blended rate.
        factor = (gross_total - imputed) / gross_total
        slots = [
            AbattementSlot(
                name=slot.name,
                description=slot.description,
                constituent_sales=slot.constituent_sales,
                gross_gain_eur=slot.total_gain_eur,
                total_gain_eur=_round(slot.total_gain_eur * factor, 0),
                total_abattement_eur=_round(slot.total_abattement_eur * factor, 0),
            )
            for slot in slots
        ]
    else:
        slots = [
            AbattementSlot(
                name=slot.name,
                description=slot.description,
                constituent_sales=slot.constituent_sales,
                gross_gain_eur=slot.total_gain_eur,
                total_gain_eur=slot.total_gain_eur,
                total_abattement_eur=slot.total_abattement_eur,
            )
            for slot in slots
        ]

    total_gain = sum((s.total_gain_eur for s in slots), Decimal(0))
    total_abat = sum((s.total_abattement_eur for s in slots), Decimal(0))
    return AbattementGrouping(
        slots=slots,
        total_gain_eur=total_gain,
        total_abattement_eur=total_abat,
        gross_gain_eur=gross_total,
        loss_imputation=LossImputation(
            prior_losses_declared_eur=losses,
            imputed_eur=imputed,
            remaining_eur=remaining,
        ),
    )


def _singleton_slot(name: str, sale: StockSale) -> AbattementSlot:
    # gross_gain_eur is set to the same value here; group_sales replaces
    # with the post-imputation amount when prior_losses_eur > 0.
    return AbattementSlot(
        name=name,
        description=sale.description,
        constituent_sales=[sale],
        total_gain_eur=sale.gain_eur,
        total_abattement_eur=sale.abattement_eur,
        gross_gain_eur=sale.gain_eur,
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
        gross_gain_eur=total_gain,
    )
