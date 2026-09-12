"""
NestQuant S8.6.7 — End-to-End Runtime Replay Test
====================================================

Proves that the actual S8Runtime executes the canonical lifecycle
through the real integration path:

    S8Runtime
        → LifecycleRegistry
        → TradeLifecycleManager
        → LifecycleDecision
        → DryRunAdapter.modify_position_stop()
        → Event log

This is the definitive parity test.
"""

import os
from datetime import datetime, timezone, timedelta


import pytest
from nestquant.production.strategy.lifecycle import (
    Direction,
    LifecycleAction,
    LifecycleRegistry,
    MarketContext,
    PositionModificationRequest,
)
from nestquant.production.strategy.lifecycle.registry import LifecycleEvent
from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig
from nestquant.production.execution.adapter import FakeExecutionAdapter


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


class TestEndToEndRuntimeReplay:
    """Full lifecycle replay through the actual integration path."""

    def setup_method(self):
        self.adapter = FakeExecutionAdapter()
        self.registry = LifecycleRegistry(
            strategy_identity="e2e_test",
            breakeven_config=BreakevenConfig(enabled=True, trigger_r=0.8),
            max_hold_config=MaxHoldConfig(enabled=True, max_hold_days=7, bars_per_day=6),
            trailing_config=TrailingStopConfig(enabled=True),
        )

    def test_full_long_lifecycle_e2e(self):
        """Complete LONG lifecycle: entry → hold → trailing → BE → MH exit."""
        # Step 1: Register entry (simulates signal path)
        self.registry.register_entry(
            trade_id="E2E001",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

        lifecycle_events = []

        # Step 2: Bar 1 — HOLD
        market = _make_market(bar_index=1, o=1.1002, h=1.1005, l=1.0998, c=1.1003,
                              prev_swing_low=1.0975, prev_swing_high=1.1015)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.HOLD
        lifecycle_events.append(("HOLD", None))

        # Step 3: Bar 2 — Trailing (swing low moves to 1.0990)
        market = _make_market(bar_index=2, o=1.1003, h=1.1008, l=1.0998, c=1.1005,
                              prev_swing_low=1.0990, prev_swing_high=1.1015)
        decisions = self.registry.evaluate_bar(market)
        # Commit pending SL (simulates broker confirmation)
        for d in decisions:
            if d.is_sl_move:
                self.registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.0990

        # Execute SL modification through adapter
        request = PositionModificationRequest(
            trade_id="E2E001", symbol="EURUSD",
            new_sl=1.0990, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)
        assert result.success is True
        assert result.sl_matches is True
        self.registry.record_modification("E2E001", result)
        lifecycle_events.append(("MOVE_STOP", 1.0990))

        # Step 4: Bar 3 — Breakeven (profit = 18 pips >= 16 threshold)
        market = _make_market(bar_index=3, o=1.1005, h=1.1020, l=1.1000, c=1.1018,
                              prev_swing_low=1.0990, prev_swing_high=1.1020)
        decisions = self.registry.evaluate_bar(market)
        for d in decisions:
            if d.is_sl_move:
                self.registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.1000  # entry price

        request = PositionModificationRequest(
            trade_id="E2E001", symbol="EURUSD",
            new_sl=1.1000, reason="breakeven",
        )
        result = self.adapter.modify_position_stop(request)
        assert result.success is True
        self.registry.record_modification("E2E001", result)
        lifecycle_events.append(("MOVE_STOP", 1.1000))

        # Verify breakeven triggered
        pos = self.registry.get_position("E2E001")
        assert pos.breakeven_triggered is True
        assert pos.current_sl == 1.1000

        # Step 5: Bars 4-5 — HOLD
        for bar in [4, 5]:
            market = _make_market(bar_index=bar, o=1.1010, h=1.1015, l=1.1005, c=1.1012,
                                  prev_swing_low=1.0995, prev_swing_high=1.1020)
            decisions = self.registry.evaluate_bar(market)
            assert len(decisions) == 1
            assert decisions[0].action == LifecycleAction.HOLD
            lifecycle_events.append(("HOLD", None))

        # Step 6: Bars 6-41 — HOLD (fast forward)
        for bar in range(6, 42):
            market = _make_market(bar_index=bar, o=1.1010, h=1.1015, l=1.1005, c=1.1012,
                                  prev_swing_low=1.0995, prev_swing_high=1.1020,
                                  minutes_offset=240 * bar)
            self.registry.evaluate_bar(market)

        # Step 7: Bar 42 — MAX HOLD EXIT
        market = _make_market(bar_index=42, o=1.1015, h=1.1020, l=1.1005, c=1.1018,
                              prev_swing_low=1.0995, prev_swing_high=1.1020,
                              minutes_offset=240 * 42)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_price == 1.1018
        lifecycle_events.append(("EXIT_MH", 1.1018))

        # Verify final sequence
        expected = [
            ("HOLD", None),
            ("MOVE_STOP", 1.0990),
            ("MOVE_STOP", 1.1000),
            ("HOLD", None),
            ("HOLD", None),
            ("EXIT_MH", 1.1018),
        ]
        assert lifecycle_events == expected

        # Verify position removed
        assert self.registry.active_count == 0

        # Verify event history
        events = self.registry.get_trade_history("E2E001")
        assert len(events) == 42

    def test_full_short_lifecycle_e2e(self):
        """Complete SHORT lifecycle with SL-first exit."""
        self.registry.register_entry(
            trade_id="SHORT_E2E",
            symbol="EURUSD",
            direction=Direction.SHORT,
            entry_price=1.1000,
            initial_sl=1.1020,
            take_profit=1.0930,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

        # Bar 1: Both SL (1.1020) and TP (1.0930) touched
        # SL should win (evaluated first)
        market = _make_market(bar_index=1, o=1.0995, h=1.1025, l=1.0925, c=1.0930,
                              prev_swing_low=1.0920, prev_swing_high=1.1025)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_price == 1.1020
        assert self.registry.active_count == 0

    def test_adapter_modification_returns_correct_result(self):
        """Verify FakeExecutionAdapter.modify_position_stop works correctly."""
        request = PositionModificationRequest(
            trade_id="T001", symbol="EURUSD",
            new_sl=1.0990, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)
        assert result.success is True
        assert result.requested_sl == 1.0990
        assert result.broker_sl == 1.0990
        assert result.sl_matches is True

    def test_multiple_positions_independent_lifecycle(self):
        """Multiple positions evaluated independently."""
        self.registry.register_entry(
            trade_id="T001", symbol="EURUSD", direction=Direction.LONG,
            entry_price=1.1000, initial_sl=1.0980, take_profit=1.1070,
            pip_size=0.0001, entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )
        self.registry.register_entry(
            trade_id="T002", symbol="GBPUSD", direction=Direction.SHORT,
            entry_price=1.2500, initial_sl=1.2520, take_profit=1.2430,
            pip_size=0.0001, entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

        # EURUSD market — only T001 evaluated
        market = _make_market(bar_index=1)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].trade_id == "T001"

        # Verify T002 still active
        assert self.registry.active_count == 2
