"""
Health Collector — Infrastructure Health Monitoring
====================================================

Collects health data from the MT5 bridge /health and /last_error endpoints.
Tracks uptime, consecutive failures, and response times.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nestquant.production.monitoring.models import HealthSnapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


class HealthCollector:
    """Collects and tracks infrastructure health from the MT5 bridge."""

    def __init__(self, max_history: int = 10000) -> None:
        self.max_history = max_history
        self._history: list[HealthSnapshot] = []
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._total_checks = 0
        self._total_failures = 0

    def collect_health(self, client_base_url: str) -> HealthSnapshot:
        """
        Call /health and /last_error endpoints on the bridge.

        Returns a HealthSnapshot with current status.
        """
        monotonic_start = time.monotonic()
        now_str = datetime.now(UTC).isoformat()

        bridge_healthy = False
        mt5_connected = False
        mt5_initialized = False
        last_error = ""
        response_time_ms = 0.0

        health_url = f"{client_base_url.rstrip('/')}/health"
        try:
            req = Request(health_url, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            response_time_ms = (time.monotonic() - monotonic_start) * 1000

            data = body.get("data", body)
            bridge_healthy = body.get("ok", False)
            mt5_connected = bool(data.get("mt5_connected", False))
            mt5_initialized = bool(data.get("mt5_initialized", False))

        except (HTTPError, URLError, OSError) as exc:
            response_time_ms = (time.monotonic() - monotonic_start) * 1000
            logger.warning("Health check failed: %s", exc)
            bridge_healthy = False
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            response_time_ms = (time.monotonic() - monotonic_start) * 1000
            logger.warning("Failed to parse health response: %s", exc)

        # Fetch last error if available
        error_url = f"{client_base_url.rstrip('/')}/last_error"
        try:
            req = Request(error_url, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            data = body.get("data", body)
            last_error = str(data.get("last_error", data.get("error", "")))
        except (HTTPError, URLError, OSError, json.JSONDecodeError, KeyError):
            pass  # last_error endpoint is optional

        # Update failure tracking
        with self._lock:
            self._total_checks += 1
            if bridge_healthy and mt5_connected:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                self._total_failures += 1

        snapshot = HealthSnapshot(
            timestamp=now_str,
            bridge_healthy=bridge_healthy,
            mt5_connected=mt5_connected,
            mt5_initialized=mt5_initialized,
            response_time_ms=response_time_ms,
            last_error=last_error,
            consecutive_failures=self._consecutive_failures,
            total_checks=self._total_checks,
            total_failures=self._total_failures,
        )

        with self._lock:
            self._history.append(snapshot)
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history:]

        return snapshot

    def get_uptime(self) -> float:
        """Return fraction of successful health checks (0.0 to 1.0)."""
        with self._lock:
            if self._total_checks == 0:
                return 0.0
            return 1.0 - (self._total_failures / self._total_checks)

    def get_consecutive_failures(self) -> int:
        """Return current number of consecutive failures."""
        with self._lock:
            return self._consecutive_failures

    def get_history(self) -> list[HealthSnapshot]:
        """Return copy of health check history."""
        with self._lock:
            return list(self._history)

    def get_latest(self) -> HealthSnapshot | None:
        """Return the most recent health snapshot, or None."""
        with self._lock:
            if not self._history:
                return None
            return self._history[-1]

    def clear(self) -> None:
        """Clear history and reset counters."""
        with self._lock:
            self._history.clear()
            self._consecutive_failures = 0
            self._total_checks = 0
            self._total_failures = 0
