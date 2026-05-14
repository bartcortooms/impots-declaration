from datetime import date
from decimal import Decimal

from impots.fx import FxRates


def test_load_from_cache():
    """fx_cache.csv exists from previous run; loading should not require network."""
    fx = FxRates.load()
    rate = fx.rate(date(2024, 3, 19))
    assert Decimal("0.91") < rate < Decimal("0.93")


def test_weekend_falls_back_to_friday():
    fx = FxRates.load()
    # 16-Mar-2024 was a Saturday → should use Friday 15-Mar
    sat = fx.rate(date(2024, 3, 16))
    fri = fx.rate(date(2024, 3, 15))
    assert sat == fri


def test_close_to_external_reference_rate():
    """ECB rate should track common third-party reference rates within < 0.5%."""
    fx = FxRates.load()
    rate = fx.rate(date(2024, 3, 19))
    reference_value = Decimal("0.92053")
    diff_pct = abs(rate - reference_value) / reference_value * 100
    assert diff_pct < Decimal("0.5"), f"ECB {rate} vs reference {reference_value} diff {diff_pct}%"
