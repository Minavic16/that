"""
Tests for nestquant.execution.health_monitor module.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from nestquant.production.execution.health_monitor import (
    HealthMonitor,
    HealthMonitorConfig,
    HealthStatus,
)
from nestquant.production.execution.mt5_client import MT5Client, MT5ConnectionError, MT5Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_response() -> MT5Response:
    return MT5Response(ok=True, data={"status": "success"}, status_code=200)


def _error_response(error: str = "Error") -> MT5Response:
    return MT5Response(ok=False, error=error, status_code=500)


def _mock_client(health_return: MT5Response = None, health_side_effect: Exception = None) -> MT5Client:
    client = MagicMock(spec=MT5Client)
    if health_side_effect:
        client.health.side_effect = health_side_effect
    else:
        client.health.return_value = health_return or _ok_response()
    return client


# ---------------------------------------------------------------------------
# HealthStatus
# ---------------------------------------------------------------------------


class TestHealthStatus:
    def test_default_status(self):
        s = HealthStatus(is_connected=False)
        assert s.is_connected is False
        assert s.consecutive_failures == 0
        assert s.total_checks == 0

    def test_to_dict(self):
        s = HealthStatus(is_connected=True, consecutive_failures=2)
        d = s.to_dict()
        assert d["is_connected"] is True
        assert d["consecutive_failures"] == 2


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestHealthMonitorConstruction:
    def test_default_construction(self):
        client = _mock_client()
        monitor = HealthMonitor(client=client)
        assert monitor.is_connected is False
        assert monitor.config.check_interval_seconds == 30.0

    def test_custom_config(self):
        config = HealthMonitorConfig(check_interval_seconds=10.0)
        client = _mock_client()
        monitor = HealthMonitor(client=client, config=config)
        assert monitor.config.check_interval_seconds == 10.0

    def test_repr(self):
        client = _mock_client()
        monitor = HealthMonitor(client=client)
        r = repr(monitor)
        assert "HealthMonitor" in r
        assert "disconnected" in r


# ---------------------------------------------------------------------------
# Synchronous check
# ---------------------------------------------------------------------------


class TestSynchronousCheck:
    def test_successful_check(self):
        client = _mock_client(_ok_response())
        monitor = HealthMonitor(client=client)

        status = monitor.check()

        assert status.is_connected is True
        assert status.consecutive_failures == 0
        assert status.total_checks == 1
        assert status.total_failures == 0

    def test_failed_check(self):
        client = _mock_client(_error_response("MT5 not connected"))
        monitor = HealthMonitor(client=client)

        status = monitor.check()

        assert status.is_connected is False
        assert status.consecutive_failures == 1
        assert status.total_failures == 1

    def test_connection_error(self):
        client = _mock_client(health_side_effect=MT5ConnectionError("No route"))
        monitor = HealthMonitor(client=client)

        status = monitor.check()

        assert status.is_connected is False
        assert status.consecutive_failures == 1
        assert "Connection failed" in status.last_error

    def test_unexpected_error(self):
        client = _mock_client(health_side_effect=RuntimeError("Boom"))
        monitor = HealthMonitor(client=client)

        status = monitor.check()

        assert status.is_connected is False
        assert "Unexpected error" in status.last_error

    def test_consecutive_failures_tracking(self):
        client = _mock_client(_error_response("Error"))
        monitor = HealthMonitor(client=client)

        monitor.check()
        assert monitor.status.consecutive_failures == 1

        monitor.check()
        assert monitor.status.consecutive_failures == 2

        monitor.check()
        assert monitor.status.consecutive_failures == 3

    def test_max_failures_disconnects(self):
        config = HealthMonitorConfig(max_consecutive_failures=3)
        client = _mock_client(_error_response("Error"))
        monitor = HealthMonitor(client=client, config=config)

        # First check: connected=True → disconnected after 3 failures
        monitor.check()  # failure 1
        monitor.check()  # failure 2
        monitor.check()  # failure 3 → is_connected = False

        assert monitor.is_connected is False

    def test_success_resets_failures(self):
        client = MagicMock(spec=MT5Client)
        client.health.side_effect = [
            _error_response("Error"),
            _error_response("Error"),
            _ok_response(),
        ]
        monitor = HealthMonitor(client=client)

        monitor.check()
        monitor.check()
        assert monitor.status.consecutive_failures == 2

        monitor.check()
        assert monitor.status.consecutive_failures == 0
        assert monitor.is_connected is True

    def test_reconnection_event(self):
        client = MagicMock(spec=MT5Client)
        client.health.side_effect = [
            _error_response("Error"),
            _ok_response(),
        ]
        logger = MagicMock()
        monitor = HealthMonitor(client=client, trade_logger=logger)

        # First check: failure (initial state was disconnected, no event)
        monitor.check()
        # Second check: success (reconnect)
        monitor.check()

        # Should have logged a RECONNECT event
        logger.log_infrastructure_event.assert_called_once()
        call_kwargs = logger.log_infrastructure_event.call_args[1]
        assert call_kwargs["event_type"] == "RECONNECT"


# ---------------------------------------------------------------------------
# Background monitoring
# ---------------------------------------------------------------------------


class TestBackgroundMonitoring:
    def test_start_stop(self):
        client = _mock_client(_ok_response())
        config = HealthMonitorConfig(check_interval_seconds=0.1)
        monitor = HealthMonitor(client=client, config=config)

        monitor.start_monitoring()
        assert monitor._monitoring is True
        assert monitor._thread is not None

        time.sleep(0.3)

        monitor.stop_monitoring()
        assert monitor._monitoring is False

    def test_monitoring_performs_checks(self):
        client = _mock_client(_ok_response())
        config = HealthMonitorConfig(check_interval_seconds=0.1)
        monitor = HealthMonitor(client=client, config=config)

        monitor.start_monitoring()
        time.sleep(0.5)
        monitor.stop_monitoring()

        assert client.health.call_count >= 3

    def test_double_start_is_noop(self):
        client = _mock_client(_ok_response())
        config = HealthMonitorConfig(check_interval_seconds=0.1)
        monitor = HealthMonitor(client=client, config=config)

        monitor.start_monitoring()
        thread1 = monitor._thread
        monitor.start_monitoring()
        thread2 = monitor._thread

        assert thread1 is thread2

        monitor.stop_monitoring()


# ---------------------------------------------------------------------------
# Status dict
# ---------------------------------------------------------------------------


class TestStatusDict:
    def test_status_dict(self):
        client = _mock_client(_ok_response())
        monitor = HealthMonitor(client=client)
        monitor.check()

        d = monitor.status_dict()
        assert "is_connected" in d
        assert "total_checks" in d
        assert d["is_connected"] is True


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.production.execution.health_monitor as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line

    def test_no_network_calls(self):
        import nestquant.production.execution.health_monitor as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "import requests" not in line
            assert "import httpx" not in line
