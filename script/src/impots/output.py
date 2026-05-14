"""Write the 5 output CSVs + audit.txt for a year's declaration."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from .abattement import AbattementGrouping
from .dividends import DividendLine, Form2047Section200
from .sales import StockSale


def _fmt(d: Decimal | int | None, places: int | None = None) -> str:
    if d is None:
        return ""
    if places is None:
        return str(d)
    return f"{float(d):.{places}f}"


def _fmt_date(d) -> str:
    return d.isoformat()


def write_stock_sales(path: Path, sales: list[StockSale]) -> None:
    """Per-sale audit view: one row per sale, all USD + EUR values."""
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "Sell date", "Order number", "Plan", "Quantity",
            "Sell price USD", "Cost basis USD", "Cost/share USD",
            "Gain USD",
            "FX rate (USD→EUR)",
            "Sell price EUR/share", "Total sell EUR",
            "Cost/share EUR", "Total cost EUR",
            "Gain EUR", "Abattement rate", "Abattement EUR",
        ])
        for s in sales:
            writer.writerow([
                _fmt_date(s.execution_date),
                s.order_number,
                s.plan,
                s.quantity,
                _fmt(s.sell_price_usd_per_share, 2),
                _fmt(s.cost_basis_usd, 2),
                _fmt(s.cost_per_share_usd, 4),
                _fmt(s.gain_usd, 2),
                _fmt(s.fx_rate, 6),
                _fmt(s.sell_price_eur_per_share, 2),
                _fmt(s.total_sell_eur, 0),
                _fmt(s.cost_per_share_eur, 2),
                _fmt(s.total_cost_eur, 0),
                _fmt(s.gain_eur, 0),
                _fmt(s.abattement_rate, 2),
                _fmt(s.abattement_eur, 0),
            ])


def write_form_2074_fields(path: Path, sales: list[StockSale]) -> None:
    """Per-sale form 2074 cadre 5 § 510 fields, in the order entered.

    Includes the typically-zero fee fields (F517, F522) and the form's computed
    subtotals (F518, F523) so the output maps 1-to-1 to the form.
    """
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "F511 Nommez les titres",
            "F512 Date de la cession",
            "F514 Valeur unitaire de cession EUR",
            "F515 Nombre de titres",
            "F516 Montant global EUR (514×515)",
            "F517 Frais de cession EUR",
            "F518 Prix de cession net EUR (516−517)",
            "F520 Prix d'acquisition unitaire EUR",
            "F521 Prix d'acquisition global EUR",
            "F522 Frais d'acquisition EUR",
            "F523 Prix de revient EUR (521+522)",
            "F524 Résultat EUR (518−523)",
        ])
        for s in sales:
            writer.writerow([
                s.description,
                s.execution_date.strftime("%d/%m/%Y"),
                _fmt(s.sell_price_eur_per_share, 2),
                s.quantity,
                _fmt(s.total_sell_eur, 0),
                _fmt(s.frais_cession_eur, 0),
                _fmt(s.prix_cession_net_eur, 0),
                _fmt(s.cost_per_share_eur, 2),
                _fmt(s.total_cost_eur, 0),
                _fmt(s.frais_acquisition_eur, 0),
                _fmt(s.prix_revient_eur, 0),
                _fmt(s.gain_eur, 0),
            ])


def write_form_2074_abt_fiche(path: Path, sales: list[StockSale]) -> None:
    """Per-sale entries for the fiche 2074-ABT helper.

    The fiche has 2 slots per page and supports unlimited pages — one slot per
    sale is fine, no grouping needed at this stage. The N08 (abattement) output
    of each slot feeds bloc 1133 of form 2074.

    Field mapping (notice 2074-ABT page 2):
      N01 = description of the security
      N02 = plus-value (= Field 524 from cadre 5)
      N03 = number of titres sold
      N05 = plus-value in the bracket matching the sale's holding period
      N07 = sale.abattement_rate × N05 (computed, shown with decimal)
      N08 = round-half-up(N07) — final abattement entered on form 2074 bloc 1133
    """
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "Slot", "N01 Désignation",
            "N02 Plus-value EUR", "N03 Nombre titres",
            "N05 Plus-value bracket EUR", "N06 Rate", "N07 Abattement (brut)",
            "N08 Abattement (arrondi)",
        ])
        slot_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for i, sale in enumerate(sales):
            slot = f"Titre {slot_letters[i]}"
            n07_brut = sale.abattement_rate * sale.gain_eur
            writer.writerow([
                slot,
                sale.description,
                _fmt(sale.gain_eur, 0),
                sale.quantity,
                _fmt(sale.gain_eur, 0),
                _fmt(sale.abattement_rate, 2),
                _fmt(n07_brut, 2),
                _fmt(sale.abattement_eur, 0),
            ])


def write_form_2074_bloc1133(path: Path, grouping: AbattementGrouping) -> None:
    """Form 2074 cadre 11 bloc 1133 — the 3-slot compensation table.

    Each line aggregates one or more fiche slots from `form_2074_abt_fiche.csv`.
    Three slots (Titres A/B/C) per abattement category; this tool currently
    only emits the "droit commun" column (col F).
    """
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "Slot", "Description", "Sales in slot",
            "Total gain EUR (col A/E)", "Abattement EUR (col F)",
        ])
        for slot in grouping.slots:
            constituents = "; ".join(
                f"{s.execution_date.isoformat()} {s.plan} qty={s.quantity}"
                for s in slot.constituent_sales
            )
            writer.writerow([
                slot.name,
                slot.description,
                constituents,
                _fmt(slot.total_gain_eur, 0),
                _fmt(slot.total_abattement_eur, 0),
            ])
        writer.writerow([])
        writer.writerow([
            "Totaux",
            "Sum of all slots",
            f"{len(_flatten(grouping))} sales total",
            _fmt(grouping.total_gain_eur, 0),
            _fmt(grouping.total_abattement_eur, 0),
        ])
        writer.writerow([])
        writer.writerow(["Report to:", "case 3VG", "(total gain after compensation)", "", ""])
        writer.writerow(["Report to:", "case 3SG", "(total abattement de droit commun)", "", ""])


def _flatten(grouping: AbattementGrouping):
    out = []
    for slot in grouping.slots:
        out.extend(slot.constituent_sales)
    return out


def write_dividends_raw(path: Path, lines: list[DividendLine]) -> None:
    """Per-payment audit view of dividends."""
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "Payment date", "Fund",
            "Gross USD", "Withholding USD", "Net USD",
            "FX rate (USD→EUR)",
            "Gross EUR", "Withholding EUR", "Net EUR",
        ])
        for line in lines:
            writer.writerow([
                _fmt_date(line.payment.date),
                line.payment.fund,
                _fmt(line.gross_usd, 2),
                _fmt(line.withholding_usd, 2),
                _fmt(line.net_usd, 2),
                _fmt(line.fx_rate, 6),
                _fmt(line.gross_eur, 2),
                _fmt(line.withholding_eur, 2),
                _fmt(line.net_eur, 2),
            ])


def write_form_2047(path: Path, form: Form2047Section200) -> None:
    """Aggregated single-country (États-Unis) entry for form 2047 section 200."""
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "F202 Pays",
            "F203 Montant net encaissé (EUR)",
            "F204 Taux applicable %",
            "F205 Résultat (=203×204%)",
            "F206 Impôt supporté à l'étranger (EUR)",
            "F207 Crédit d'impôt retenu (=min(205,206))",
            "F208 Revenus crédit d'impôt inclus (=203+207)",
        ])
        writer.writerow([
            form.country,
            form.field_203,
            _fmt(form.field_204, 1),
            form.field_205,
            form.field_206,
            form.field_207,
            form.field_208,
        ])
        writer.writerow([])
        writer.writerow(["Audit (USD source totals)"])
        writer.writerow(["Total gross dividends USD", _fmt(form.total_gross_usd, 2)])
        writer.writerow(["Total withholding USD", _fmt(form.total_withholding_usd, 2)])
        writer.writerow(["Total net USD", _fmt(form.total_net_usd, 2)])


def write_audit(
    path: Path,
    *,
    year: int,
    sales: list[StockSale],
    dividend_lines: list[DividendLine],
    form_2047: Form2047Section200,
    grouping: AbattementGrouping,
    fx_source: str = "ECB historical reference rates (mirrored by Banque de France)",
) -> None:
    """Human-readable audit summary."""
    lines: list[str] = []
    lines.append(f"# Tax declaration audit — fiscal year {year}")
    lines.append("")
    lines.append(f"FX rate source: {fx_source}")
    lines.append("")
    lines.append("## Stock sales")
    lines.append(f"  Sales: {len(sales)}")
    total_gain_usd = sum((s.gain_usd for s in sales), Decimal(0))
    total_gain_eur = sum((s.gain_eur for s in sales), Decimal(0))
    total_abat_eur = sum((s.abattement_eur for s in sales), Decimal(0))
    lines.append(f"  Total gain USD: ${total_gain_usd:,.2f}")
    lines.append(f"  Total gain EUR: €{total_gain_eur:,.2f}")
    lines.append(f"  Total abattement EUR: €{total_abat_eur:,.0f}")
    rates = sorted({s.abattement_rate for s in sales})
    rate_str = ", ".join(f"{int(r*100)}%" for r in rates)
    lines.append(f"  Rate(s) applied: {rate_str if rate_str else 'n/a'}")
    lines.append(f"  Net taxable plus-value EUR: €{total_gain_eur - total_abat_eur:,.2f}")
    lines.append("")
    lines.append("## Abattement grouping (Form 2074-ABT line 1133)")
    for slot in grouping.slots:
        n = len(slot.constituent_sales)
        lines.append(f"  {slot.name}: {slot.description} ({n} sale{'s' if n > 1 else ''})")
        lines.append(f"    gain EUR: €{slot.total_gain_eur:,.2f}  abattement: €{slot.total_abattement_eur:,.0f}")
    lines.append("")
    lines.append("## Dividends")
    lines.append(f"  Payments: {len(dividend_lines)}")
    lines.append(f"  Total gross USD: ${form_2047.total_gross_usd:,.2f}")
    lines.append(f"  Total withholding USD: ${form_2047.total_withholding_usd:,.2f}")
    lines.append(f"  Total net USD: ${form_2047.total_net_usd:,.2f}")
    lines.append(f"  Form 2047 entry (États-Unis): "
                 f"F203={form_2047.field_203}  F206={form_2047.field_206}  "
                 f"F207={form_2047.field_207}  F208={form_2047.field_208}")
    lines.append("")
    lines.append("## Cross-checks")
    lines.append("  1042-S Box 2 (gross income) should match Total gross USD.")
    lines.append("  1042-S Box 7a (withholding) should match Total withholding USD.")
    lines.append("")
    lines.append("## Caveats")
    lines.append("  * Field 520 (prix d'acquisition unitaire) uses weighted average cost")
    lines.append("    across all source lots. The notice 2074 § 510 suggests identifiable")
    lines.append("    titres (lot-tagged shares) could be entered per-lot, which would")
    lines.append("    split multi-lot sales into multiple form lines. The practical")
    lines.append("    taxable result is identical when all lots within a sale qualify for")
    lines.append("    the same abattement rate.")
    lines.append("  * Rounding: F516 / F521 / F524 / Field 1133 use ROUND_HALF_UP to whole")
    lines.append("    euros, matching the fiche 2074-ABT N08 paper-form convention.")
    lines.append("    F514 / F520 use 2 decimals (unit prices).")
    path.write_text("\n".join(lines) + "\n")
