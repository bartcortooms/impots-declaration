"""Dividend computation for Form 2047, section 200.

Two important details (both points where an earlier hand-rolled spreadsheet
got things wrong):
  * Field 203 must use NET dividend (gross − foreign withholding), not gross.
    MS's "Dividend (Cash)" column in the statement is the GROSS dividend
    (withholding rate works out to 15% only when applied to that value).
  * Field 206 must be the withholding tax converted to EUR, not the raw USD
    amount.

For this user, all dividends are US-source. The form has 4 country slots on
lines 203/206/207 (verified against forms/form2047.pdf page 2), but since all
dividends are US-source we emit a single aggregated row for États-Unis.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .fx import FxRates
from .statement import DividendPayment


# Field 204 for US dividends, per notice 2047 page 5: "ÉTATS-UNIS div. 17,6%".
# This is the rate applied to NET dividends (= 15% treaty cap on gross,
# expressed as 15/85 ≈ 17.647% on net).
TAUX_APPLICABLE_US = Decimal("17.6")


def _floor_to_euro(amount: Decimal) -> int:
    """Floor a Decimal EUR amount to a whole euro (toward zero for nonneg)."""
    return int(amount)


@dataclass(frozen=True)
class DividendLine:
    """One per-payment entry in the raw dividend audit view."""

    payment: DividendPayment
    fx_rate: Decimal

    @property
    def gross_usd(self) -> Decimal:
        return self.payment.gross_usd

    @property
    def withholding_usd(self) -> Decimal:
        return self.payment.withholding_usd

    @property
    def net_usd(self) -> Decimal:
        return self.payment.net_usd

    @property
    def gross_eur(self) -> Decimal:
        return self.gross_usd * self.fx_rate

    @property
    def withholding_eur(self) -> Decimal:
        return self.withholding_usd * self.fx_rate

    @property
    def net_eur(self) -> Decimal:
        return self.net_usd * self.fx_rate


@dataclass(frozen=True)
class Form2047Section200:
    """Aggregated single-country (États-Unis) entry for Form 2047 section 200."""

    country: str  # 'États-Unis'
    field_203: int  # Montant net encaissé (EUR, floored)
    field_204: Decimal  # Taux applicable % (constant 17.6 for US)
    field_205: int  # Résultat = round(203 × 204%)
    field_206: int  # Impôt supporté à l'étranger (EUR, floored)
    field_207: int  # Crédit d'impôt retenu = min(205, 206)
    field_208: int  # Revenus crédit d'impôt inclus = 203 + 207

    # Audit totals (USD source values that fed the conversion)
    total_gross_usd: Decimal
    total_withholding_usd: Decimal
    total_net_usd: Decimal


def build_dividend_lines(
    *,
    dividends: list[DividendPayment],
    fx: FxRates,
) -> list[DividendLine]:
    """Per-payment audit lines with FX rates."""
    return [
        DividendLine(payment=d, fx_rate=fx.rate(d.date))
        for d in sorted(dividends, key=lambda d: (d.date, d.fund))
    ]


def build_form_2047(lines: list[DividendLine]) -> Form2047Section200:
    """Aggregate per-payment lines into a single États-Unis row."""
    total_gross_usd = sum((line.gross_usd for line in lines), Decimal(0))
    total_withholding_usd = sum((line.withholding_usd for line in lines), Decimal(0))
    total_net_usd = total_gross_usd - total_withholding_usd

    # Field 203: floor the sum of per-payment (net_usd × fx) values.
    sum_net_eur = sum((line.net_eur for line in lines), Decimal(0))
    field_203 = _floor_to_euro(sum_net_eur)

    # Field 206: floor the sum of per-payment (withholding_usd × fx) values.
    sum_withholding_eur = sum((line.withholding_eur for line in lines), Decimal(0))
    field_206 = _floor_to_euro(sum_withholding_eur)

    # Field 205 = 203 × 17.6% (the form computes this itself; we compute for cross-check)
    field_205 = int(Decimal(field_203) * TAUX_APPLICABLE_US / 100)

    # Field 207 = min(205, 206)
    field_207 = min(field_205, field_206)

    # Field 208 = 203 + 207
    field_208 = field_203 + field_207

    return Form2047Section200(
        country="États-Unis",
        field_203=field_203,
        field_204=TAUX_APPLICABLE_US,
        field_205=field_205,
        field_206=field_206,
        field_207=field_207,
        field_208=field_208,
        total_gross_usd=total_gross_usd,
        total_withholding_usd=total_withholding_usd,
        total_net_usd=total_net_usd,
    )
