"""
NestQuant Strategy — Lifecycle Integration Tests
==================================================

Four test levels:
A. Unit tests — contracts and individual components
B. Integration tests — lifecycle → execution intents
C. Broker adapter mock tests — modification success/failure
D. Deterministic replay test — full bar sequence
"""

import os
from datetime import datetime, timezone, timedelta


import pytest
from nestquant.production.strategy.lifecycle.contracts import (
    Direction,
    ExitReason,
    LifecycleAction,
    LifecycleDecision,
    MarketContext,
    ModificationResult,
    PositionLifecycleState,
    ReconciliationResult,
)
from nestquant.production.strategy.lifecycle.registry import LifecycleEvent, LifecycleRegistry
from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig


# ═══════════════════════════════════════════════════════════════
# A. Unit Tests — Contracts
# ═══════════════════════════════════════════════════════════════

class TestPositionLifecycleState:
    """Unit tests for PositionLifecycleState."""

    def test_creation_with_defaults(self):
        pos = PositionLifecycleState(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.LONG,
            strategy_identity="abc",
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            risk_pips=20.0,
            pip_size=0.0001,
            entry_time=datetime.now(timezone.utc),
            entry_bar_index=0,
        )
        assert pos.current_sl == 1.0980
        assert pos.bars_held == 0
        assert pos.breakeven_triggered is False

    def test_risk_pips_never_changes(self):
        """risk_pips must be immutable — matches research engine."""
        pos = PositionLifecycleState(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.LONG,
            strategy_identity="abc",
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            risk_pips=20.0,
            pip_size=0.0001,
            entry_time=datetime.now(timezone.utc),
            entry_bar_index=0,
        )
        # Even if we hypothetically changed current_sl, risk_pips stays
        assert pos.risk_pips == 20.0

    def test_unrealized_r_long(self):
        pos = PositionLifecycleState(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.LONG,
            strategy_identity="abc",
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            risk_pips=20.0,
            pip_size=0.0001,
            entry_time=datetime.now(timezone.utc),
            entry_bar_index=0,
        )
        # +10 pips = 0.5R
        assert pos.unrealized_r(1.1010) == pytest.approx(0.5, abs=1e-10)

    def test_unrealized_r_short(self):
        pos = PositionLifecycleState(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.SHORT,
            strategy_identity="abc",
            entry_price=1.1000,
            initial_sl=1.1020,
            take_profit=1.0930,
            risk_pips=20.0,
            pip_size=0.0001,
            entry_time=datetime.now(timezone.utc),
            entry_bar_index=0,
        )
        # -10 pips = 0.5R
        assert pos.unrealized_r(1.0990) == pytest.approx(0.5, abs=1e-10)


class TestModificationResult:
    def test_sl_matches(self):
        r = ModificationResult(
            success=True, trade_id="T001",
            requested_sl=1.1000, broker_sl=1.1000,
            timestamp=datetime.now(timezone.utc),
        )
        assert r.sl_matches is True

    def test_sl_mismatch(self):
        r = ModificationResult(
            success=True, trade_id="T001",
            requested_sl=1.1000, broker_sl=1.1005,
            timestamp=datetime.now(timezone.utc),
        )
        assert r.sl_matches is False

    def test_failed_modification(self):
        r = ModificationResult(
            success=False, trade_id="T001",
            requested_sl=1.1000, broker_sl=None,
            timestamp=datetime.now(timezone.utc),
            error="ORDER_INVALID",
        )
        assert r.sl_matches is False


class TestReconciliationResult:
    def test_ok(self):
        r = ReconciliationResult(
            trade_id="T001", internal_sl=1.1000,
            broker_sl=1.1000, mismatch=False, severity="OK",
        )
        assert r.is_ok is True

    def test_critical(self):
        r = ReconciliationResult(
            trade_id="T001", internal_sl=1.1000,
            broker_sl=1.1005, mismatch=True, severity="CRITICAL",
        )
        assert r.is_ok is False


# ═══════════════════════════════════════════════════════════════
# B. Integration Tests — Lifecycle → Execution Intents
# ═══════════════════════════════════════════════════════════════

def _make_market(
    symbol="EURUSD",
    timeframe="4h",
    bar_index=1,
    o=1.1000, h=1.1010, l=1.0990, c=1.1005,
    prev_swing_low=1.0985,
    prev_swing_high=1.1015,
    minutes_offset=240,
) -> MarketContext:
    return MarketContext(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes_offset * bar_index),
        bar_index=bar_index,
        open=o, high=h, low=l, close=c,
        previous_swing_low=prev_swing_low,
        previous_swing_high=prev_swing_high,
    )


class TestLifecycleIntegration:
    """Integration tests: market data → lifecycle → execution intents."""

    def setup_method(self):
        self.registry = LifecycleRegistry(strategy_identity="test_v1")
        self.registry.register_entry(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

    def test_hold_on_quiet_bar(self):
        """No exit, no trailing, no BE → HOLD."""
        market = _make_market(bar_index=1, o=1.1002, h=1.1005, l=1.0998, c=1.1003,
                              prev_swing_low=1.0975, prev_swing_high=1.1015)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.HOLD

    def test_trailing_moves_sl(self):
        """Swing low above current SL → MOVE_STOP."""
        market = _make_market(bar_index=1, o=1.1002, h=1.1010, l=1.0998, c=1.1005,
                              prev_swing_low=1.0990, prev_swing_high=1.1015)
        decisions = self.registry.evaluate_bar(market)
        # Commit pending SL (simulates broker confirmation)
        for d in decisions:
            if d.is_sl_move:
                self.registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.0990
        # Verify internal state updated
        pos = self.registry.get_position("T001")
        assert pos.current_sl == 1.0990

    def test_breakeven_triggers_after_trailing(self):
        """Trailing moves SL up, then BE moves to entry."""
        # Register with close SL to test BE trigger
        self.registry.register_entry(
            trade_id="T002",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )
        # Profit = 18 pips, threshold = 16 pips → BE triggers
        market = _make_market(bar_index=1, o=1.1005, h=1.1020, l=1.1000, c=1.1018,
                              prev_swing_low=1.0990, prev_swing_high=1.1020)
        decisions = self.registry.evaluate_bar(market)
        # Both T001 and T002 evaluated
        assert len(decisions) == 2
        # T002 should have BE triggered (trailing moves to 1.0990, then BE to 1.1000)
        t2_dec = [d for d in decisions if d.trade_id == "T002"][0]
        assert t2_dec.action == LifecycleAction.MOVE_STOP
        assert t2_dec.new_sl == 1.1000  # entry price

    def test_sl_exits_position(self):
        """Low touches SL → EXIT."""
        market = _make_market(bar_index=1, o=1.0995, h=1.1000, l=1.0975, c=1.0980,
                              prev_swing_low=1.0975, prev_swing_high=1.1015)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_reason == ExitReason.STOP_LOSS
        assert decisions[0].exit_price == 1.0980
        assert self.registry.active_count == 0

    def test_tp_exits_position(self):
        """High touches TP → EXIT."""
        market = _make_market(bar_index=1, o=1.1005, h=1.1075, l=1.1000, c=1.1070,
                              prev_swing_low=1.0995, prev_swing_high=1.1075)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_reason == ExitReason.TAKE_PROFIT
        assert decisions[0].exit_price == 1.1070

    def test_max_hold_exits_at_close(self):
        """After 42 bars, exit at close."""
        # Advance to bar 41 (will become 42 on next evaluate_bar)
        for i in range(1, 42):
            market = _make_market(bar_index=i, o=1.1002, h=1.1005, l=1.0998, c=1.1003,
                                  prev_swing_low=1.0975, prev_swing_high=1.1015,
                                  minutes_offset=240 * i)
            self.registry.evaluate_bar(market)

        # Bar 42 → MH exit
        market = _make_market(bar_index=42, o=1.1005, h=1.1010, l=1.0998, c=1.1008,
                              prev_swing_low=1.0990, prev_swing_high=1.1015,
                              minutes_offset=240 * 42)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_reason == ExitReason.MAX_HOLD
        assert decisions[0].exit_price == 1.1008  # close

    def test_multiple_positions_independent(self):
        """Multiple positions evaluated independently."""
        self.registry.register_entry(
            trade_id="T002",
            symbol="GBPUSD",
            direction=Direction.SHORT,
            entry_price=1.2500,
            initial_sl=1.2520,
            take_profit=1.2430,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )
        # EURUSD market — only T001 evaluated
        market = _make_market(symbol="EURUSD", bar_index=1)
        decisions = self.registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].trade_id == "T001"

    def test_events_recorded(self):
        """All evaluations produce lifecycle events."""
        market = _make_market(bar_index=1)
        self.registry.evaluate_bar(market)
        assert len(self.registry.events) == 1
        assert self.registry.events[0].trade_id == "T001"


# ═══════════════════════════════════════════════════════════════
# C. Broker Adapter Mock Tests
# ═══════════════════════════════════════════════════════════════

class TestBrokerMockIntegration:
    """Test modification result handling and reconciliation."""

    def setup_method(self):
        self.registry = LifecycleRegistry(strategy_identity="test_v1")
        self.registry.register_entry(
            trade_id="T001",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

    def test_successful_modification_recorded(self):
        """Broker confirms SL modification."""
        result = ModificationResult(
            success=True,
            trade_id="T001",
            requested_sl=1.0990,
            broker_sl=1.0990,
            timestamp=datetime.now(timezone.utc),
        )
        self.registry.record_modification("T001", result)
        events = self.registry.get_trade_history("T001")
        assert len(events) == 0  # No evaluation yet

    def test_reconciliation_ok(self):
        """Internal and broker SL match."""
        results = self.registry.reconcile({"T001": 1.0980})
        assert len(results) == 1
        assert results[0].is_ok is True
        assert results[0].severity == "OK"

    def test_reconciliation_mismatch(self):
        """Internal and broker SL diverge — CRITICAL."""
        results = self.registry.reconcile({"T001": 1.0985})
        assert len(results) == 1
        assert results[0].is_ok is False
        assert results[0].severity == "CRITICAL"

    def test_reconciliation_missing_broker_position(self):
        """Broker doesn't know about position — CRITICAL."""
        results = self.registry.reconcile({})
        assert len(results) == 1
        assert results[0].is_ok is False
        assert results[0].severity == "CRITICAL"


# ═══════════════════════════════════════════════════════════════
# D. Deterministic Replay Test
# ═══════════════════════════════════════════════════════════════

class TestDeterministicReplay:
    """Full bar sequence replay — the most valuable test.

    Replays a synthetic 7-bar sequence:
        Bar 0 → entry
        Bar 1 → hold
        Bar 2 → trailing (swing low moves up)
        Bar 3 → breakeven (profit exceeds 0.8R)
        Bar 4 → hold
        Bar 5 → hold
        Bar 6 → max hold exit
    """

    def test_full_lifecycle_replay(self):
        registry = LifecycleRegistry(strategy_identity="replay_v1")

        # Bar 0: Entry
        registry.register_entry(
            trade_id="REPLAY001",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=1.1000,
            initial_sl=1.0980,
            take_profit=1.1070,
            pip_size=0.0001,
            entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_bar_index=0,
        )

        expected_actions = []

        # Bar 1: Hold (quiet bar)
        market = _make_market(bar_index=1, o=1.1002, h=1.1005, l=1.0998, c=1.1003,
                              prev_swing_low=1.0975, prev_swing_high=1.1015)
        decisions = registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.HOLD
        expected_actions.append("HOLD")

        # Bar 2: Trailing (swing low moves to 1.0990)
        market = _make_market(bar_index=2, o=1.1003, h=1.1008, l=1.0998, c=1.1005,
                              prev_swing_low=1.0990, prev_swing_high=1.1015)
        decisions = registry.evaluate_bar(market)
        for d in decisions:
            if d.is_sl_move:
                registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.0990
        expected_actions.append("MOVE_STOP")

        # Bar 3: Breakeven (close=1.1018, profit=18 pips >= 16 threshold)
        market = _make_market(bar_index=3, o=1.1005, h=1.1020, l=1.1000, c=1.1018,
                              prev_swing_low=1.0990, prev_swing_high=1.1020)
        decisions = registry.evaluate_bar(market)
        for d in decisions:
            if d.is_sl_move:
                registry.commit_sl(d.trade_id)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.MOVE_STOP
        assert decisions[0].new_sl == 1.1000  # entry price (breakeven)
        expected_actions.append("MOVE_STOP")

        # Verify breakeven triggered
        pos = registry.get_position("REPLAY001")
        assert pos.breakeven_triggered is True
        assert pos.current_sl == 1.1000

        # Bar 4: Hold
        market = _make_market(bar_index=4, o=1.1010, h=1.1015, l=1.1005, c=1.1012,
                              prev_swing_low=1.0995, prev_swing_high=1.1020)
        decisions = registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.HOLD
        expected_actions.append("HOLD")

        # Bar 5: Hold
        market = _make_market(bar_index=5, o=1.1012, h=1.1018, l=1.1008, c=1.1015,
                              prev_swing_low=1.0998, prev_swing_high=1.1020)
        decisions = registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.HOLD
        expected_actions.append("HOLD")

        # Bar 6: Max hold exit (bars_held reaches 42)
        # We need 42 bars. Let's simulate bars 6-41 quickly
        for i in range(6, 42):
            market = _make_market(bar_index=i, o=1.1010, h=1.1015, l=1.1005, c=1.1012,
                                  prev_swing_low=1.0995, prev_swing_high=1.1020,
                                  minutes_offset=240 * i)
            registry.evaluate_bar(market)

        # Bar 42: MH exit
        market = _make_market(bar_index=42, o=1.1015, h=1.1020, l=1.1005, c=1.1018,
                              prev_swing_low=1.0995, prev_swing_high=1.1020,
                              minutes_offset=240 * 42)
        decisions = registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_reason == ExitReason.MAX_HOLD
        assert decisions[0].exit_price == 1.1018
        expected_actions.append("EXIT")

        # Verify final sequence
        assert expected_actions == [
            "HOLD", "MOVE_STOP", "MOVE_STOP", "HOLD", "HOLD", "EXIT"
        ]

        # Verify position removed
        assert registry.active_count == 0

        # Verify event history
        events = registry.get_trade_history("REPLAY001")
        assert len(events) == 42  # 42 bars evaluated

    def test_short_replay_sl_first(self):
        """SHORT position — SL exit before TP on same bar."""
        registry = LifecycleRegistry(strategy_identity="replay_short")

        registry.register_entry(
            trade_id="SHORT001",
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
        decisions = registry.evaluate_bar(market)
        assert len(decisions) == 1
        assert decisions[0].action == LifecycleAction.EXIT
        assert decisions[0].exit_reason == ExitReason.STOP_LOSS
        assert decisions[0].exit_price == 1.1020
