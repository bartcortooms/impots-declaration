"""USD→EUR daily reference rates.

Source: ECB daily reference rate (republished by Banque de France as the
official "cours du change à Paris"; values are identical). The 2047 notice
says: "calculée d'après le cours du change à Paris au jour de l'encaissement".

ECB publishes a single rate per business day around 16:00 CET. For weekends
and holidays, we use the most recent prior business day's rate.

Rates are cached in fx_cache.csv to avoid re-fetching.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import requests

_ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
_NS = {"ex": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


def _cache_path() -> Path:
    return Path(__file__).parent.parent.parent / "fx_cache.csv"


def _fetch_ecb_history() -> dict[date, Decimal]:
    """Fetch ECB historical EUR→USD rates and invert to USD→EUR."""
    response = requests.get(_ECB_HIST_URL, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rates: dict[date, Decimal] = {}
    for time_cube in root.iterfind(".//ex:Cube[@time]", _NS):
        day = datetime.strptime(time_cube.get("time"), "%Y-%m-%d").date()
        for currency_cube in time_cube.iterfind("ex:Cube[@currency='USD']", _NS):
            eur_to_usd = Decimal(currency_cube.get("rate"))
            # USD→EUR is the reciprocal
            usd_to_eur = (Decimal(1) / eur_to_usd).quantize(Decimal("0.000001"))
            rates[day] = usd_to_eur
    return rates


def _load_cache() -> dict[date, Decimal]:
    path = _cache_path()
    if not path.exists():
        return {}
    rates: dict[date, Decimal] = {}
    with open(path, newline="") as fp:
        for row in csv.DictReader(fp):
            rates[date.fromisoformat(row["date"])] = Decimal(row["usd_to_eur"])
    return rates


def _save_cache(rates: dict[date, Decimal]) -> None:
    path = _cache_path()
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["date", "usd_to_eur"])
        for day in sorted(rates):
            writer.writerow([day.isoformat(), str(rates[day])])


class FxRates:
    """Lookup USD→EUR daily rates with cache and weekend/holiday fallback."""

    def __init__(self, rates: dict[date, Decimal]):
        self._rates = rates

    @classmethod
    def load(cls, *, refresh: bool = False) -> FxRates:
        cached = {} if refresh else _load_cache()
        if not cached:
            cached = _fetch_ecb_history()
            _save_cache(cached)
        return cls(cached)

    def rate(self, day: date) -> Decimal:
        """Return USD→EUR rate for `day`. If `day` is a weekend or holiday,
        falls back to the most recent prior business day with a published rate."""
        cursor = day
        while cursor >= date(1999, 1, 4):  # ECB euro start
            if cursor in self._rates:
                return self._rates[cursor]
            cursor -= timedelta(days=1)
        raise ValueError(f"No FX rate available on or before {day}")
