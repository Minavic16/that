"""
NestQuant S8.6.7.B — Fill-Aware Geometry Tests
=================================================

Proves that a deliberate fill-price shift propagates correctly
through every downstream component:

    Signal level ≠ Fill price
        → SL recalculated from fill
        → TP recalculated from fill
        → Risk = same (fixed distance)
        → Breakeven uses fill reference
        → R uses fill reference

This is the central acceptance test for S8.6.7.B.
"""

import os
from datetime import datetime, timezone, timedelta


import pytest
from nestquant.production.strategy.lifecycle import (
    Direction,
    LifecycleAction,
    LifecycleRegistry,
    MarketContext,
    RiskReconciliation,
    TradeGeometry,
)
from nestquant.production.strategy.lifecycle.contracts import PositionModificationRequest
from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig
from nestquant.production.execution.adapter import FakeExecutionAdapter


# ═══════════════════════════════════════════════════════════════
# TradeGeometry Unit Tests
# ═══════════════════════════════════════════════════════════════

class TestTradeGeometry:
    """Verify TradeGeometry builds correctly from fill price."""

    def test_long_geometry_from_fill(self):
        """LONG: SL below fill, TP above fill."""
        geo = TradeGeometry.from_fill(
            fill_price=1.10050,  # 5 pips above signal level
            stop_distance=0.00200,  # 20 pips
            rrr=3.5,
            pip_size=0.0001,
            direction=1,
        )
        assert geo.entry_price == 1.10050
        assert geo.stop_loss == 1.09850  # fill - 20 pips
        assert geo.take_profit == 1.10750  # fill + 70 pips
        assert geo.risk_pips == 20.0

    def test_short_geometry_from_fill(self):
        """SHORT: SL above fill, TP below fill."""
        geo = TradeGeometry.from_fill(
            fill_price=1.09950,  # 5 pips below signal level
            stop_distance=0.00200,
            rrr=3.5,
            pip_size=0.0001,
            direction=-1,
        )
        assert geo.entry_price == 1.09950
        assert geo.stop_loss == 1.10150  # fill + 20 pips
        assert geo.take_profit == 1.09250  # fill - 70 pips
        assert geo.risk_pips == 20.0

    def test_geometry_preserves_risk_distance(self):
        """Fixed stop_distance means risk_pips is invariant to fill shift."""
        geo1 = TradeGeometry.from_fill(
            fill_price=1.10000, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        geo2 = TradeGeometry.from_fill(
            fill_price=1.10050, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        # Risk is the same because stop_distance is fixed
        assert geo1.risk_pips == geo2.risk_pips == 20.0
        # But SL and TP shifted with fill
        assert geo2.stop_loss == geo1.stop_loss + 0.00050
        assert geo2.take_profit == geo1.take_profit + 0.00050

    def test_unrealized_r_uses_fill_reference(self):
        """R calculation uses fill as entry, not signal level."""
        geo = TradeGeometry.from_fill(
            fill_price=1.10050, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        # +10 pips from fill = 0.5R
        r = geo.unrealized_r(1.10150)
        assert r == pytest.approx(0.5, abs=1e-10)

    def test_unrealized_r_not_from_signal(self):
        """R uses fill price, NOT signal level."""
        geo = TradeGeometry.from_fill(
            fill_price=1.10050, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        # If R used signal level (1.10000), +150 pips = 0.75R
        # But R uses fill (1.10050), +100 pips = 0.5R
        r = geo.unrealized_r(1.10150)
        assert r == pytest.approx(0.5, abs=1e-10)


# ═══════════════════════════════════════════════════════════════
# RiskReconciliation Tests
# ═══════════════════════════════════════════════════════════════

class TestRiskReconciliation:
    """Verify risk reconciliation detects fill deviations."""

    def test_within_tolerance(self):
        """5 pip deviation within 5 pip tolerance."""
        rec = RiskReconciliation.from_reconciliation(
            expected_entry=1.10000,
            actual_entry=1.10050,
            stop_distance=0.00200,
            pip_size=0.0001,
            tolerance_pips=5.0,
        )
        assert rec.is_ok is True
        assert rec.entry_deviation_pips == pytest.approx(5.0, abs=1e-10)
        assert rec.severity == "OK"

    def test_exceeds_tolerance(self):
        """10 pip deviation exceeds 5 pip tolerance."""
        rec = RiskReconciliation.from_reconciliation(
            expected_entry=1.10000,
            actual_entry=1.10100,
            stop_distance=0.00200,
            pip_size=0.0001,
            tolerance_pips=5.0,
        )
        assert rec.is_ok is False
        assert rec.entry_deviation_pips == pytest.approx(10.0, abs=1e-10)
        assert rec.severity == "CRITICAL"

    def test_risk_deviation_zero_with_fixed_distance(self):
        """Fixed stop_distance means risk deviation is always 0."""
        rec = RiskReconciliation.from_reconciliation(
            expected_entry=1.10000,
            actual_entry=1.10100,
            stop_distance=0.00200,
            pip_size=0.0001,
            tolerance_pips=5.0,
        )
        assert rec.risk_deviation_pips == 0.0


# ═══════════════════════════════════════════════════════════════
# Shifted-Fill Lifecycle Replay
# ═══════════════════════════════════════════════════════════════

def _make_market(
    bar_index=1,
    o=1.1000, h=1.1010, l=1.0990, c=1.1005,
    prev_swing_low=1.0985,
    prev_swing_high=1.1015,
    minutes_offset=240,
) -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="H4",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes_offset * bar_index),
        bar_index=bar_index,
        open=o, high=h, low=l, close=c,
        previous_swing_low=prev_swing_low,
        previous_swing_high=prev_swing_high,
    )


class TestShiftedFillReplay:
    """Prove that a 5-pip fill shift propagates correctly."""

    def test_5pip_shift_long_lifecycle(self):
        """Signal level 1.10000, fill 1.10050, verify geometry."""
        registry = LifecycleRegistry(
            strategy_identity="shift_test",
            breakeven_config=BreakevenConfig(enabled=True, trigger_r=0.8),
            max_hold_config=MaxHoldConfig(enabled=True, max_hold_days=7, bars_per_day=6),
            trailing_config=TrailingStopConfig(enabled=True),
        )
        adapter = FakeExecutionAdapter()

        # Step 1: Build geometry from shifted fill
        # Signal: entry_level=1.10000, ATR=0.00100, stop_distance=0.00200
        # Broker fill: 1.10050 (5 pips higher)
        geometry = TradeGeometry.from_fill(
            fill_price=1.10050,  # ← actual fill, not signal level
            stop_distance=0.00200,
            rrr=3.5,
            pip_size=0.0001,
            direction=1,
        )

        # Verify geometry is built from fill
        assert geometry.entry_price == 1.10050
        assert geometry.stop_loss == 1.09850  # fill - 20 pips
        assert geometry.take_profit == 1.10750  # fill + 70 pips
        assert geometry.risk_pips == 20.0

        # Step 2: Register lifecycle with fill-based geometry
        registry.register_entry(
            trade_id="SHIFT001",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=geometry.entry_price,       # 1.10050 (fill)
            initial_sl=geometry.stop_loss,           # 1.09850 (from fill)
            take_profit=geometry.take_profit,        # 1.10750 (from fill)
            pip_size=geometry.pip_size,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

        # Step 3: Verify lifecycle uses fill-based state
        pos = registry.get_position("SHIFT001")
        assert pos.entry_price == 1.10050
        assert pos.current_sl == 1.09850
        assert pos.risk_pips == pytest.approx(20.0, abs=1e-10)

        # Step 4: Bar 1 — trailing check
        # prev_swing_low=1.0990 > current_sl=1.09850 → trailing moves SL to 1.0990
        market = _make_market(bar_index=1, o=1.1005, h=1.1020, l=1.1000, c=1.1018,
                              prev_swing_low=1.0990, prev_swing_high=1.1020)
        decisions = registry.evaluate_bar(market)
        # Commit pending SL (simulates broker confirmation)
        for d in decisions:
            if d.is_sl_move:
                registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        # Trailing moves SL up (not breakeven)
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.0990  # trailing moved SL

        # Step 5: Bar 2 — close=1.10220, profit from fill = 17 pips → breakeven triggers
        # (17 pips >= 16 pips threshold)
        market = _make_market(bar_index=2, o=1.1018, h=1.1025, l=1.1015, c=1.1022,
                              prev_swing_low=1.0995, prev_swing_high=1.1025)
        decisions = registry.evaluate_bar(market)
        for d in decisions:
            if d.is_sl_move:
                registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.10050  # entry price (breakeven)

        # Step 6: Verify breakeven used FILL price, not signal level
        pos = registry.get_position("SHIFT001")
        assert pos.breakeven_triggered is True
        assert pos.current_sl == 1.10050  # ← fill price, not 1.10000

    def test_5pip_shift_risk_reconciliation(self):
        """Verify risk reconciliation detects the 5-pip shift."""
        rec = RiskReconciliation.from_reconciliation(
            expected_entry=1.10000,  # signal level
            actual_entry=1.10050,    # broker fill
            stop_distance=0.00200,
            pip_size=0.0001,
            tolerance_pips=5.0,
        )
        assert rec.entry_deviation_pips == pytest.approx(5.0, abs=1e-10)
        assert rec.is_ok is True  # exactly at tolerance

    def test_10pip_shift_triggers_critical(self):
        """Verify large deviation triggers CRITICAL."""
        rec = RiskReconciliation.from_reconciliation(
            expected_entry=1.10000,
            actual_entry=1.10100,  # 10 pips off
            stop_distance=0.00200,
            pip_size=0.0001,
            tolerance_pips=5.0,
        )
        assert rec.severity == "CRITICAL"

    def test_sl_tp_shift_with_fill_preserves_geometry(self):
        """Both SL and TP shift by the same amount as fill."""
        geo_signal = TradeGeometry.from_fill(
            fill_price=1.10000, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        geo_fill = TradeGeometry.from_fill(
            fill_price=1.10050, stop_distance=0.00200,
            rrr=3.5, pip_size=0.0001, direction=1,
        )
        # Fill shifted +5 pips → SL and TP also shift +5 pips
        assert geo_fill.stop_loss == geo_signal.stop_loss + 0.00050
        assert geo_fill.take_profit == geo_signal.take_profit + 0.00050
        # Risk distance preserved
        assert geo_fill.risk_pips == geo_signal.risk_pips
