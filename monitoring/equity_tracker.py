"""
Equity Tracker — Equity Curve and Drawdown Analysis
=====================================================

Tracks equity snapshots, peak equity, drawdown (absolute and pct),
peak-to-trough drawdown, and daily P&L.
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

from monitoring.models import AccountSnapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


class EquityTracker:
    """Tracks equity curve and drawdown metrics over time."""

    def __init__(self, max_snapshots: int = 50000) -> None:
        self.max_snapshots = max_snapshots
        self._snapshots: list[AccountSnapshot] = []
        self._lock = threading.Lock()
        self._peak_equity = 0.0
        self._peak_to_trough = 0.0
        self._trough_since_peak = 0.0
        self._daily_start_equity: float | None = None
        self._current_day: str | None = None

    def record_snapshot(
        self,
        equity: float,
        balance: float,
        floating_pnl: float,
        realized_pnl: float,
    ) -> AccountSnapshot:
        """
        Store a point-in-time equity record.

        Returns the created AccountSnapshot with computed drawdown fields.
        """
        now_str = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        with self._lock:
            # Track daily start
            if self._current_day != today:
                self._current_day = today
                self._daily_start_equity = equity

            # Update peak
            if equity > self._peak_equity:
                self._peak_equity = equity
                self._trough_since_peak = equity

            # Track trough since peak
            if equity < self._trough_since_peak:
                self._trough_since_peak = equity

            # Peak-to-trough drawdown
            if self._peak_equity > 0:
                current_ptt = self._peak_equity - self._trough_since_peak
                if current_ptt > self._peak_to_trough:
                    self._peak_to_trough = current_ptt

            # Current drawdown
            current_dd = self._peak_equity - equity if self._peak_equity > 0 else 0.0
            dd_pct = (current_dd / self._peak_equity * 100) if self._peak_equity > 0 else 0.0

            # Daily drawdown
            daily_start = self._daily_start_equity if self._daily_start_equity else equity
            daily_pnl = equity - daily_start

            snapshot = AccountSnapshot(
                timestamp=now_str,
                balance=balance,
                equity=equity,
                floating_pnl=floating_pnl,
                realized_pnl=realized_pnl,
                daily_pnl=daily_pnl,
                peak_equity=self._peak_equity,
                current_drawdown=current_dd,
                peak_to_trough_drawdown=self._peak_to_trough,
                drawdown_pct=dd_pct,
            )

            self._snapshots.append(snapshot)
            if len(self._snapshots) > self.max_snapshots:
                self._snapshots = self._snapshots[-self.max_snapshots:]

        return snapshot

    def get_current_drawdown(self) -> dict[str, float]:
        """Return current drawdown in absolute and pct terms."""
        with self._lock:
            if not self._snapshots:
                return {"absolute": 0.0, "pct": 0.0}
            latest = self._snapshots[-1]
            return {
                "absolute": latest.current_drawdown,
                "pct": latest.drawdown_pct,
            }

    def get_daily_drawdown(self) -> float:
        """Return today's drawdown as a signed P&L value."""
        with self._lock:
            if not self._snapshots:
                return 0.0
            return self._snapshots[-1].daily_pnl

    def get_peak_to_trough(self) -> float:
        """Return max peak-to-trough drawdown in absolute terms."""
        with self._lock:
            return self._peak_to_trough

    def get_equity_curve(self) -> np.ndarray:
        """Return numpy array of equity values over time."""
        with self._lock:
            if not self._snapshots:
                return np.array([], dtype=float)
            return np.array([s.equity for s in self._snapshots], dtype=float)

    def get_drawdown_series(self) -> np.ndarray:
        """Return numpy array of drawdown percentages over time."""
        with self._lock:
            if not self._snapshots:
                return np.array([], dtype=float)
            return np.array([s.drawdown_pct for s in self._snapshots], dtype=float)

    def load_from_positions(self, client_base_url: str) -> AccountSnapshot | None:
        """
        Load current account state from /get_positions endpoint.

        Sums profit fields from open positions.
        """
        url = f"{client_base_url.rstrip('/')}/get_positions"
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if not body.get("ok", False):
                logger.warning("Positions endpoint returned ok=false")
                return None

            data = body.get("data", {})
            positions = data.get("positions", [])

            equity = float(data.get("equity", 0))
            balance = float(data.get("balance", 0))
            floating_pnl = sum(float(p.get("profit", 0)) for p in positions)
            realized_pnl = float(data.get("realized_pnl", 0))

            return self.record_snapshot(equity, balance, floating_pnl, realized_pnl)

        except (HTTPError, URLError, OSError) as exc:
            logger.warning("Failed to load positions: %s", exc)
            return None
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse positions data: %s", exc)
            return None

    def get_snapshots(self) -> list[AccountSnapshot]:
        """Return copy of stored snapshots."""
        with self._lock:
            return list(self._snapshots)

    def get_latest(self) -> AccountSnapshot | None:
        """Return the most recent snapshot, or None."""
        with self._lock:
            if not self._snapshots:
                return None
            return self._snapshots[-1]

    def clear(self) -> None:
        """Clear all stored data and reset tracking."""
        with self._lock:
            self._snapshots.clear()
            self._peak_equity = 0.0
            self._peak_to_trough = 0.0
            self._trough_since_peak = 0.0
            self._daily_start_equity = None
            self._current_day = None
