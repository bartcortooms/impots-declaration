"""Parse the per-sale activity CSV from the broker.

Each row is either a share sale or a cash withdrawal (Plan='Cash'). Cash
rows are dividend wire-outs to the user's bank — not taxable events on
their own (see notes.md). The script filters those out.

The CSV shape this parser expects matches the Morgan Stanley Activity
Report; adapting to other brokers means changing the column names and
the date format here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Optional Plan→Fund hint, used when the parser hasn't joined yet to the
# canonical fund name from statement.pdf. Add entries here if your broker
# uses Plan strings the statement doesn't.
PLAN_TO_FUND_HINT = {
    "Cash": "Cash - USD",
}


@dataclass(frozen=True)
class WithdrawalRow:
    """One row from the activity CSV (after filtering out trailing disclaimer lines)."""

    execution_date: date  # trade date
    order_number: str
    plan: str  # broker-specific (e.g., 'RSU Class A', 'Class B', 'Cash')
    fund: str  # placeholder; real fund comes via the join with statement.pdf
    price_usd: Decimal  # share price; $1.00 for Cash wire-outs
    quantity: Decimal  # negative in the CSV; we store positive
    net_amount_usd: Decimal

    @property
    def is_share_sale(self) -> bool:
        return self.plan != "Cash"


def _parse_money(s: str) -> Decimal:
    cleaned = s.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return Decimal(0)
    return Decimal(cleaned)


def parse(csv_path: Path | str) -> list[WithdrawalRow]:
    rows: list[WithdrawalRow] = []
    with open(csv_path, newline="") as fp:
        reader = csv.DictReader(fp)
        for raw in reader:
            execution_date_str = raw.get("Execution Date", "")
            if not execution_date_str or not execution_date_str[0].isdigit():
                # Trailing disclaimer line or blank
                continue
            plan = raw["Plan"]
            rows.append(
                WithdrawalRow(
                    execution_date=datetime.strptime(execution_date_str, "%d-%b-%Y").date(),
                    order_number=raw["Order Number"],
                    plan=plan,
                    fund=PLAN_TO_FUND_HINT.get(plan, plan),
                    price_usd=_parse_money(raw["Price"]),
                    quantity=abs(_parse_money(raw["Quantity"])),
                    net_amount_usd=_parse_money(raw["Net Amount"]),
                )
            )
    return rows


def share_sales(rows: list[WithdrawalRow]) -> list[WithdrawalRow]:
    """Filter to actual share sales (exclude Cash dividend wire-outs)."""
    return [r for r in rows if r.is_share_sale]
