"""Command-line entry point.

Usage:
    uv run build-declaration <year> --all-acquired-before YYYY-MM-DD
    uv run build-declaration <year> --all-acquired-before YYYY-MM-DD --data-dir /path/to/data

The `--all-acquired-before` flag is the recommended path: it makes the
abattement rate per sale derive from the holding period (sale_date −
cutoff_date), conservatively. Omitting it falls back to assuming 65 %
across the board, which is only safe if you've verified every sold share
qualifies — the tool prints a warning when you do.

Reads from <data-dir>/{year}/input/ and writes to <data-dir>/{year}/output/.
Default --data-dir is <repo>/personal-data/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from .abattement import group_sales
from .dividends import build_dividend_lines, build_form_2047
from .fx import FxRates
from .lot_attribution import attribute_sales, compute_consumed_lots
from .output import (
    write_audit,
    write_dividends_raw,
    write_form_2047,
    write_form_2074_abt_fiche,
    write_form_2074_bloc1133,
    write_form_2074_fields,
    write_stock_sales,
)
from .sales import apply_lot_breakdown, build_sales
from .statement import parse as parse_statement
from .web.render import render_declaration
from .withdrawals import parse as parse_withdrawals


def _repo_root() -> Path:
    # script/src/impots/cli.py → repo root is 3 levels up
    return Path(__file__).parent.parent.parent.parent


def _default_data_dir() -> Path:
    return _repo_root() / "personal-data"


def _parse_iso_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}") from e


_NON_SALES_CSV_HINTS = ("wire",)


def _discover_sales_csv(input_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise FileNotFoundError(f"--sales-csv {explicit} does not exist")
        return explicit
    csvs = sorted(input_dir.glob("*.csv"))
    # Filter out CSVs that the broker bundles alongside the sales report but
    # which don't contain share-sale rows (e.g., MS's "Withdrawal Wire Report").
    sales_csvs = [
        c for c in csvs
        if not any(hint in c.name.lower() for hint in _NON_SALES_CSV_HINTS)
    ]
    if len(sales_csvs) == 1:
        return sales_csvs[0]
    if not sales_csvs:
        raise FileNotFoundError(
            f"No CSV files in {input_dir}. Place your broker's sales report there, "
            f"or pass --sales-csv path/to/file.csv explicitly."
        )
    names = ", ".join(c.name for c in sales_csvs)
    raise FileNotFoundError(
        f"Multiple candidate CSV files in {input_dir} ({names}). "
        f"Pass --sales-csv to pick one explicitly."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build French tax declaration inputs from a foreign-broker stock statement.",
    )
    parser.add_argument("year", type=int, help="Fiscal year (e.g., 2025)")
    parser.add_argument(
        "--data-dir",
        "-d",
        type=Path,
        default=_default_data_dir(),
        help=(
            "Directory holding per-year subfolders. Each year directory has an "
            "input/ (CSV + statement.pdf) and an output/ (generated) subfolder. "
            "Default: <repo>/personal-data/"
        ),
    )
    parser.add_argument(
        "--sales-csv",
        type=Path,
        default=None,
        help=(
            "Path to the sales CSV. If omitted, auto-discovers the single *.csv "
            "file in <data-dir>/<year>/input/."
        ),
    )
    parser.add_argument(
        "--all-acquired-before",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Declare that every share lot in your portfolio was acquired strictly "
            "before this date. The tool then computes per-sale abattement rate "
            "(0%% / 50%% / 65%%) from sale_date − cutoff_date. Conservative: never "
            "over-claims. Default (omitted): assume every sale qualifies for the "
            "65%% rate — only safe if you've verified the lot table yourself."
        ),
    )
    parser.add_argument(
        "--prior-statement",
        type=Path,
        default=None,
        help=(
            "Path to the previous year's statement.pdf. If provided (or if "
            "auto-discovered at <data-dir>/<year-1>/input/statement.pdf), the "
            "tool reconciles prior- vs current-year lot tables to determine "
            "exactly which lots each sale consumed (FIFO), and applies the "
            "abattement rate per lot. This is the most accurate mode — overrides "
            "--all-acquired-before."
        ),
    )
    parser.add_argument(
        "--refresh-fx",
        action="store_true",
        help="Force re-fetching FX rates from ECB (ignores local cache).",
    )
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir
    year_dir = data_dir / str(args.year)
    input_dir = year_dir / "input"
    output_dir = year_dir / "output"

    if not input_dir.exists():
        print(f"error: input directory {input_dir} does not exist", file=sys.stderr)
        print(
            f"\nExpected layout:\n"
            f"  {data_dir}/\n"
            f"    {args.year}/input/<sales-report>.csv\n"
            f"    {args.year}/input/statement.pdf\n",
            file=sys.stderr,
        )
        return 1

    try:
        sales_csv = _discover_sales_csv(input_dir, args.sales_csv)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    statement_pdf = input_dir / "statement.pdf"
    if not statement_pdf.exists():
        print(f"error: missing required input file {statement_pdf}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-discover prior-year statement for lot reconciliation.
    prior_statement_pdf = args.prior_statement
    if prior_statement_pdf is None:
        candidate = data_dir / str(args.year - 1) / "input" / "statement.pdf"
        if candidate.exists():
            prior_statement_pdf = candidate

    print(f"Loading inputs from {input_dir} ...")
    print(f"  sales CSV:     {sales_csv.name}")
    print(f"  statement PDF: {statement_pdf.name}")
    if prior_statement_pdf:
        print(f"  prior PDF:     {prior_statement_pdf} (lot FIFO attribution)")
    elif args.all_acquired_before:
        print(f"  cutoff date:   {args.all_acquired_before} (per-sale rate)")
    else:
        print(
            "  WARNING: no --prior-statement or --all-acquired-before — assuming\n"
            "           every sale qualifies for 65 %. Only safe if every sold share\n"
            "           came from a lot vested ≥ 8 years before the sale date AND\n"
            "           before 2018-01-01. See docs/USER_GUIDE.md → Acquisition dates.",
            file=sys.stderr,
        )
    withdrawals = parse_withdrawals(sales_csv)
    statement = parse_statement(statement_pdf)
    fx = FxRates.load(refresh=args.refresh_fx)

    print(f"Computing ...")
    sales = build_sales(
        withdrawals=withdrawals,
        statement=statement,
        fx=fx,
        acquired_before=args.all_acquired_before,
    )

    if prior_statement_pdf:
        prior = parse_statement(prior_statement_pdf)
        consumed = compute_consumed_lots(prior.lots, statement.lots)
        attributions = attribute_sales(sales=sales, consumed_lots=consumed)
        breakdown = {a.order_number: tuple(a.chunks) for a in attributions}
        sales = apply_lot_breakdown(sales, breakdown)
        n_chunks = sum(len(a.chunks) for a in attributions)
        print(
            f"  lot attribution: {len(consumed)} consumed lots → {n_chunks} chunks "
            f"across {len(attributions)} sales"
        )
    dividend_lines = build_dividend_lines(dividends=statement.dividends, fx=fx)
    form_2047 = build_form_2047(dividend_lines)
    grouping = group_sales(sales)

    print(f"Writing outputs to {output_dir} ...")
    write_stock_sales(output_dir / "stock_sales.csv", sales)
    write_form_2074_fields(output_dir / "form_2074_fields.csv", sales)
    write_form_2074_abt_fiche(output_dir / "form_2074_abt_fiche.csv", sales)
    write_form_2074_bloc1133(output_dir / "form_2074_bloc1133.csv", grouping)
    write_dividends_raw(output_dir / "dividends_raw.csv", dividend_lines)
    write_form_2047(output_dir / "form_2047.csv", form_2047)
    write_audit(
        output_dir / "audit.txt",
        year=args.year,
        sales=sales,
        dividend_lines=dividend_lines,
        form_2047=form_2047,
        grouping=grouping,
    )
    render_declaration(
        year=args.year,
        sales=sales,
        dividend_lines=dividend_lines,
        form_2047=form_2047,
        bloc1133=grouping,
        output_path=output_dir / "declaration.html",
    )

    print(f"Done. Generated:")
    try:
        rel_root = _repo_root()
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                print(f"  {f.relative_to(rel_root)}")
    except ValueError:
        # output_dir isn't under repo (custom --data-dir outside repo)
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
