"""
Latency Probe — HTTP Round-Trip Measurement
=============================================

Measures and tracks HTTP latency to the MT5 bridge and other components.
Uses time.monotonic() for all timing to avoid wall-clock drift.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from monitoring.models import LatencySnapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


def measure_http_latency(url: str, timeout: float = DEFAULT_TIMEOUT) -> float:
    """
    Measure HTTP round-trip latency in milliseconds.

    Uses time.monotonic() for precise timing.
    Returns latency in ms, or float('nan') on failure.
    """
    monotonic_start = time.monotonic()
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000
        return elapsed_ms
    except (HTTPError, URLError, OSError) as exc:
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000
        logger.warning("Latency probe to %s failed after %.1fms: %s", url, elapsed_ms, exc)
        return float("nan")


class LatencyTracker:
    """Stores and analyzes latency measurements across components."""

    def __init__(self, max_measurements: int = 10000) -> None:
        self.max_measurements = max_measurements
        self._measurements: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def record(self, component: str, latency_ms: float) -> None:
        """Store a latency measurement for a component."""
        if not np.isfinite(latency_ms):
            return
        with self._lock:
            if component not in self._measurements:
                self._measurements[component] = []
            series = self._measurements[component]
            series.append(latency_ms)
            if len(series) > self.max_measurements:
                self._measurements[component] = series[-self.max_measurements:]

    def measure_and_record(
        self,
        component: str,
        url: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> LatencySnapshot:
        """
        Perform a round-trip measurement and store the result.

        Returns a LatencySnapshot.
        """
        latency_ms = measure_http_latency(url, timeout)
        self.record(component, latency_ms)

        now_str = datetime.now(UTC).isoformat()
        return LatencySnapshot(
            timestamp=now_str,
            component=component,
            latency_ms=latency_ms,
            is_measured=np.isfinite(latency_ms),
        )

    def get_distribution(self, component: str) -> np.ndarray:
        """Return numpy array of latency measurements for a component."""
        with self._lock:
            series = self._measurements.get(component, [])
            if not series:
                return np.array([], dtype=float)
            return np.array(series, dtype=float)

    def get_percentiles(self, component: str) -> dict[str, float]:
        """Return dict of P50/P75/P90/P95/P99 for a component's latency."""
        from monitoring.percentiles import compute_percentiles

        dist = self.get_distribution(component)
        if len(dist) == 0:
            return {
                "P50": float("nan"),
                "P75": float("nan"),
                "P90": float("nan"),
                "P95": float("nan"),
                "P99": float("nan"),
                "count": 0,
            }

        result = compute_percentiles(dist)
        return {
            "P50": result.p50.value,
            "P75": result.p75.value,
            "P90": result.p90.value,
            "P95": result.p95.value,
            "P99": result.p99.value,
            "count": result.count,
        }

    def get_all_components(self) -> list[str]:
        """Return list of tracked component names."""
        with self._lock:
            return list(self._measurements.keys())

    def clear(self) -> None:
        """Clear all stored measurements."""
        with self._lock:
            self._measurements.clear()
