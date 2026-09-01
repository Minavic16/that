"""
NestQuant Health Monitor — MT5 Connection Monitoring
=====================================================
Monitors the MT5 bridge connection health.

This module:
  - Periodically checks MT5 bridge health
  - Detects disconnections and reconnections
  - Records infrastructure events
  - Provides connection status to the execution layer

This module does NOT:
  - Import MetaTrader5 directly
  - Perform risk calculations
  - Perform strategy calculations
  - Make trading decisions
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable, Optional

from nestquant.execution.mt5_client import MT5Client, MT5ConnectionError, MT5Response
from nestquant.execution.trade_logger import InfrastructureRecord, TradeLogger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthMonitorConfig:
    """Configuration for the health monitor."""

    check_interval_seconds: float = 30.0
    timeout_seconds: float = 10.0
    max_consecutive_failures: int = 3
    warning_threshold_seconds: float = 300.0  # 5 minutes


# ---------------------------------------------------------------------------
# Health status
# ---------------------------------------------------------------------------


@dataclass
class HealthStatus:
    """Current health status of the MT5 connection."""

    is_connected: bool
    last_check: Optional[str] = None
    last_success: Optional[str] = None
    consecutive_failures: int = 0
    total_checks: int = 0
    total_failures: int = 0
    uptime_seconds: float = 0.0
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "is_connected": self.is_connected,
            "last_check": self.last_check,
            "last_success": self.last_success,
            "consecutive_failures": self.consecutive_failures,
            "total_checks": self.total_checks,
            "total_failures": self.total_failures,
            "uptime_seconds": self.uptime_seconds,
            "last_error": self.last_error,
        }


# ---------------------------------------------------------------------------
# Health Monitor
# ---------------------------------------------------------------------------


class HealthMonitor:
    """Monitors MT5 bridge connection health.

    Can run checks synchronously or in a background thread.
    Records infrastructure events via TradeLogger.
    """

    def __init__(
        self,
        client: MT5Client,
        config: Optional[HealthMonitorConfig] = None,
        trade_logger: Optional[TradeLogger] = None,
    ) -> None:
        """Initialize the health monitor.

        Args:
            client: MT5Client to monitor.
            config: Monitor configuration.
            trade_logger: Optional logger for infrastructure events.
        """
        self._client = client
        self._config = config or HealthMonitorConfig()
        self._trade_logger = trade_logger
        self._status = HealthStatus(is_connected=False)
        self._start_time = datetime.now(UTC)
        self._monitoring = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def status(self) -> HealthStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._status.is_connected

    @property
    def config(self) -> HealthMonitorConfig:
        return self._config

    # ------------------------------------------------------------------
    # Synchronous check
    # ------------------------------------------------------------------

    def check(self) -> HealthStatus:
        """Perform a single health check.

        Returns:
            Updated HealthStatus.
        """
        now = datetime.now(UTC)
        self._status.last_check = now.isoformat()
        self._status.total_checks += 1

        try:
            response = self._client.health()
            if response.ok:
                self._on_success(now)
            else:
                self._on_failure(now, response.error or "Health check returned error")
        except MT5ConnectionError as exc:
            self._on_failure(now, f"Connection failed: {exc}")
        except Exception as exc:
            self._on_failure(now, f"Unexpected error: {exc}")

        return self._status

    def _on_success(self, now: datetime) -> None:
        """Handle a successful health check."""
        was_connected = self._status.is_connected
        self._status.is_connected = True
        self._status.consecutive_failures = 0
        self._status.last_success = now.isoformat()
        self._status.last_error = None
        self._status.uptime_seconds = (now - self._start_time).total_seconds()

        if not was_connected and self._status.total_checks > 1:
            self._record_event(
                event_type="RECONNECT",
                description="MT5 connection restored",
                impact="NO_IMPACT",
                resolution="auto-reconnect",
            )

    def _on_failure(self, now: datetime, error: str) -> None:
        """Handle a failed health check."""
        was_connected = self._status.is_connected
        self._status.consecutive_failures += 1
        self._status.total_failures += 1
        self._status.last_error = error

        if was_connected:
            self._record_event(
                event_type="DISCONNECT",
                description=error,
                impact="UNKNOWN",
                resolution="pending",
            )

        if self._status.consecutive_failures >= self._config.max_consecutive_failures:
            self._status.is_connected = False

    def _record_event(
        self,
        event_type: str,
        description: str,
        impact: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> None:
        """Record an infrastructure event."""
        if self._trade_logger:
            self._trade_logger.log_infrastructure_event(
                event_type=event_type,
                description=description,
                impact=impact,
                resolution=resolution,
            )

    # ------------------------------------------------------------------
    # Background monitoring
    # ------------------------------------------------------------------

    def start_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="health-monitor",
        )
        self._thread.start()

    def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._monitoring = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            self.check()
            self._stop_event.wait(timeout=self._config.check_interval_seconds)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status_dict(self) -> dict:
        """Get health status as a dictionary."""
        return self._status.to_dict()

    def __repr__(self) -> str:
        conn = "connected" if self.is_connected else "disconnected"
        return (
            f"<HealthMonitor({conn}, "
            f"checks={self._status.total_checks}, "
            f"failures={self._status.total_failures})>"
        )
