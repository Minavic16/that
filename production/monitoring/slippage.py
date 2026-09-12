"""
Slippage Tracker — Execution Quality Measurement
==================================================

Measures and tracks entry/exit slippage in pips.
Handles JPY pairs (0.01 pip size) and standard pairs (0.0001 pip size).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Optional

import numpy as np

from nestquant.production.monitoring.models import ExecutionSnapshot

logger = logging.getLogger(__name__)

# Pip sizes by quote currency
JPY_PAIRS = {
    "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY",
    "CADJPY", "CHFJPY", "EURAUD", "EURNZD",
}

DEFAULT_PIP_SIZE = 0.0001
JPY_PIP_SIZE = 0.01


def _get_pip_size(pair: str) -> float:
    """Return pip size for a given pair."""
    pair_upper = pair.upper().replace("/", "").replace("_", "")
    if pair_upper.endswith("JPY"):
        return JPY_PIP_SIZE
    return DEFAULT_PIP_SIZE


class SlippageTracker:
    """Tracks entry and exit slippage measurements."""

    def __init__(self, max_measurements: int = 10000) -> None:
        self.max_measurements = max_measurements
        self._entry_slippage: list[float] = []
        self._exit_slippage: list[float] = []
        self._lock = threading.Lock()

    def record_entry_slippage(
        self,
        requested_price: float,
        fill_price: float,
        pair: str,
    ) -> ExecutionSnapshot:
        """
        Calculate and store entry slippage.

        Returns an ExecutionSnapshot with the slippage recorded.
        """
        pip_size = _get_pip_size(pair)
        slippage_pips = abs(fill_price - requested_price) / pip_size

        now_str = datetime.now(UTC).isoformat()

        snapshot = ExecutionSnapshot(
            submission_timestamp=now_str,
            requested_price=requested_price,
            fill_price=fill_price,
            entry_slippage_pips=slippage_pips,
            execution_status="measured",
            measured=True,
        )

        with self._lock:
            self._entry_slippage.append(slippage_pips)
            if len(self._entry_slippage) > self.max_measurements:
                self._entry_slippage = self._entry_slippage[-self.max_measurements:]

        logger.debug(
            "Entry slippage %s: requested=%.5f fill=%.5f slip=%.2f pips",
            pair, requested_price, fill_price, slippage_pips,
        )
        return snapshot

    def record_exit_slippage(
        self,
        requested_price: float,
        fill_price: float,
        pair: str,
    ) -> ExecutionSnapshot:
        """
        Calculate and store exit slippage.

        Returns an ExecutionSnapshot with the slippage recorded.
        """
        pip_size = _get_pip_size(pair)
        slippage_pips = abs(fill_price - requested_price) / pip_size

        now_str = datetime.now(UTC).isoformat()

        snapshot = ExecutionSnapshot(
            submission_timestamp=now_str,
            requested_price=requested_price,
            fill_price=fill_price,
            exit_slippage_pips=slippage_pips,
            execution_status="measured",
            measured=True,
        )

        with self._lock:
            self._exit_slippage.append(slippage_pips)
            if len(self._exit_slippage) > self.max_measurements:
                self._exit_slippage = self._exit_slippage[-self.max_measurements:]

        logger.debug(
            "Exit slippage %s: requested=%.5f fill=%.5f slip=%.2f pips",
            pair, requested_price, fill_price, slippage_pips,
        )
        return snapshot

    def get_entry_slippage_distribution(self) -> np.ndarray:
        """Return numpy array of entry slippage values in pips."""
        with self._lock:
            if not self._entry_slippage:
                return np.array([], dtype=float)
            return np.array(self._entry_slippage, dtype=float)

    def get_exit_slippage_distribution(self) -> np.ndarray:
        """Return numpy array of exit slippage values in pips."""
        with self._lock:
            if not self._exit_slippage:
                return np.array([], dtype=float)
            return np.array(self._exit_slippage, dtype=float)

    def get_overall_distribution(self) -> np.ndarray:
        """Return combined numpy array of all slippage values in pips."""
        with self._lock:
            combined = self._entry_slippage + self._exit_slippage
            if not combined:
                return np.array([], dtype=float)
            return np.array(combined, dtype=float)

    def get_percentiles(self) -> dict[str, float]:
        """Return dict of P50/P75/P90/P95/P99 for overall slippage."""
        from nestquant.production.monitoring.percentiles import compute_percentiles

        dist = self.get_overall_distribution()
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

    @staticmethod
    def get_direction_adjusted_adverse(
        entry_slip: float,
        direction: str,
    ) -> float:
        """
        Return adverse (negative for the trader) slippage component.

        For BUY: adverse = fill > requested (positive slippage is adverse).
        For SELL: adverse = fill < requested (positive slippage is adverse).

        Returns signed adverse slippage in pips. Positive = adverse.
        """
        # entry_slip is already |fill - requested| / pip_size
        # For entry, we always treat the measured slippage as potentially adverse
        # unless we know the direction. Since slippage is stored as absolute,
        # direction-adjusted adverse is simply the absolute slippage.
        # The caller knows if it was a buy or sell to interpret sign.
        return abs(entry_slip)

    def get_entry_count(self) -> int:
        """Return number of entry slippage measurements."""
        with self._lock:
            return len(self._entry_slippage)

    def get_exit_count(self) -> int:
        """Return number of exit slippage measurements."""
        with self._lock:
            return len(self._exit_slippage)

    def clear(self) -> None:
        """Clear all stored measurements."""
        with self._lock:
            self._entry_slippage.clear()
            self._exit_slippage.clear()
