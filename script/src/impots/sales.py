"""Stock sales: join CSV rows with statement cost basis, compute form fields.

Joining strategy:
  CSV row's order_number   → statement WithdrawalBlock (has fund + settlement date)
  WithdrawalBlock          → statement Sale (matches by fund + settlement date + qty)
  statement Sale           → cost_basis_usd

Abattement rate: by default we assume every sold lot is ≥ 8 years old AND
acquired before 2018-01-01, so the rate is 65% across the board. If the
caller passes `acquired_before=<date>`, we instead compute the rate per
sale conservatively from `sale_date − acquired_before` (date-to-date),
giving 0% / 50% / 65% per the holding-period brackets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .fx import FxRates
from .statement import Sale as StatementSale, Statement, WithdrawalBlock
from .withdrawals import WithdrawalRow


# Per notice 2074-ABT, droit commun rates:
#   < 2 years held → 0%
#   2 to < 8 years → 50%
#   ≥ 8 years      → 65%
ABATTEMENT_RATE_8YR = Decimal("0.65")
ABATTEMENT_RATE_2YR = Decimal("0.50")
ABATTEMENT_RATE_NONE = Decimal("0")


def _round(value: Decimal, places: int) -> Decimal:
    """Standard ROUND_HALF_UP to `places` decimal places."""
    q = Decimal(10) ** -places
    return value.quantize(q, rounding=ROUND_HALF_UP)


def years_held_date_to_date(acquisition_date: date, sale_date: date) -> int:
    """Integer 'de date à date' year count, per notice 2074-ABT.

    Returns the number of full anniversaries elapsed: 8 years exactly is
    8; one day short is 7.
    """
    years = sale_date.year - acquisition_date.year
    if (sale_date.month, sale_date.day) < (acquisition_date.month, acquisition_date.day):
        years -= 1
    return years


def abattement_rate_for(years_held: int) -> Decimal:
    """Map a holding period (in full years, date-to-date) to a droit-commun rate."""
    if years_held < 2:
        return ABATTEMENT_RATE_NONE
    if years_held < 8:
        return ABATTEMENT_RATE_2YR
    return ABATTEMENT_RATE_8YR


@dataclass(frozen=True)
class StockSale:
    """One share sale, with all values needed for form 2074 + 2074-ABT.

    Currency convention: `*_usd` are source-currency amounts; `*_eur` are
    converted using the FX rate on the execution date.
    """

    # source
    execution_date: date
    order_number: str
    plan: str  # broker-specific plan label, e.g. 'RSU Class A'
    fund: str  # broker-specific fund label, e.g. '<TICKER> - <EXCHANGE>'
    quantity: int

    # USD numbers
    sell_price_usd_per_share: Decimal
    cost_basis_usd: Decimal
    fx_rate: Decimal

    # Abattement rate for this sale (set by build_sales based on holding period).
    abattement_rate: Decimal = ABATTEMENT_RATE_8YR

    # derived USD totals
    @property
    def total_sell_usd(self) -> Decimal:
        return self.sell_price_usd_per_share * self.quantity

    @property
    def gain_usd(self) -> Decimal:
        return self.total_sell_usd - self.cost_basis_usd

    @property
    def cost_per_share_usd(self) -> Decimal:
        return self.cost_basis_usd / self.quantity

    # EUR values, rounded to match the fiche 2074-ABT paper-form convention
    # (standard half-up to the unit for totals; 2 decimals for unit prices).
    # Per-sale form 2074 cadre 5 § 510 mapping:
    #   Field 514 = ROUND(price_usd × FX, 2)         per-share (decimal)
    #   Field 515 = quantity                          integer
    #   Field 516 = ROUND(price_usd × FX × qty, 0)   total sell (integer)
    #   Field 517 = 0                                  frais de cession (typically none)
    #   Field 518 = Field 516 − Field 517              prix de cession net
    #   Field 520 = ROUND(cost_usd_per_share × FX, 2) per-share (decimal, display only)
    #   Field 521 = ROUND(cost_usd × FX, 0)            total cost (integer)
    #   Field 522 = 0                                  frais d'acquisition (typically none)
    #   Field 523 = Field 521 + Field 522              prix de revient
    #   Field 524 = Field 518 − Field 523              résultat (integer when 517=522=0)
    @property
    def sell_price_eur_per_share(self) -> Decimal:
        return _round(self.sell_price_usd_per_share * self.fx_rate, 2)

    @property
    def total_sell_eur(self) -> Decimal:
        """Field 516. Rounded to whole euros to match form convention."""
        return _round(self.sell_price_usd_per_share * self.fx_rate * self.quantity, 0)

    @property
    def cost_per_share_eur(self) -> Decimal:
        return _round(self.cost_per_share_usd * self.fx_rate, 2)

    @property
    def total_cost_eur(self) -> Decimal:
        """Field 521. Rounded to whole euros."""
        return _round(self.cost_basis_usd * self.fx_rate, 0)

    @property
    def frais_cession_eur(self) -> Decimal:
        """Field 517. RSU-style sales have no acquisition cost on the seller's side."""
        return Decimal(0)

    @property
    def prix_cession_net_eur(self) -> Decimal:
        """Field 518 = Field 516 − Field 517."""
        return self.total_sell_eur - self.frais_cession_eur

    @property
    def frais_acquisition_eur(self) -> Decimal:
        """Field 522. RSU vests have no acquisition fee."""
        return Decimal(0)

    @property
    def prix_revient_eur(self) -> Decimal:
        """Field 523 = Field 521 + Field 522."""
        return self.total_cost_eur + self.frais_acquisition_eur

    @property
    def gain_eur(self) -> Decimal:
        """Field 524 = Field 518 − Field 523. Integer when no fees."""
        return self.prix_cession_net_eur - self.prix_revient_eur

    @property
    def abattement_eur(self) -> Decimal:
        """Field 1133 col F = round-half-up(rate × gain). Matches fiche N08 convention."""
        return _round(self.abattement_rate * self.gain_eur, 0)

    @property
    def description(self) -> str:
        """Form 2074 Field 511 — user-visible description, derived from fund + plan."""
        ticker = self.fund.split(" - ")[0] if " - " in self.fund else self.fund
        return f"Actions {ticker} ({self.plan})"


def build_sales(
    *,
    withdrawals: list[WithdrawalRow],
    statement: Statement,
    fx: FxRates,
    acquired_before: date | None = None,
) -> list[StockSale]:
    """Join CSV rows with statement data; return one StockSale per share sale.

    If `acquired_before` is given, the abattement rate for each sale is
    computed from `sale_date − acquired_before` (conservative — assumes
    every sold share comes from the latest pre-cutoff lot).
    """
    by_order: dict[str, WithdrawalBlock] = {w.reference_number: w for w in statement.withdrawals}

    sales: list[StockSale] = []
    for row in withdrawals:
        if not row.is_share_sale:
            continue
        block = by_order.get(row.order_number)
        if block is None:
            raise ValueError(
                f"No withdrawal block in statement for order {row.order_number}; "
                f"is statement.pdf for the right year?"
            )
        statement_sale = _find_matching_statement_sale(statement.sales, block, row)
        if acquired_before is not None:
            rate = abattement_rate_for(
                years_held_date_to_date(acquired_before, row.execution_date)
            )
        else:
            rate = ABATTEMENT_RATE_8YR
        sales.append(
            StockSale(
                execution_date=row.execution_date,
                order_number=row.order_number,
                plan=row.plan,
                fund=statement_sale.fund,  # canonical fund from statement
                quantity=int(row.quantity),
                sell_price_usd_per_share=row.price_usd,
                cost_basis_usd=statement_sale.cost_basis_usd,
                fx_rate=fx.rate(row.execution_date),
                abattement_rate=rate,
            )
        )
    sales.sort(key=lambda s: s.execution_date)
    return sales


def _find_matching_statement_sale(
    statement_sales: list[StatementSale],
    block: WithdrawalBlock,
    csv_row: WithdrawalRow,
) -> StatementSale:
    """Activity Sale rows use settlement date; we match by settlement date + fund + qty.

    If multiple Sales match (e.g., two same-day sales of different sizes), qty
    disambiguates. If qty is also identical, share price disambiguates.
    """
    candidates = [
        s
        for s in statement_sales
        if s.date == block.settlement_date
        and s.fund == block.fund
        and s.quantity == int(csv_row.quantity)
    ]
    if len(candidates) == 1:
        return candidates[0]
    # Tiebreak by share price
    price_matches = [s for s in candidates if s.share_price_usd == csv_row.price_usd]
    if len(price_matches) == 1:
        return price_matches[0]
    if not candidates:
        raise ValueError(
            f"No statement Sale row found for {block.reference_number} "
            f"(fund={block.fund}, settlement={block.settlement_date}, qty={csv_row.quantity})"
        )
    raise ValueError(
        f"Ambiguous match for {block.reference_number}: {len(candidates)} candidates"
    )


def cost_per_share_within_known_range(sale: StockSale, max_known_fmv: Decimal) -> bool:
    """Defensive check: cost per share should be ≤ known maximum lot FMV.

    If a sale's avg cost exceeds the FMV of the most recent known lot, it may
    contain an unexpected newer (post-2018) lot — abattement assumption needs
    manual review.
    """
    return sale.cost_per_share_usd <= max_known_fmv
