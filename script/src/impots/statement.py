"""Parse the broker's annual account summary PDF.

The current parser is written against the Morgan Stanley StockPlan Connect
"Account Summary" report (Full type, PDF, A4). The relevant sections are:
- page 1: account summary header (we skip — derivable from elsewhere)
- page 2: per-lot holdings as of year-end
- page 3: activity log (sales, dividends, withholdings, cash transfers)
- pages 3–N: per-sale withdrawal blocks (gross proceeds, fees, net proceeds)

Adapting to other brokers would mean replacing this module entirely with a
parser for that broker's PDF / CSV / API shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

ZWSP = "​"


def _clean(s: str | None) -> str:
    if s is None:
        return ""
    return s.replace(ZWSP, "").replace("\n", " ").strip()


def _parse_money(s: str) -> Decimal:
    """Parse '$1,234.56', '$-1,234.56', or '$1,234.56 USD' to Decimal. Empty/dash → 0."""
    cleaned = _clean(s).replace("$", "").replace(",", "").replace("USD", "").strip()
    if not cleaned or cleaned == "-":
        return Decimal(0)
    return Decimal(cleaned)


def _parse_date(s: str) -> date:
    """Parse 'DD-Mon-YYYY' (e.g. '17-Jun-2024') to date."""
    return datetime.strptime(_clean(s), "%d-%b-%Y").date()


def _parse_qty(s: str) -> Decimal:
    cleaned = _clean(s).replace(",", "")
    if not cleaned:
        return Decimal(0)
    return Decimal(cleaned)


@dataclass(frozen=True)
class Lot:
    """One row of the year-end holdings table."""

    fund: str  # broker-specific fund label, e.g. '<TICKER> - <EXCHANGE>'
    acquisition_date: date
    lot_id: str
    cost_basis_usd: Decimal
    cost_basis_per_share_usd: Decimal
    shares: int


@dataclass(frozen=True)
class Sale:
    """A 'Sale' row from the activity log. Cost basis comes from the Book Value column."""

    date: date
    fund: str
    quantity: int  # positive (we store qty sold)
    share_price_usd: Decimal
    cost_basis_usd: Decimal  # absolute value of Book Value column


@dataclass(frozen=True)
class DividendPayment:
    """A 'Dividend (Cash)' row, paired with its 'IRS Withholding' row.

    `gross_usd` is the dividend amount declared (the 'Dividend (Cash)' line).
    `withholding_usd` is the absolute value of the matching withholding line.
    Net = gross - withholding is what's actually credited to the user.
    """

    date: date
    fund: str
    gross_usd: Decimal
    withholding_usd: Decimal

    @property
    def net_usd(self) -> Decimal:
        return self.gross_usd - self.withholding_usd


@dataclass(frozen=True)
class WithdrawalBlock:
    """One of the per-sale 'Withdrawal on ...' blocks at the bottom of the statement.

    Primary use: links order numbers to fund/settlement. Detailed Gross/Net/Fee
    values span multiple pdfplumber-detected tables and are unreliable to parse;
    use the Activity Sale row and the Withdrawals CSV's Net Amount instead.
    """

    date: date  # trade date from block header
    reference_number: str  # 'WRC...-1EE' (sale) or 'WBC...-1EE' (cash wire)
    fund: str  # broker-specific fund label, e.g. '<TICKER> - <EXCHANGE>' or 'Cash - <CURRENCY>'
    settlement_date: date
    shares_sold: Decimal  # may be 0 for Cash withdrawals
    market_price_per_unit: Decimal | None  # higher precision than Activity row


@dataclass(frozen=True)
class Statement:
    period_start: date
    period_end: date
    lots: list[Lot]
    sales: list[Sale]
    dividends: list[DividendPayment]
    withdrawals: list[WithdrawalBlock]


def parse(pdf_path: Path | str) -> Statement:
    with pdfplumber.open(str(pdf_path)) as pdf:
        period_start, period_end = _parse_summary_period(pdf.pages[0])
        lots = _parse_holdings(pdf.pages[1])
        sales, dividends = _parse_activity(pdf.pages[2])
        withdrawals = _parse_withdrawal_blocks(pdf.pages)
    return Statement(
        period_start=period_start,
        period_end=period_end,
        lots=lots,
        sales=sales,
        dividends=dividends,
        withdrawals=withdrawals,
    )


def _parse_summary_period(page) -> tuple[date, date]:
    text = page.extract_text()
    m = re.search(r"Summary Period:\s*(\d{2}-\w{3}-\d{4})\s*to\s*(\d{2}-\w{3}-\d{4})", text)
    if not m:
        raise ValueError("Could not find summary period in page 1")
    return _parse_date(m.group(1)), _parse_date(m.group(2))


def _parse_holdings(page) -> list[Lot]:
    table = page.extract_tables()[0]
    lots = []
    for row in table:
        if not row or not row[0]:
            continue
        fund = _clean(row[0])
        if not fund.endswith("- NASDAQ"):
            # skip header rows ('Summary of...', 'Fund', 'Type of Money: ...') and totals
            continue
        acq_date = _parse_date(row[1])
        lot_id = _clean(row[2])
        # row[3]: 'Long Term' / 'Short Term' (we ignore — all are long term)
        # row[4]: Gain/Loss (USD) — derived, we don't keep
        cost_basis = _parse_money(row[5])
        cost_basis_per_share = _parse_money(row[6])
        shares = int(_parse_qty(row[7]))
        lots.append(
            Lot(
                fund=fund,
                acquisition_date=acq_date,
                lot_id=lot_id,
                cost_basis_usd=cost_basis,
                cost_basis_per_share_usd=cost_basis_per_share,
                shares=shares,
            )
        )
    return lots


def _parse_activity(page) -> tuple[list[Sale], list[DividendPayment]]:
    table = page.extract_tables()[0]
    sales: list[Sale] = []
    dividends: list[DividendPayment] = []

    current_fund: str | None = None
    pending_dividend: tuple[date, str, Decimal] | None = None  # (date, fund, gross)

    for row in table:
        if not row or not row[0]:
            continue
        first = _clean(row[0])
        if first.startswith("Fund:"):
            current_fund = first.removeprefix("Fund:").strip()
            pending_dividend = None
            continue
        activity = _clean(row[1])
        if not activity or first in ("Entry Date", "Activity"):
            continue
        if current_fund is None:
            continue

        if activity == "Sale":
            assert current_fund != "Cash - USD", f"unexpected sale under Cash fund: {row}"
            sales.append(
                Sale(
                    date=_parse_date(row[0]),
                    fund=current_fund,
                    quantity=abs(int(_parse_qty(row[4]))),
                    share_price_usd=_parse_money(row[5]),
                    cost_basis_usd=abs(_parse_money(row[6])),
                )
            )
        elif activity == "Dividend (Cash)":
            pending_dividend = (
                _parse_date(row[0]),
                current_fund,
                _parse_money(row[3]),
            )
        elif activity == "IRS Nonresident Alien Withholding":
            if pending_dividend is None:
                raise ValueError(f"Withholding row without preceding dividend: {row}")
            div_date, div_fund, gross = pending_dividend
            assert _parse_date(row[0]) == div_date
            assert current_fund == div_fund
            withholding = abs(_parse_money(row[3]))
            dividends.append(
                DividendPayment(
                    date=div_date,
                    fund=div_fund,
                    gross_usd=gross,
                    withholding_usd=withholding,
                )
            )
            pending_dividend = None

    if pending_dividend is not None:
        raise ValueError(f"Dividend without matching withholding: {pending_dividend}")

    return sales, dividends


_WITHDRAWAL_HEADER_RE = re.compile(r"^Withdrawal on (\w+ \d+, \d{4})$")


def _parse_withdrawal_blocks(pages) -> list[WithdrawalBlock]:
    blocks: list[WithdrawalBlock] = []
    # Each block is a small table. Iterate all tables on all pages,
    # filter those whose first row matches "Withdrawal on ...".
    for page in pages:
        for table in page.extract_tables():
            if not table:
                continue
            first = _clean(table[0][0])
            m = _WITHDRAWAL_HEADER_RE.match(first)
            if not m:
                continue
            blocks.append(_parse_withdrawal_block(table, m.group(1)))
    return blocks


def _parse_withdrawal_block(table, header_date_str: str) -> WithdrawalBlock:
    """Each block has key:value pairs, but pdfplumber returns labels and values
    concatenated by newlines in cells. The 5-column layout is:

        [labels_left, values_left, labels_right, None, values_right]

    e.g. row 1 has 'Reference Number:\\nSavings Plan:\\nFund\\n...' in col 0
    and the matching values like '<ref>\\n<plan>\\n<fund>\\n...' in col 1.
    """
    kv: dict[str, str] = {}

    def _zip_labels_values(label_cell: str | None, value_cell: str | None) -> None:
        if not label_cell or not value_cell:
            return
        labels = [line.rstrip(":").strip() for line in label_cell.replace(ZWSP, "").split("\n")]
        values = [line.replace(ZWSP, "").strip() for line in value_cell.split("\n")]
        for label, value in zip(labels, values):
            if label and value and label not in kv:
                kv[label] = value

    for row in table:
        # The key:value layout is always (labels_cell, value_cell) pairs in
        # adjacent non-None columns. pdfplumber sometimes inserts spacer None
        # columns. Walk through the row pairing each non-None labels cell
        # with the next non-None cell.
        non_none = [(i, c) for i, c in enumerate(row) if c is not None]
        i = 0
        while i + 1 < len(non_none):
            _, label_cell = non_none[i]
            _, value_cell = non_none[i + 1]
            if "\n" in (label_cell or "") and ":" in (label_cell or ""):
                _zip_labels_values(label_cell, value_cell)
                i += 2
            else:
                i += 1
        # Standard 2-col Description/Value rows (Gross Proceeds, etc.)
        cleaned = [_clean(c) for c in row]
        # Look for Description-style rows: [key, ..., value] with key not in labels above
        nonempty = [c for c in cleaned if c]
        if len(nonempty) == 2 and nonempty[0] not in ("Description", "Sale Breakdown", "Proceeds Breakdown"):
            key, val = nonempty
            if "USD" in val and key not in kv:
                kv[key] = val
        elif len(nonempty) == 2 and nonempty[0].startswith("Net Proceeds:"):
            # "Net Proceeds: $20,692.47 USD" sometimes appears as a single bottom cell
            m = re.match(r"Net Proceeds:\s*(.*)", nonempty[0])
            if m and "Net Proceeds" not in kv:
                kv["Net Proceeds"] = m.group(1)

    reference_number = kv.get("Reference Number", "")
    fund = kv.get("Fund", "").strip()
    settlement_date_str = kv.get("Settlement Date", "")
    shares_sold_str = kv.get("Shares Sold", "0")
    market_price_str = kv.get("Market Price Per Unit", "")

    # Header date — e.g., "March 19, 2024"
    block_date = datetime.strptime(header_date_str, "%B %d, %Y").date()

    return WithdrawalBlock(
        date=block_date,
        reference_number=reference_number,
        fund=fund,
        settlement_date=_parse_date(settlement_date_str) if settlement_date_str else block_date,
        shares_sold=_parse_qty(shares_sold_str) if shares_sold_str else Decimal(0),
        market_price_per_unit=(_parse_money(market_price_str.split()[0]) if market_price_str else None),
    )
