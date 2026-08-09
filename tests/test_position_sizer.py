"""
Tests for nestquant.portfolio.position_sizer module.
"""

import pytest

from nestquant.portfolio.position_sizer import (
    DEFAULT_SNAPSHOT,
    QuoteSnapshot,
    compute_position_size,
    lot_size_by_risk,
    pip_size_for_pair,
    pip_value_per_lot,
    required_margin,
    round_lot_to_step,
)


class TestPipSizeForPair:
    def test_usd_pair(self):
        assert pip_size_for_pair("EUR/USD") == 0.0001

    def test_jpy_quote(self):
        assert pip_size_for_pair("USD/JPY") == 0.01
        assert pip_size_for_pair("GBP/JPY") == 0.01

    def test_cross_pair(self):
        assert pip_size_for_pair("EUR/GBP") == 0.0001
        assert pip_size_for_pair("AUD/NZD") == 0.0001


class TestPipValuePerLot:
    def test_eurusd(self):
        val = pip_value_per_lot("EUR/USD")
        # EUR/USD: pip * lot * USD_per_EUR = 0.0001 * 100000 * 1.08 = ~10.80
        assert 9.0 < val < 12.0

    def test_usdjpy(self):
        val = pip_value_per_lot("USD/JPY")
        # USD/JPY: 0.01 * 100000 * 0.0067 = ~6.70
        assert 5.0 < val < 8.0

    def test_custom_snapshot(self):
        snap = QuoteSnapshot(usd_value={"USD": 1.0, "EUR": 1.0, "GBP": 1.0, "JPY": 0.01})
        val = pip_value_per_lot("EUR/USD", snap)
        # 0.0001 * 100000 * 1.0 = 10.0
        assert abs(val - 10.0) < 1e-10


class TestLotSizeByRisk:
    def test_basic_sizing(self):
        lot = lot_size_by_risk("EUR/USD", 0.0020, 3.0)
        # risk / (sl_distance * pip_value * 100) = 3.0 / (0.0020 / 0.0001 * 10)
        assert lot > 0

    def test_zero_sl_distance(self):
        lot = lot_size_by_risk("EUR/USD", 0.0, 3.0)
        assert lot == 0.0

    def test_zero_risk(self):
        lot = lot_size_by_risk("EUR/USD", 0.0020, 0.0)
        assert lot == 0.0


class TestRoundLotToStep:
    def test_round_up(self):
        assert round_lot_to_step(0.015) == 0.02

    def test_round_down(self):
        assert round_lot_to_step(0.011) == 0.01

    def test_below_min(self):
        assert round_lot_to_step(0.005) == 0.01

    def test_exact_step(self):
        assert round_lot_to_step(0.03) == 0.03


class TestRequiredMargin:
    def test_basic_margin(self):
        margin = required_margin("EUR/USD", 0.1, 100)
        # notional = 0.1 * 100000 * 1.08 = 10800
        # margin = 10800 / 100 = 108
        assert 50 < margin < 200

    def test_higher_leverage_less_margin(self):
        m1 = required_margin("EUR/USD", 0.1, 100)
        m2 = required_margin("EUR/USD", 0.1, 500)
        assert m2 < m1


class TestComputePositionSize:
    def test_basic_computation(self):
        result = compute_position_size(
            pair="EUR/USD",
            side="BUY",
            entry_price=1.1000,
            sl_price=1.0950,
            account_balance_usd=10000.0,
            risk_pct=0.01,
            leverage=100,
        )
        assert result.ok
        assert result.pair == "EUR/USD"
        assert result.side == "BUY"
        assert result.lot_size > 0
        assert result.volume_units > 0
        assert result.required_margin_usd > 0
        assert result.reject_reason is None

    def test_reject_high_margin(self):
        result = compute_position_size(
            pair="EUR/USD",
            side="BUY",
            entry_price=1.1000,
            sl_price=1.0950,
            account_balance_usd=100.0,
            risk_pct=0.50,
            leverage=10,
            margin_safety=0.5,
        )
        # With very high risk and low leverage, margin should be rejected
        assert not result.ok
        assert result.reject_reason is not None

    def test_sell_side(self):
        result = compute_position_size(
            pair="GBP/USD",
            side="SELL",
            entry_price=1.2600,
            sl_price=1.2650,
            account_balance_usd=10000.0,
            risk_pct=0.01,
            leverage=100,
        )
        assert result.ok
        assert result.side == "SELL"

    def test_max_lot_cap(self):
        result = compute_position_size(
            pair="EUR/USD",
            side="BUY",
            entry_price=1.1000,
            sl_price=1.0999,
            account_balance_usd=1000000.0,
            risk_pct=0.05,
            leverage=100,
            max_lot=1.0,
        )
        assert result.lot_size <= 1.0

    def test_jpy_pair(self):
        result = compute_position_size(
            pair="USD/JPY",
            side="BUY",
            entry_price=150.0,
            sl_price=149.50,
            account_balance_usd=10000.0,
            risk_pct=0.01,
            leverage=100,
        )
        assert result.ok
        assert result.pip_value_per_lot_usd > 0

    def test_sizing_deterministic(self):
        kwargs = dict(
            pair="EUR/USD", side="BUY", entry_price=1.1000,
            sl_price=1.0950, account_balance_usd=10000.0,
            risk_pct=0.01, leverage=100,
        )
        r1 = compute_position_size(**kwargs)
        r2 = compute_position_size(**kwargs)
        assert r1.lot_size == r2.lot_size
        assert r1.required_margin_usd == r2.required_margin_usd
