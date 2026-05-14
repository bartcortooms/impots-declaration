"""Render a self-contained HTML report from computed declaration data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ..abattement import AbattementGrouping
from ..dividends import DividendLine, Form2047Section200
from ..sales import StockSale


_TEMPLATES_PKG = "impots.web"
_TEMPLATES_DIR = "templates"
_STATIC_DIR = Path(__file__).parent / "static"


@dataclass(frozen=True)
class Form2074Page:
    """One page of form 2074 cadre 5 § 510 (main page + Complément CRVM pages).

    The main page holds Titres 1-3; subsequent Complément CRVM pages hold
    Titres 4-6, 7-9, etc.
    """

    start_index: int  # 1, 4, 7, …
    end_index: int    # 3, 6, 9, …
    sales: list[StockSale]


@dataclass(frozen=True)
class FicheSlot:
    """One slot of the fiche 2074-ABT (a single sale's abattement breakdown)."""

    letter: str  # A, B, C, …
    sale: StockSale
    n07: Decimal  # sale.abattement_rate × N05, with decimal precision (matches fiche)


@dataclass(frozen=True)
class FichePage:
    """A page of the fiche 2074-ABT, holding up to 2 slots."""

    slots: list[FicheSlot]


def _paginate_form_2074(sales: list[StockSale], per_page: int = 3) -> list[Form2074Page]:
    pages = []
    for i in range(0, len(sales), per_page):
        chunk = sales[i : i + per_page]
        pages.append(
            Form2074Page(
                start_index=i + 1,
                end_index=i + len(chunk),
                sales=chunk,
            )
        )
    return pages


_SLOT_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _paginate_fiche(sales: list[StockSale], per_page: int = 2) -> list[FichePage]:
    slots = [
        FicheSlot(
            letter=_SLOT_LETTERS[i],
            sale=sale,
            n07=sale.abattement_rate * sale.gain_eur,
        )
        for i, sale in enumerate(sales)
    ]
    pages = []
    for i in range(0, len(slots), per_page):
        pages.append(FichePage(slots=slots[i : i + per_page]))
    return pages


# Jinja filters --------------------------------------------------------------

def _fmt_int(value) -> str:
    """Format as integer with thousand separator (spaces, French style)."""
    if value is None:
        return ""
    n = int(round(float(value)))
    return f"{n:,}".replace(",", " ")


def _fmt_money(value) -> str:
    """Format as USD/EUR amount with 2 decimals."""
    if value is None:
        return ""
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")


def _fmt_decimal2(value) -> str:
    """Format with exactly 2 decimals, comma decimal separator."""
    if value is None:
        return ""
    return f"{float(value):.2f}".replace(".", ",")


def _fmt_decimal2_strip(value) -> str:
    """Format with up to 2 decimals, trailing zero stripped (matches fiche display)."""
    if value is None:
        return ""
    s = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _fmt_fx(value) -> str:
    """Format FX rate with 6 decimals."""
    if value is None:
        return ""
    return f"{float(value):.6f}".replace(".", ",")


def _fmt_pct(value) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f} %".replace(".", ",")


def _build_env() -> Environment:
    env = Environment(
        loader=PackageLoader(_TEMPLATES_PKG, _TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt_int"] = _fmt_int
    env.filters["fmt_money"] = _fmt_money
    env.filters["fmt_decimal2"] = _fmt_decimal2
    env.filters["fmt_decimal2_strip"] = _fmt_decimal2_strip
    env.filters["fmt_fx"] = _fmt_fx
    env.filters["fmt_pct"] = _fmt_pct
    return env


def render_declaration(
    *,
    year: int,
    sales: list[StockSale],
    dividend_lines: list[DividendLine],
    form_2047: Form2047Section200,
    bloc1133: AbattementGrouping,
    output_path: Path,
    fx_source: str = "ECB / Banque de France",
) -> None:
    """Render the full HTML declaration to `output_path` (self-contained file)."""
    env = _build_env()
    template = env.get_template("declaration.html")

    sales_sorted = sorted(sales, key=lambda s: s.execution_date)
    form_2074_pages = _paginate_form_2074(sales_sorted)
    fiche_pages = _paginate_fiche(sales_sorted)

    total_gain_usd = sum((s.gain_usd for s in sales_sorted), Decimal(0))
    total_gain_eur = sum((s.gain_eur for s in sales_sorted), Decimal(0))
    total_abattement_eur = sum((s.abattement_eur for s in sales_sorted), Decimal(0))
    totals = {
        "gain_usd": total_gain_usd,
        "gain_eur": total_gain_eur,
        "abattement_eur": total_abattement_eur,
        "taxable_eur": total_gain_eur - total_abattement_eur,
    }

    inline_css = (_STATIC_DIR / "style.css").read_text()
    inline_js = (
        (_STATIC_DIR / "steps.js").read_text()
        + "\n"
        + (_STATIC_DIR / "copy.js").read_text()
    )

    html = template.render(
        year=year,
        fx_source=fx_source,
        inline_css=inline_css,
        inline_js=inline_js,
        sales=sales_sorted,
        sales_total_gain_eur=total_gain_eur,
        sales_total_abattement_eur=total_abattement_eur,
        dividend_lines=dividend_lines,
        form_2047=form_2047,
        form_2074_pages=form_2074_pages,
        fiche_pages=fiche_pages,
        bloc1133=bloc1133,
        totals=totals,
    )
    output_path.write_text(html)
