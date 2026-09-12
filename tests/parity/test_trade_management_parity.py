"""
NestQuant Strategy — Trade Management Parity Tests
===================================================

These tests verify that the production trade management modules
produce identical results to the research simulation code.

Test cases are derived from specific line traces of the research
engines (phase_s0, phase_s5_5, phase_s6).
"""

import os


import pytest
from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig, BreakevenManager
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig, MaxHoldManager
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig, TrailingStopManager
from nestquant.production.strategy.trade_management.manager import (
    TradeAction,
    TradeState,
    MarketUpdate,
    TradeDecision,
    TradeLifecycleManager,
)
from nestquant.production.strategy.trade_management.trailing_stop import _is_nan


class TestBreakevenParity:
    """Verify breakeven logic matches research code exactly."""

    def setup_method(self):
        self.manager = BreakevenManager(BreakevenConfig(enabled=True, trigger_r=0.8))

    def test_long_breakeven_triggers_at_0p8r(self):
        """Research: phase_s0 line 156-158."""
        # Entry 1.0, SL 0.98 (risk 20 pips), close 1.016 (profit 160 pips)
        # 160 pips >= 0.8 * 20 = 16 pips → trigger
        new_sl = self.manager.evaluate(
            direction=1,
            entry_price=1.0,
            current_sl=0.98,
            close=1.016,
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 1.0

    def test_long_breakeven_not_triggers_below_0p8r(self):
        """Profit too low."""
        new_sl = self.manager.evaluate(
            direction=1,
            entry_price=1.0,
            current_sl=0.98,
            close=1.0015,  # 15 pips < 16 pips threshold (0.8 * 20)
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 0.98

    def test_long_breakeven_guard_sl_already_at_entry(self):
        """If SL already at entry, no change."""
        new_sl = self.manager.evaluate(
            direction=1,
            entry_price=1.0,
            current_sl=1.0,  # Already at entry
            close=1.016,
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 1.0

    def test_short_breakeven_triggers_at_0p8r(self):
        """Research: phase_s5_5 line 213-215."""
        # Entry 1.0, SL 1.02 (risk 20 pips), close 0.984 (profit 160 pips)
        new_sl = self.manager.evaluate(
            direction=-1,
            entry_price=1.0,
            current_sl=1.02,
            close=0.984,
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 1.0

    def test_short_breakeven_not_triggers_below_0p8r(self):
        """Profit too low."""
        new_sl = self.manager.evaluate(
            direction=-1,
            entry_price=1.0,
            current_sl=1.02,
            close=0.9985,  # Profit 15 pips < 16 pips threshold (0.8 * 20)
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 1.02

    def test_breakeven_disabled(self):
        """When disabled, no change."""
        manager = BreakevenManager(BreakevenConfig(enabled=False))
        new_sl = manager.evaluate(
            direction=1,
            entry_price=1.0,
            current_sl=0.98,
            close=1.016,
            risk_pips=20.0,
            pip_size=0.0001,
        )
        assert new_sl == 0.98

    def test_breakeven_risk_zero(self):
        """No change when risk is zero."""
        new_sl = self.manager.evaluate(
            direction=1,
            entry_price=1.0,
            current_sl=0.98,
            close=1.016,
            risk_pips=0.0,
            pip_size=0.0001,
        )
        assert new_sl == 0.98


class TestMaxHoldParity:
    """Verify max hold logic matches research code exactly."""

    def setup_method(self):
        self.manager = MaxHoldManager(MaxHoldConfig(enabled=True, max_hold_days=7, bars_per_day=6))

    def test_max_hold_triggers_at_42_bars(self):
        """Research: phase_s0 line 146-151."""
        result = self.manager.evaluate(
            bars_held=42,
            close=1.01,
            risk_pips=20.0,
        )
        assert result.should_exit is True
        assert result.exit_price == 1.01
        assert result.exit_reason == "MH"

    def test_max_hold_not_triggers_before_42(self):
        """Not yet at limit."""
        result = self.manager.evaluate(
            bars_held=41,
            close=1.01,
            risk_pips=20.0,
        )
        assert result.should_exit is False

    def test_max_hold_disabled(self):
        """When disabled, no exit."""
        manager = MaxHoldManager(MaxHoldConfig(enabled=False))
        result = manager.evaluate(
            bars_held=100,
            close=1.01,
            risk_pips=20.0,
        )
        assert result.should_exit is False

    def test_max_hold_risk_zero(self):
        """No exit when risk is zero."""
        result = self.manager.evaluate(
            bars_held=42,
            close=1.01,
            risk_pips=0.0,
        )
        assert result.should_exit is False

    def test_max_hold_custom_days(self):
        """Different max hold period."""
        manager = MaxHoldManager(MaxHoldConfig(max_hold_days=3, bars_per_day=6))
        result = manager.evaluate(
            bars_held=18,
            close=1.01,
            risk_pips=20.0,
        )
        assert result.should_exit is True
        assert result.exit_reason == "MH"


class TestTrailingStopParity:
    """Verify trailing stop logic matches research code exactly."""

    def setup_method(self):
        self.manager = TrailingStopManager(TrailingStopConfig(enabled=True))

    def test_long_trailing_up(self):
        """Research: phase_s0 line 152-155."""
        new_sl = self.manager.evaluate(
            direction=1,
            current_sl=0.98,
            prev_swing_low=0.985,
            prev_swing_high=1.02,
        )
        assert new_sl == 0.985

    def test_long_trailing_down(self):
        """Swing low below current SL → no change."""
        new_sl = self.manager.evaluate(
            direction=1,
            current_sl=0.98,
            prev_swing_low=0.975,
            prev_swing_high=1.02,
        )
        assert new_sl == 0.98

    def test_long_trailing_nan_swing(self):
        """NaN swing level → no change."""
        new_sl = self.manager.evaluate(
            direction=1,
            current_sl=0.98,
            prev_swing_low=float('nan'),
            prev_swing_high=1.02,
        )
        assert new_sl == 0.98

    def test_short_trailing_down(self):
        """Research: phase_s5_5 line 210-212."""
        new_sl = self.manager.evaluate(
            direction=-1,
            current_sl=1.02,
            prev_swing_low=0.98,
            prev_swing_high=1.015,
        )
        assert new_sl == 1.015

    def test_short_trailing_up(self):
        """Swing high above current SL → no change."""
        new_sl = self.manager.evaluate(
            direction=-1,
            current_sl=1.02,
            prev_swing_low=0.98,
            prev_swing_high=1.025,
        )
        assert new_sl == 1.02

    def test_trailing_disabled(self):
        """When disabled, no change."""
        manager = TrailingStopManager(TrailingStopConfig(enabled=False))
        new_sl = manager.evaluate(
            direction=1,
            current_sl=0.98,
            prev_swing_low=0.985,
            prev_swing_high=1.02,
        )
        assert new_sl == 0.98


class TestTradeLifecycleManagerParity:
    """Verify full lifecycle matches research event ordering."""

    def setup_method(self):
        self.manager = TradeLifecycleManager()

    def test_long_sl_exits_before_tp(self):
        """SL takes priority over TP."""
        trade = TradeState(
            direction=1, entry_price=1.0, current_sl=0.98,
            take_profit=1.035, risk_pips=20.0, pip_size=0.0001,
            bars_held=5, entry_idx=0,
        )
        market = MarketUpdate(
            open=1.01, high=1.04, low=0.97, close=1.035,
            prev_swing_low=0.98, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.EXIT
        assert result.exit_reason == "SL"
        assert result.exit_price == 0.98

    def test_long_tp_exits_before_mh(self):
        """TP takes priority over MH."""
        trade = TradeState(
            direction=1, entry_price=1.0, current_sl=0.98,
            take_profit=1.035, risk_pips=20.0, pip_size=0.0001,
            bars_held=42, entry_idx=0,  # At max hold
        )
        market = MarketUpdate(
            open=1.01, high=1.04, low=0.99, close=1.035,
            prev_swing_low=0.98, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.EXIT
        assert result.exit_reason == "TP"
        assert result.exit_price == 1.035

    def test_long_mh_exits_at_close(self):
        """MH uses close as exit price."""
        trade = TradeState(
            direction=1, entry_price=1.0, current_sl=0.98,
            take_profit=1.035, risk_pips=20.0, pip_size=0.0001,
            bars_held=42, entry_idx=0,
        )
        market = MarketUpdate(
            open=1.01, high=1.02, low=0.99, close=1.015,
            prev_swing_low=0.98, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.EXIT
        assert result.exit_reason == "MH"
        assert result.exit_price == 1.015

    def test_long_trailing_then_breakeven(self):
        """Trailing runs before breakeven (same bar, no exit)."""
        trade = TradeState(
            direction=1, entry_price=1.0, current_sl=0.98,
            take_profit=1.035, risk_pips=20.0, pip_size=0.0001,
            bars_held=10, entry_idx=0,
        )
        # Swing low above SL → trailing moves up
        # Close high enough for breakeven to also trigger
        market = MarketUpdate(
            open=1.01, high=1.02, low=0.99, close=1.018,
            prev_swing_low=0.99, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.MOVE_STOP
        # Trailing moves to 0.99, then BE moves to 1.0
        assert result.new_sl == 1.0

    def test_short_sl_exits_before_tp(self):
        """SHORT SL takes priority."""
        trade = TradeState(
            direction=-1, entry_price=1.0, current_sl=1.02,
            take_profit=0.965, risk_pips=20.0, pip_size=0.0001,
            bars_held=5, entry_idx=0,
        )
        market = MarketUpdate(
            open=0.99, high=1.025, low=0.96, close=0.99,
            prev_swing_low=0.98, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.EXIT
        assert result.exit_reason == "SL"
        assert result.exit_price == 1.02

    def test_short_tp_exits(self):
        """SHORT TP trigger."""
        trade = TradeState(
            direction=-1, entry_price=1.0, current_sl=1.02,
            take_profit=0.965, risk_pips=20.0, pip_size=0.0001,
            bars_held=5, entry_idx=0,
        )
        market = MarketUpdate(
            open=0.99, high=1.01, low=0.96, close=0.97,
            prev_swing_low=0.98, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.EXIT
        assert result.exit_reason == "TP"
        assert result.exit_price == 0.965

    def test_hold_when_no_event(self):
        """No exit and no SL change → HOLD."""
        trade = TradeState(
            direction=1, entry_price=1.0, current_sl=0.98,
            take_profit=1.035, risk_pips=20.0, pip_size=0.0001,
            bars_held=5, entry_idx=0,
        )
        # close=1.001 → profit 10 pips < 16 pips threshold → no BE
        # prev_swing_low=0.97 < 0.98 → no trailing
        market = MarketUpdate(
            open=1.001, high=1.002, low=0.999, close=1.001,
            prev_swing_low=0.97, prev_swing_high=1.02,
        )
        result = self.manager.evaluate(trade, market)
        assert result.action == TradeAction.HOLD


class TestIsNaN:
    """Test NaN detection utility."""

    def test_nan_detected(self):
        assert _is_nan(float('nan')) is True

    def test_number_not_nan(self):
        assert _is_nan(1.0) is False

    def test_zero_not_nan(self):
        assert _is_nan(0.0) is False

    def test_negative_not_nan(self):
        assert _is_nan(-1.0) is False
