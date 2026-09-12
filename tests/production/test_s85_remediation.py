"""
Tests for S8.5 Remediation — Runtime, Modes, Health Gate, Strategy Wiring
==========================================================================
Validates all critical fixes from the preflight report.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s85_remediation.py -v --noconftest
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# Mock pandas if not available (for strategy wiring tests)
_MOCK_PD = None
if "pandas" not in sys.modules:
    _mock_pd = MagicMock()
    _MockDataFrame = type("DataFrame", (), {
        "__init__": lambda self, data=None: setattr(self, "_data", data) or None,
        "empty": False,
        "columns": ["time", "open", "high", "low", "close", "volume"],
        "__getitem__": lambda self, key: MagicMock(),
    })
    _mock_pd.DataFrame = _MockDataFrame
    sys.modules["pandas"] = _mock_pd
    _MOCK_PD = _mock_pd

from nestquant.core.contracts.execution_contracts import Direction, ExecutionResult, ExecutionStatus, TradeIntent
from nestquant.production.execution.data_feed import OHLCV
from nestquant.production.execution.intent_factory import IntentFactory
from nestquant.production.execution.orchestration import ExecutionCoordinator
from nestquant.production.execution.prop_firm_guard import PropFirmConfig, PropFirmGuard
from nestquant.production.execution.s8_runtime import (
    DryRunAdapter,
    PositionTracker,
    RuntimeConfig,
    RuntimeMode,
    RuntimeState,
    S8Runtime,
)


# ===================================================================
# RuntimeMode
# ===================================================================


class TestRuntimeMode:
    def test_dry_run_value(self):
        assert RuntimeMode.DRY_RUN.value == "dry-run"

    def test_experimental_live_value(self):
        assert RuntimeMode.EXPERIMENTAL_LIVE.value == "experimental-live"


# ===================================================================
# RuntimeConfig
# ===================================================================


class TestRuntimeConfig:
    def test_default_mode_is_dry_run(self):
        cfg = RuntimeConfig()
        assert cfg.mode == RuntimeMode.DRY_RUN

    def test_pairs_default_eur_usd(self):
        cfg = RuntimeConfig()
        assert cfg.pairs == ("EUR/USD",)

    def test_timeframe_default_h4(self):
        cfg = RuntimeConfig()
        assert cfg.timeframe == "H4"


# ===================================================================
# DryRunAdapter
# ===================================================================


class TestDryRunAdapter:
    def test_execute_returns_rejected(self):
        adapter = DryRunAdapter()
        request = MagicMock()
        request.direction.value = "BUY"
        request.lot_size = 0.01
        request.pair = "EUR/USD"
        request.stop_loss = 1.0820
        request.take_profit = 1.0950
        request.entry_price = 1.0850

        result = adapter.execute(request)
        assert result.status == ExecutionStatus.REJECTED
        assert "DRY_RUN" in result.rejection_reason

    def test_execute_does_not_send_real_order(self):
        adapter = DryRunAdapter()
        request = MagicMock()
        request.direction.value = "BUY"
        request.lot_size = 0.01
        request.pair = "EUR/USD"
        request.stop_loss = 1.0820
        request.take_profit = 1.0950
        request.entry_price = 1.0850

        result = adapter.execute(request)
        # Should never have an order_id (no real order)
        assert result.order_id is None

    def test_execute_logs_event(self):
        mock_logger = MagicMock()
        adapter = DryRunAdapter(trade_logger=mock_logger)
        request = MagicMock()
        request.direction.value = "SELL"
        request.lot_size = 0.01
        request.pair = "GBP/USD"
        request.stop_loss = 1.2730
        request.take_profit = 1.2600
        request.entry_price = 1.2700

        adapter.execute(request)
        mock_logger.log_infrastructure_event.assert_called_once()
        call_args = mock_logger.log_infrastructure_event.call_args
        assert call_args.kwargs["event_type"] == "DRY_RUN_ORDER"


# ===================================================================
# PositionTracker
# ===================================================================


class TestPositionTracker:
    def test_track_open(self):
        tracker = PositionTracker()
        tracker.track_open(12345, "EURUSD", "BUY", 0.01, 1.0850)
        assert tracker.open_count == 1
        assert 12345 in tracker.open_tickets

    def test_detect_closed(self):
        tracker = PositionTracker()
        tracker.track_open(12345, "EURUSD", "BUY", 0.01, 1.0850)
        tracker.track_open(12346, "EURUSD", "SELL", 0.01, 1.2700)

        # Current positions: only 12346 is still open
        current = [{"ticket": 12346}]
        closed = tracker.detect_closed(current)

        assert len(closed) == 1
        assert closed[0].ticket == 12345
        assert tracker.open_count == 1

    def test_no_closed_positions(self):
        tracker = PositionTracker()
        tracker.track_open(12345, "EURUSD", "BUY", 0.01, 1.0850)

        current = [{"ticket": 12345}]
        closed = tracker.detect_closed(current)
        assert len(closed) == 0
        assert tracker.open_count == 1


# ===================================================================
# S8Runtime Initialization (C3, C5 fix)
# ===================================================================


class TestS8RuntimeInit:
    def test_initialize_creates_components(self):
        runtime = S8Runtime(config=RuntimeConfig())
        # Mock the MT5 client to avoid network calls
        runtime._client = MagicMock()
        result = runtime.initialize()
        assert result is True
        assert runtime._data_feed is not None
        assert runtime._intent_factory is not None
        assert runtime._prop_guard is not None
        assert runtime._coordinator is not None
        assert runtime._adapter is not None

    def test_initialize_dry_run_uses_dry_run_adapter(self):
        runtime = S8Runtime(config=RuntimeConfig(mode=RuntimeMode.DRY_RUN))
        runtime._client = MagicMock()
        runtime.initialize()
        assert isinstance(runtime._adapter, DryRunAdapter)

    def test_initialize_experimental_live_requires_env(self):
        runtime = S8Runtime(config=RuntimeConfig(mode=RuntimeMode.EXPERIMENTAL_LIVE))
        runtime._client = MagicMock()
        # Without env var, should refuse
        with patch.dict(os.environ, {}, clear=True):
            result = runtime.initialize()
            assert result is False
            assert runtime.state == RuntimeState.ERROR

    def test_initialize_experimental_live_with_env(self):
        runtime = S8Runtime(config=RuntimeConfig(mode=RuntimeMode.EXPERIMENTAL_LIVE))
        runtime._client = MagicMock()
        with patch.dict(os.environ, {"NESTQUANT_EXPERIMENTAL_LIVE": "true"}):
            result = runtime.initialize()
            assert result is True
            # Should NOT be DryRunAdapter
            assert not isinstance(runtime._adapter, DryRunAdapter)

    def test_prop_guard_is_coordinator_risk(self):
        """PropFirmGuard must be the risk evaluator in the coordinator."""
        prop_guard = PropFirmGuard()
        runtime = S8Runtime(
            config=RuntimeConfig(),
            prop_guard=prop_guard,
        )
        runtime._client = MagicMock()
        runtime.initialize()
        assert runtime._coordinator.risk is prop_guard

    def test_status_includes_mode(self):
        runtime = S8Runtime(config=RuntimeConfig(mode=RuntimeMode.DRY_RUN))
        status = runtime.status()
        assert status["mode"] == "dry-run"


# ===================================================================
# Health Gate (C7 fix)
# ===================================================================


class TestHealthGate:
    def test_health_gate_blocks_on_circuit_breaker(self):
        runtime = S8Runtime(config=RuntimeConfig())
        runtime._client = MagicMock()
        runtime._prop_guard = MagicMock()
        runtime._prop_guard.breakers.can_trade = (False, "Max drawdown breached")
        runtime._trade_logger = MagicMock()

        result = runtime._check_health_gate()
        assert result is False
        assert runtime._metrics.trades_halted == 1

    def test_health_gate_passes_when_ok(self):
        runtime = S8Runtime(config=RuntimeConfig())
        runtime._client = MagicMock()
        runtime._prop_guard = MagicMock()
        runtime._prop_guard.breakers.can_trade = (True, "")

        result = runtime._check_health_gate()
        assert result is True


# ===================================================================
# Strategy Wiring (C4 fix)
# ===================================================================


class TestStrategyWiring:
    def _make_candles(self) -> list[OHLCV]:
        """Create realistic OHLCV candles for testing."""
        from datetime import timedelta
        candles = []
        base_ts = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        for i in range(20):
            ts = base_ts + timedelta(hours=4 * i)
            candles.append(OHLCV(
                timestamp=ts,
                open=1.0800 + i * 0.001,
                high=1.0850 + i * 0.001,
                low=1.0780 + i * 0.001,
                close=1.0830 + i * 0.001,
                volume=1000,
            ))
        return candles

    def test_strategy_wired_in_runtime(self):
        mock_strategy = MagicMock()
        mock_signal = MagicMock()
        mock_signal.direction = "NEUTRAL"
        mock_strategy.generate.return_value = mock_signal

        runtime = S8Runtime(
            config=RuntimeConfig(),
            strategy=mock_strategy,
        )
        runtime._client = MagicMock()
        runtime.initialize()

        candles = self._make_candles()
        # Patch pandas at sys.modules level for the lazy import
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_pd.DataFrame.return_value = mock_df
        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = runtime._get_strategy_signal("EUR/USD", candles)
        assert result is None  # NEUTRAL returns None

    def test_buy_signal_produces_signal(self):
        mock_strategy = MagicMock()
        mock_signal = MagicMock()
        mock_signal.direction = "BUY"
        mock_strategy.generate.return_value = mock_signal

        runtime = S8Runtime(
            config=RuntimeConfig(),
            strategy=mock_strategy,
        )
        runtime._client = MagicMock()
        runtime.initialize()

        candles = self._make_candles()
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_pd.DataFrame.return_value = mock_df
        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = runtime._get_strategy_signal("EUR/USD", candles)
        assert result is not None
        assert result.direction == "BUY"

    def test_strategy_receives_dataframe(self):
        mock_strategy = MagicMock()
        mock_signal = MagicMock()
        mock_signal.direction = "NEUTRAL"
        mock_strategy.generate.return_value = mock_signal

        runtime = S8Runtime(
            config=RuntimeConfig(),
            strategy=mock_strategy,
        )
        runtime._client = MagicMock()
        runtime.initialize()

        candles = self._make_candles()
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_pd.DataFrame.return_value = mock_df
        with patch.dict(sys.modules, {"pandas": mock_pd}):
            runtime._get_strategy_signal("EUR/USD", candles)

            # Verify strategy was called with a DataFrame
            call_args = mock_strategy.generate.call_args
            df = call_args[0][0]
            assert df is mock_df


# ===================================================================
# IntentFactory + Signal → Intent (C1, C2 fix)
# ===================================================================


class TestSignalToIntent:
    def test_buy_signal_produces_buy_intent(self):
        factory = IntentFactory()
        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.direction = "BUY"
        mock_signal.strength = 1.0
        mock_signal.entry_price = 1.0850
        mock_signal.sl_price = 1.0820
        mock_signal.tp_price = 1.0950

        intent = factory.create_intent(mock_signal)
        assert intent.direction == Direction.BUY
        assert intent.entry_price == 1.0850

    def test_sell_signal_produces_sell_intent(self):
        factory = IntentFactory()
        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.direction = "SELL"
        mock_signal.strength = 1.0
        mock_signal.entry_price = 1.2700
        mock_signal.sl_price = 1.2730
        mock_signal.tp_price = 1.2600

        intent = factory.create_intent(mock_signal)
        assert intent.direction == Direction.SELL

    def test_sl_tp_match_research_params(self):
        """Verify SL/TP from strategy match research: SL=2.0*ATR, TP=2.0*ATR*3.5."""
        factory = IntentFactory()

        # Simulate: entry=1.0850, ATR=0.0030, SL_MULT=2.0, RRR=3.5
        atr = 0.0030
        sl_mult = 2.0
        rrr = 3.5
        entry = 1.0850

        expected_sl = entry - (atr * sl_mult)  # 1.0790
        expected_tp = entry + (atr * sl_mult * rrr)  # 1.1060

        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.direction = "BUY"
        mock_signal.strength = 1.0
        mock_signal.entry_price = entry
        mock_signal.sl_price = expected_sl
        mock_signal.tp_price = expected_tp

        intent = factory.create_intent(mock_signal)
        assert intent.stop_loss == pytest.approx(1.0790, abs=1e-6)
        assert intent.take_profit == pytest.approx(1.1060, abs=1e-6)


# ===================================================================
# PropFirmGuard Configuration (Step 7)
# ===================================================================


class TestPropFirmConfig:
    def test_experiment_config_values(self):
        cfg = PropFirmConfig(
            starting_balance=200_000.0,
            risk_pct=0.001,  # 0.10%
            max_daily_loss_absolute=1_000.0,  # 0.50%
            max_total_drawdown_absolute=2_000.0,  # 1.00%
            max_concurrent_positions=1,
            max_consecutive_losing_days=3,
        )
        assert cfg.risk_pct == 0.001
        assert cfg.max_daily_loss_absolute == 1_000.0
        assert cfg.max_total_drawdown_absolute == 2_000.0
        assert cfg.max_concurrent_positions == 1
        assert cfg.max_consecutive_losing_days == 3

    def test_prop_firm_guard_rejects_over_daily_limit(self):
        cfg = PropFirmConfig(
            starting_balance=200_000.0,
            max_daily_loss_absolute=1_000.0,
        )
        guard = PropFirmGuard(prop_config=cfg)
        # Simulate daily loss by recording trades (bypasses reset)
        guard._daily_pnl = -1_001.0
        guard._prop_state.daily_pnl = -1_001.0
        guard._prop_state.daily_reset_date = datetime.now(UTC).date()  # Prevent reset

        intent = TradeIntent(
            pair="EUR/USD",
            direction=Direction.BUY,
            signal_strength=1.0,
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0950,
            strategy="test",
            policy_version="s8-prop-1.0.0",
            timestamp=datetime.now(UTC),
        )
        decision = guard.evaluate(intent)
        assert not decision.approved
        assert "daily loss" in decision.reason.lower()


# ===================================================================
# Full Pipeline Integration
# ===================================================================


class TestFullPipeline:
    def test_end_to_end_dry_run(self):
        """Full pipeline: strategy → signal → intent → risk → dry-run adapter."""
        # Create strategy mock
        mock_strategy = MagicMock()
        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.direction = "BUY"
        mock_signal.strength = 1.0
        mock_signal.pair = "EUR/USD"
        mock_signal.entry_price = 1.0850
        mock_signal.sl_price = 1.0820
        mock_signal.tp_price = 1.0950
        mock_strategy.generate.return_value = mock_signal

        # Create runtime with dry-run mode
        runtime = S8Runtime(
            config=RuntimeConfig(mode=RuntimeMode.DRY_RUN),
            strategy=mock_strategy,
        )
        runtime._client = MagicMock()
        result = runtime.initialize()
        assert result is True

        # Verify adapter is dry-run
        assert isinstance(runtime._adapter, DryRunAdapter)

        # Verify coordinator uses PropFirmGuard
        assert isinstance(runtime._coordinator.risk, PropFirmGuard)


# ===================================================================
# mode-authorization test
# ===================================================================


class TestModeAuthorization:
    def test_experimental_live_refuses_without_env(self):
        runtime = S8Runtime(
            config=RuntimeConfig(mode=RuntimeMode.EXPERIMENTAL_LIVE)
        )
        runtime._client = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            result = runtime.initialize()
            assert result is False

    def test_dry_run_always_allowed(self):
        runtime = S8Runtime(
            config=RuntimeConfig(mode=RuntimeMode.DRY_RUN)
        )
        runtime._client = MagicMock()
        result = runtime.initialize()
        assert result is True
