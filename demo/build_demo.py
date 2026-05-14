"""Build a demo declaration.html with anonymized example data.

The real pipeline reads CSV + statement.pdf. Faking a broker statement PDF
is painful, so this script bypasses the PDF parser and constructs the parsed
objects (Sale, DividendPayment, etc.) directly with made-up values.

Run:  uv run python demo/build_demo.py [YEAR]
Output: demo/output/declaration.html

If YEAR is omitted, defaults to DEFAULT_DEMO_YEAR below.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Make `impots` importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "script" / "src"))

from impots.abattement import group_sales
from impots.dividends import build_dividend_lines, build_form_2047
from impots.fx import FxRates
from impots.sales import StockSale
from impots.statement import DividendPayment
from impots.web.render import render_declaration


DEFAULT_DEMO_YEAR = 2024

# Anonymised fictional sales — month/day are fixed, year is filled in at build
# time. Order: chronological by execution date.
DEMO_SALES_INPUT = [
    # (month, day, order_number, plan, fund, qty, price_usd, cost_basis_usd)
    (2, 12, "SALE-001", "RSU Class A", "ACMA - NASDAQ", 50,
     Decimal("185.50"), Decimal("1200.00")),
    (4, 3,  "SALE-002", "RSU Class B", "ACMB - NASDAQ",  100,
     Decimal("162.30"), Decimal("1500.00")),
    (7, 17, "SALE-003", "RSU Class A", "ACMA - NASDAQ", 200,
     Decimal("210.00"), Decimal("4800.00")),
    (11, 11, "SALE-004", "RSU Class A", "ACMA - NASDAQ", 150,
     Decimal("225.75"), Decimal("3600.00")),
]

# Made-up quarterly dividend payments. Same pattern: (month, day, fund, gross, withholding).
DEMO_DIVIDENDS = [
    (3, 17, "ACMA - NASDAQ", Decimal("250.00"), Decimal("37.50")),
    (3, 17, "ACMB - NASDAQ",  Decimal("40.00"),  Decimal("6.00")),
    (6, 16, "ACMA - NASDAQ", Decimal("265.00"), Decimal("39.75")),
    (6, 16, "ACMB - NASDAQ",  Decimal("38.00"),  Decimal("5.70")),
    (9, 15, "ACMA - NASDAQ", Decimal("285.00"), Decimal("42.75")),
    (9, 15, "ACMB - NASDAQ",  Decimal("36.00"),  Decimal("5.40")),
    (12, 15, "ACMA - NASDAQ", Decimal("310.00"), Decimal("46.50")),
    (12, 15, "ACMB - NASDAQ",  Decimal("34.00"),  Decimal("5.10")),
]


def build_demo(year: int = DEFAULT_DEMO_YEAR) -> None:
    fx = FxRates.load()  # uses cached ECB rates

    sales: list[StockSale] = []
    for month, day, order, plan, fund, qty, price, cost in DEMO_SALES_INPUT:
        exec_date = date(year, month, day)
        sales.append(
            StockSale(
                execution_date=exec_date,
                order_number=order,
                plan=plan,
                fund=fund,
                quantity=qty,
                sell_price_usd_per_share=price,
                cost_basis_usd=cost,
                fx_rate=fx.rate(exec_date),
            )
        )

    dividends = [
        DividendPayment(date=date(year, m, d), fund=f, gross_usd=g, withholding_usd=w)
        for m, d, f, g, w in DEMO_DIVIDENDS
    ]
    dividend_lines = build_dividend_lines(dividends=dividends, fx=fx)
    form_2047 = build_form_2047(dividend_lines)
    grouping = group_sales(sales)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "declaration.html"

    render_declaration(
        year=year,
        sales=sales,
        dividend_lines=dividend_lines,
        form_2047=form_2047,
        bloc1133=grouping,
        output_path=output_path,
        fx_source="ECB / Banque de France (demo: anonymised values)",
    )
    print(f"Wrote {output_path} (year={year})")
    print(f"  {len(sales)} sales, {len(dividends)} dividend payments")
    print(f"  Total gain USD: ${sum(s.gain_usd for s in sales):,.2f}")
    print(f"  Total gain EUR: €{sum(s.gain_eur for s in sales):,.0f}")
    print(f"  Total abattement EUR: €{sum(s.abattement_eur for s in sales):,.0f}")


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DEMO_YEAR
    build_demo(year)
