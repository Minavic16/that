"""
Tests for nestquant.execution.s7_engine module.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from nestquant.core.contracts.execution_contracts import (
    Direction,
    ExecutionResult,
    ExecutionStatus,
    TradeIntent,
)
from nestquant.production.execution.mt5_adapter import MT5ExecutionAdapter
from nestquant.production.execution.mt5_client import MT5Client
from nestquant.production.execution.orchestration import ExecutionCoordinator
from nestquant.production.execution.risk_guard import RiskGuard
from nestquant.production.execution.s7_engine import S7Config, S7Engine
from nestquant.production.execution.trade_logger import TradeLogger


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


# ---------------------------------------------------------------------------
# S7Config
# ---------------------------------------------------------------------------


class TestS7Config:
    def test_default_config(self):
        config = S7Config()
        assert config.mt5_base_url == "http://127.0.0.1:5001"
        assert config.account_balance == 5_000_000.0
        assert config.policy_version == "s7-1.0.0"

    def test_custom_config(self):
        config = S7Config(
            mt5_base_url="http://custom:9999",
            account_balance=100_000,
            policy_version="2.0.0",
        )
        assert config.mt5_base_url == "http://custom:9999"
        assert config.account_balance == 100_000
        assert config.policy_version == "2.0.0"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestS7EngineConstruction:
    def test_default_construction(self):
        engine = S7Engine()
        assert engine.config is not None
        assert isinstance(engine.adapter, MT5ExecutionAdapter)
        assert isinstance(engine.risk_guard, RiskGuard)
        assert isinstance(engine.coordinator, ExecutionCoordinator)
        assert isinstance(engine.trade_logger, TradeLogger)

    def test_custom_config(self):
        config = S7Config(account_balance=100_000, policy_version="test")
        engine = S7Engine(config=config)
        assert engine.config.account_balance == 100_000
        assert engine.config.policy_version == "test"

    def test_components_wired_correctly(self):
        engine = S7Engine()
        assert engine.coordinator.risk is engine.risk_guard
        assert engine.coordinator.adapter is engine.adapter

    def test_repr(self):
        engine = S7Engine()
        r = repr(engine)
        assert "S7Engine" in r
        assert "s7-1.0.0" in r


# ---------------------------------------------------------------------------
# Environment config loading
# ---------------------------------------------------------------------------


class TestEnvironmentConfig:
    def test_loads_from_env(self):
        env = {
            "NESTQUANT_MT5_BASE_URL": "http://env:8888",
            "NESTQUANT_ACCOUNT_BALANCE": "200000",
            "NESTQUANT_RISK_PCT": "0.005",
            "NESTQUANT_POLICY_VERSION": "env-test",
        }
        with patch.dict(os.environ, env):
            engine = S7Engine()
            assert engine.config.mt5_base_url == "http://env:8888"
            assert engine.config.account_balance == 200_000
            assert engine.config.risk_pct == 0.005
            assert engine.config.policy_version == "env-test"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check_healthy(self):
        engine = S7Engine()
        engine._health_monitor._status.is_connected = True

        assert engine.health_check() is True

    def test_health_check_unhealthy(self):
        engine = S7Engine()
        engine._health_monitor._status.is_connected = False

        assert engine.health_check() is False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_structure(self):
        engine = S7Engine()
        s = engine.status()

        assert "config" in s
        assert "health" in s
        assert "risk" in s
        assert "trade_logger" in s

    def test_status_values(self):
        engine = S7Engine()
        s = engine.status()

        assert s["config"]["mt5_base_url"] == "http://127.0.0.1:5001"
        assert s["config"]["policy_version"] == "s7-1.0.0"
        assert "is_connected" in s["health"]
        assert "can_trade" in s["risk"]


# ---------------------------------------------------------------------------
# Start/stop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_stop(self):
        engine = S7Engine()
        engine.start()
        assert engine._health_monitor._monitoring is True

        engine.stop()
        assert engine._health_monitor._monitoring is False

    def test_start_logs_event(self):
        engine = S7Engine()
        engine.start()
        events = engine.trade_logger.get_infrastructure_events()
        assert len(events) >= 1
        assert events[-1]["event_type"] == "STARTUP"

        engine.stop()
        events = engine.trade_logger.get_infrastructure_events()
        assert events[-1]["event_type"] == "SHUTDOWN"


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_returns_result(self):
        engine = S7Engine()
        intent = _valid_intent()
        result = engine.execute(intent)

        assert isinstance(result, ExecutionResult)

    def test_execute_rejected_by_risk(self):
        config = S7Config(max_concurrent_positions=0)
        engine = S7Engine(config=config)
        intent = _valid_intent()
        result = engine.execute(intent)

        assert result.is_rejected

    def test_execute_with_mocked_adapter(self):
        engine = S7Engine()
        mock_adapter = MagicMock(spec=MT5ExecutionAdapter)
        mock_adapter.execute.return_value = ExecutionResult(
            status=ExecutionStatus.FILLED,
            order_id="TEST-001",
            requested_price=1.1000,
            fill_price=1.1002,
            slippage_pips=0.2,
            rejection_reason=None,
        )
        mock_adapter.get_positions.return_value = []
        engine._coordinator._adapter = mock_adapter

        intent = _valid_intent()
        result = engine.execute(intent)

        assert result.is_filled
        assert result.order_id == "TEST-001"

    def test_execute_error_logged(self):
        engine = S7Engine()
        mock_adapter = MagicMock(spec=MT5ExecutionAdapter)
        mock_adapter.execute.return_value = ExecutionResult(
            status=ExecutionStatus.ERROR,
            order_id=None,
            requested_price=1.1000,
            fill_price=None,
            slippage_pips=0.0,
            rejection_reason="Connection timeout",
        )
        mock_adapter.get_positions.return_value = []
        engine._coordinator._adapter = mock_adapter

        intent = _valid_intent()
        result = engine.execute(intent)

        assert result.is_error
        events = engine.trade_logger.get_infrastructure_events()
        error_events = [e for e in events if e["event_type"] == "ERROR"]
        assert len(error_events) >= 1


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.production.execution.s7_engine as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line

    def test_no_network_calls(self):
        import nestquant.production.execution.s7_engine as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "import requests" not in line
            assert "import httpx" not in line
