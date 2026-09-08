"""
Tests for S8.4 — S8 Runtime
=============================
Verifies runtime lifecycle, metrics, configuration, signal handling,
and component integration.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_runtime.py -v --noconftest
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

NESTQUANT_ROOT = str(Path(__file__).parent.parent)
if NESTQUANT_ROOT not in os.sys.path:
    os.sys.path.insert(0, NESTQUANT_ROOT)

from execution.s8_runtime import (
    RuntimeConfig,
    RuntimeMetrics,
    RuntimeMode,
    RuntimeState,
    S8Runtime,
)


# ===================================================================
# RuntimeConfig
# ===================================================================


class TestRuntimeConfig:
    def test_defaults(self):
        cfg = RuntimeConfig()
        assert cfg.pairs == ("EUR/USD",)
        assert cfg.timeframe == "H4"
        assert cfg.poll_interval_seconds == 60
        assert cfg.max_loop_errors == 10
        assert cfg.mode == RuntimeMode.DRY_RUN

    def test_custom_config(self):
        cfg = RuntimeConfig(
            pairs=("EUR/USD", "GBP/USD"),
            timeframe="H1",
            poll_interval_seconds=30,
        )
        assert cfg.pairs == ("EUR/USD", "GBP/USD")
        assert cfg.timeframe == "H1"
        assert cfg.poll_interval_seconds == 30


# ===================================================================
# RuntimeMetrics
# ===================================================================


class TestRuntimeMetrics:
    def test_initial_metrics(self):
        m = RuntimeMetrics()
        assert m.bars_processed == 0
        assert m.signals_generated == 0
        assert m.trades_executed == 0
        assert m.errors == 0
        assert m.uptime_seconds == 0.0

    def test_uptime_calculation(self):
        m = RuntimeMetrics()
        m.start_time = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        assert m.uptime_seconds >= 0

    def test_to_dict(self):
        m = RuntimeMetrics()
        d = m.to_dict()
        assert "bars_processed" in d
        assert "signals_generated" in d
        assert "trades_executed" in d
        assert "errors" in d
        assert "uptime_seconds" in d


# ===================================================================
# RuntimeState
# ===================================================================


class TestRuntimeState:
    def test_states_exist(self):
        assert RuntimeState.IDLE == "idle"
        assert RuntimeState.RUNNING == "running"
        assert RuntimeState.STOPPING == "stopping"
        assert RuntimeState.STOPPED == "stopped"
        assert RuntimeState.ERROR == "error"


# ===================================================================
# S8Runtime
# ===================================================================


def _make_runtime_with_mocks(**kwargs) -> S8Runtime:
    """Create a fully mocked S8Runtime for testing."""
    runtime = S8Runtime(**kwargs)
    runtime._client = MagicMock()
    runtime._prop_guard = MagicMock()
    runtime._prop_guard.breakers.can_trade = (True, "")
    runtime._trade_logger = MagicMock()
    runtime._data_feed = MagicMock()
    runtime._intent_factory = MagicMock()
    runtime._coordinator = MagicMock()
    runtime._adapter = MagicMock()
    runtime._strategy = MagicMock()
    return runtime


class TestS8Runtime:
    def test_creates_with_defaults(self):
        runtime = S8Runtime()
        assert runtime.state == RuntimeState.IDLE
        assert runtime.config.pairs == ("EUR/USD",)

    def test_creates_with_custom_config(self):
        cfg = RuntimeConfig(pairs=("GBP/USD",), timeframe="H1")
        runtime = S8Runtime(config=cfg)
        assert runtime.config.pairs == ("GBP/USD",)
        assert runtime.config.timeframe == "H1"

    def test_initialize_with_mocked_components(self):
        runtime = S8Runtime()
        runtime._client = MagicMock()
        result = runtime.initialize()
        assert result is True
        assert runtime._data_feed is not None
        assert runtime._intent_factory is not None

    def test_metrics_start_at_zero(self):
        runtime = S8Runtime()
        assert runtime.metrics.bars_processed == 0
        assert runtime.metrics.signals_generated == 0
        assert runtime.metrics.trades_executed == 0

    def test_status_returns_dict(self):
        runtime = S8Runtime()
        status = runtime.status()
        assert "runtime" in status
        assert "config" in status
        assert status["runtime"]["state"] == "idle"

    def test_stop_sets_state(self):
        runtime = S8Runtime()
        runtime._state = RuntimeState.RUNNING
        runtime.stop()
        assert runtime._state == RuntimeState.STOPPING

    def test_stop_from_idle_is_noop(self):
        runtime = S8Runtime()
        runtime.stop()
        assert runtime.state == RuntimeState.IDLE

    def test_process_pair_no_candles(self):
        runtime = _make_runtime_with_mocks()
        runtime._data_feed.fetch_candles.return_value = []
        runtime._process_pair("EUR/USD")
        assert runtime.metrics.bars_processed == 0

    def test_process_pair_no_new_bar(self):
        runtime = _make_runtime_with_mocks()
        runtime._data_feed.fetch_candles.return_value = [MagicMock()]
        runtime._data_feed.has_new_bar.return_value = False
        runtime._process_pair("EUR/USD")
        assert runtime.metrics.bars_processed == 0

    def test_process_pair_with_signal(self):
        runtime = _make_runtime_with_mocks()

        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.pair = "EUR/USD"
        mock_signal.direction = "BUY"
        mock_signal.strength = 1.0
        mock_signal.entry_price = 1.0850
        mock_signal.sl_price = 1.0820
        mock_signal.tp_price = 1.0950
        runtime._get_strategy_signal = MagicMock(return_value=mock_signal)

        mock_intent = MagicMock()
        mock_intent.direction.value = "BUY"
        mock_intent.signal_strength = 1.0
        mock_intent.entry_price = 1.0850
        mock_intent.stop_loss = 1.0820
        mock_intent.take_profit = 1.0950
        runtime._intent_factory.create_intent_with_id.return_value = (mock_intent, "test-signal-id")

        mock_result = MagicMock()
        mock_result.is_filled = True
        mock_result.order_id = "12345"
        mock_result.fill_price = 1.0850
        runtime._coordinator.orchestrate.return_value = mock_result

        runtime._data_feed.fetch_candles.return_value = [MagicMock()]
        runtime._data_feed.has_new_bar.return_value = True

        runtime._process_pair("EUR/USD")

        assert runtime.metrics.bars_processed == 1
        assert runtime.metrics.signals_generated == 1
        assert runtime.metrics.intents_created == 1
        assert runtime.metrics.trades_executed == 1

    def test_process_pair_rejected_trade(self):
        runtime = _make_runtime_with_mocks()

        mock_signal = MagicMock()
        mock_signal.is_active = True
        mock_signal.pair = "EUR/USD"
        mock_signal.direction = "BUY"
        mock_signal.strength = 1.0
        mock_signal.entry_price = 1.0850
        mock_signal.sl_price = 1.0820
        mock_signal.tp_price = 1.0950
        runtime._get_strategy_signal = MagicMock(return_value=mock_signal)

        mock_intent = MagicMock()
        mock_intent.direction.value = "BUY"
        mock_intent.signal_strength = 1.0
        mock_intent.entry_price = 1.0850
        mock_intent.stop_loss = 1.0820
        mock_intent.take_profit = 1.0950
        runtime._intent_factory.create_intent_with_id.return_value = (mock_intent, "test-id")

        mock_result = MagicMock()
        mock_result.is_filled = False
        mock_result.is_rejected = True
        mock_result.rejection_reason = "Risk rejected"
        runtime._coordinator.orchestrate.return_value = mock_result

        runtime._data_feed.fetch_candles.return_value = [MagicMock()]
        runtime._data_feed.has_new_bar.return_value = True

        runtime._process_pair("EUR/USD")
        assert runtime.metrics.trades_rejected == 1
        assert runtime.metrics.trades_executed == 0

    def test_health_gate_blocks_trade(self):
        runtime = _make_runtime_with_mocks()
        runtime._prop_guard.breakers.can_trade = (False, "Circuit breaker active")

        runtime._data_feed.fetch_candles.return_value = [MagicMock()]
        runtime._data_feed.has_new_bar.return_value = True

        runtime._process_pair("EUR/USD")
        assert runtime.metrics.trades_halted == 1
        assert runtime.metrics.bars_processed == 0  # Should not process at all
