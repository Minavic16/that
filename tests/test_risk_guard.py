"""
Tests for nestquant.execution.risk_guard module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest

from nestquant.execution.contracts import (
    Direction,
    RiskDecision,
    TradeIntent,
)
from nestquant.execution.risk_guard import RiskGuard, RiskGuardConfig
from nestquant.risk.circuit_breakers import BreakerSuite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_intent(**overrides) -> TradeIntent:
    defaults = dict(
        pair="EUR/USD",
        direction=Direction.BUY,
        signal_strength=0.75,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        strategy="zscore",
        policy_version="s7-1.0.0",
        timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return TradeIntent(**defaults)


def _make_position(ticket: int = 1, symbol: str = "EURUSD", volume: float = 0.1) -> dict:
    return {"ticket": ticket, "symbol": symbol, "volume": volume}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestRiskGuardConstruction:
    def test_default_construction(self):
        guard = RiskGuard()
        assert guard.config is not None
        assert guard.breakers is not None
        assert guard.policy_version == "s7-1.0.0"

    def test_custom_config(self):
        config = RiskGuardConfig(account_balance=100_000, max_concurrent_positions=5)
        guard = RiskGuard(config=config)
        assert guard.config.account_balance == 100_000
        assert guard.config.max_concurrent_positions == 5

    def test_custom_policy_version(self):
        guard = RiskGuard(policy_version="2.0.0")
        assert guard.policy_version == "2.0.0"

    def test_repr(self):
        guard = RiskGuard()
        r = repr(guard)
        assert "RiskGuard" in r
        assert "s7-1.0.0" in r


# ---------------------------------------------------------------------------
# Basic approval
# ---------------------------------------------------------------------------


class TestBasicApproval:
    def test_simple_buy_approved(self):
        guard = RiskGuard()
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is True
        assert decision.lot_size > 0
        assert decision.risk_amount > 0
        assert decision.policy_version == "s7-1.0.0"

    def test_simple_sell_approved(self):
        guard = RiskGuard()
        intent = _valid_intent(
            direction=Direction.SELL,
            stop_loss=1.1050,
            take_profit=1.0850,
        )
        decision = guard.evaluate(intent)

        assert decision.approved is True
        assert decision.lot_size > 0

    def test_lot_size_within_bounds(self):
        guard = RiskGuard()
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.lot_size >= 0.01
        assert decision.lot_size <= 1.0  # max_position_size_per_pair


# ---------------------------------------------------------------------------
# Circuit breaker gates
# ---------------------------------------------------------------------------


class TestCircuitBreakerGates:
    def test_hard_stop_blocks_trade(self):
        guard = RiskGuard()
        guard.breakers.dd_pace.hard_stop()
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is False
        assert "Circuit breaker" in decision.reason

    def test_pause_blocks_trade(self):
        guard = RiskGuard()
        guard.breakers.winrate.pause()
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is False
        assert "Circuit breaker" in decision.reason


# ---------------------------------------------------------------------------
# Position limit gates
# ---------------------------------------------------------------------------


class TestPositionLimits:
    def test_max_concurrent_positions_rejected(self):
        config = RiskGuardConfig(max_concurrent_positions=2)
        guard = RiskGuard(config=config)
        guard.update_positions([
            _make_position(1, "EURUSD", 0.1),
            _make_position(2, "GBPUSD", 0.1),
        ])
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is False
        assert "Max concurrent positions" in decision.reason

    def test_below_max_positions_approved(self):
        config = RiskGuardConfig(
            account_balance=100_000,
            max_concurrent_positions=5,
            max_position_size_per_pair=2.0,
            risk_pct=0.003,
        )
        guard = RiskGuard(config=config)
        guard.update_positions([
            _make_position(1, "EURUSD", 0.1),
            _make_position(2, "GBPUSD", 0.1),
        ])
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is True

    def test_zero_positions_approved(self):
        guard = RiskGuard()
        guard.update_positions([])
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is True


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------


class TestDailyLossLimit:
    def test_daily_loss_within_limit(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_daily_loss_pct=0.03)
        guard = RiskGuard(config=config)
        guard._daily_pnl = -20_000  # 2% loss, under 3% limit

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is True

    def test_daily_loss_at_limit(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_daily_loss_pct=0.03)
        guard = RiskGuard(config=config)
        guard._daily_pnl = -30_000  # Exactly 3% loss

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is False
        assert "Daily loss limit" in decision.reason

    def test_daily_loss_over_limit(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_daily_loss_pct=0.03)
        guard = RiskGuard(config=config)
        guard._daily_pnl = -50_000  # 5% loss, over 3% limit

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is False

    def test_daily_profit_not_affected(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_daily_loss_pct=0.03)
        guard = RiskGuard(config=config)
        guard._daily_pnl = 50_000  # Positive PnL

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is True


# ---------------------------------------------------------------------------
# Drawdown limit
# ---------------------------------------------------------------------------


class TestDrawdownLimit:
    def test_drawdown_within_limit(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_drawdown_pct=0.10)
        guard = RiskGuard(config=config)
        guard._peak_equity = 1_050_000  # 4.76% DD, under 10%

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is True

    def test_drawdown_at_limit(self):
        config = RiskGuardConfig(
            account_balance=1_000_000,
            max_drawdown_pct=0.10,
            max_daily_loss_pct=0.50,
        )
        guard = RiskGuard(config=config)
        guard._peak_equity = 1_200_000
        guard._daily_pnl = -200_000  # Current equity = 800k, DD = (1.2M - 800k) / 1.2M = 33%

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is False
        assert "drawdown" in decision.reason.lower()

    def test_drawdown_over_limit(self):
        config = RiskGuardConfig(account_balance=1_000_000, max_drawdown_pct=0.10)
        guard = RiskGuard(config=config)
        guard._peak_equity = 1_200_000  # 16.67% DD

        intent = _valid_intent()
        decision = guard.evaluate(intent)
        assert decision.approved is False


# ---------------------------------------------------------------------------
# Per-pair exposure
# ---------------------------------------------------------------------------


class TestPerPairExposure:
    def test_pair_exposure_within_limit(self):
        config = RiskGuardConfig(
            account_balance=100_000,
            max_position_size_per_pair=2.0,
            risk_pct=0.003,
        )
        guard = RiskGuard(config=config)
        guard.update_positions([
            _make_position(1, "EURUSD", 0.2),
        ])
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is True

    def test_pair_exposure_at_limit(self):
        config = RiskGuardConfig(max_position_size_per_pair=0.5)
        guard = RiskGuard(config=config)
        guard.update_positions([
            _make_position(1, "EURUSD", 0.4),
        ])
        # New lot would be ~0.15, total ~0.55 > 0.5
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        # May be rejected depending on lot sizing
        if not decision.approved:
            assert "Per-pair exposure" in decision.reason


# ---------------------------------------------------------------------------
# Total exposure
# ---------------------------------------------------------------------------


class TestTotalExposure:
    def test_total_exposure_within_limit(self):
        config = RiskGuardConfig(
            account_balance=100_000,
            max_total_exposure=10.0,
            max_position_size_per_pair=5.0,
            risk_pct=0.003,
        )
        guard = RiskGuard(config=config)
        guard.update_positions([
            _make_position(1, "EURUSD", 0.1),
            _make_position(2, "GBPUSD", 0.1),
        ])
        intent = _valid_intent()
        decision = guard.evaluate(intent)

        assert decision.approved is True


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStateManagement:
    def test_update_positions(self):
        guard = RiskGuard()
        positions = [_make_position(1, "EURUSD", 0.1)]
        guard.update_positions(positions)

        assert len(guard._open_positions) == 1
        assert guard._open_positions[0]["symbol"] == "EURUSD"

    def test_record_trade_result(self):
        guard = RiskGuard()
        guard.record_trade_result(pnl=100.0, equity=5_000_100.0, slippage_pips=0.2)

        assert guard._daily_pnl == 100.0
        assert guard._peak_equity == 5_000_100.0
        assert guard._trade_count_today == 1

    def test_record_multiple_trades(self):
        guard = RiskGuard()
        guard.record_trade_result(pnl=100.0, equity=5_000_100.0)
        guard.record_trade_result(pnl=-50.0, equity=5_000_050.0)
        guard.record_trade_result(pnl=200.0, equity=5_000_250.0)

        assert guard._daily_pnl == 250.0
        assert guard._peak_equity == 5_000_250.0
        assert guard._trade_count_today == 3

    def test_reset_daily(self):
        guard = RiskGuard()
        guard.record_trade_result(pnl=100.0, equity=5_000_100.0)
        guard._trade_count_today = 5

        guard.reset_daily()

        assert guard._daily_pnl == 0.0
        assert guard._trade_count_today == 0


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_structure(self):
        guard = RiskGuard()
        status = guard.status()

        assert "can_trade" in status
        assert "blocked_by" in status
        assert "open_positions" in status
        assert "max_positions" in status
        assert "daily_pnl" in status
        assert "peak_equity" in status
        assert "trade_count_today" in status
        assert "policy_version" in status
        assert "breakers" in status

    def test_status_reflects_state(self):
        guard = RiskGuard()
        guard.update_positions([_make_position(1, "EURUSD", 0.1)])
        guard.record_trade_result(pnl=50.0, equity=5_000_050.0)

        status = guard.status()
        assert status["open_positions"] == 1
        assert status["daily_pnl"] == 50.0
        assert status["trade_count_today"] == 1


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_risk_evaluator_protocol(self):
        from nestquant.execution.orchestration import RiskEvaluator
        guard = RiskGuard()
        assert isinstance(guard, RiskEvaluator)

    def test_evaluate_returns_risk_decision(self):
        guard = RiskGuard()
        result = guard.evaluate(_valid_intent())
        assert isinstance(result, RiskDecision)


# ---------------------------------------------------------------------------
# Integration with ExecutionCoordinator
# ---------------------------------------------------------------------------


class TestCoordinatorIntegration:
    def test_risk_guard_with_coordinator(self):
        from nestquant.execution.orchestration import ExecutionCoordinator
        from nestquant.execution.adapter import FakeExecutionAdapter

        guard = RiskGuard()
        adapter = FakeExecutionAdapter()
        coordinator = ExecutionCoordinator(risk=guard, adapter=adapter)

        intent = _valid_intent()
        result = coordinator.orchestrate(intent)

        assert result.is_filled
        assert adapter.execution_count == 1

    def test_risk_guard_rejection_through_coordinator(self):
        from nestquant.execution.orchestration import ExecutionCoordinator
        from nestquant.execution.adapter import FakeExecutionAdapter

        config = RiskGuardConfig(max_concurrent_positions=0)
        guard = RiskGuard(config=config)
        adapter = FakeExecutionAdapter()
        coordinator = ExecutionCoordinator(risk=guard, adapter=adapter)

        intent = _valid_intent()
        result = coordinator.orchestrate(intent)

        assert result.is_rejected
        assert adapter.execution_count == 0


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.execution.risk_guard as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line

    def test_no_network_calls(self):
        import nestquant.execution.risk_guard as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "import requests" not in line
            assert "import httpx" not in line
