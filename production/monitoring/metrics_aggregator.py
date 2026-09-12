"""
NestQuant Metrics Aggregator — Bridges Python Monitoring to Dashboard
=====================================================================
Collects metrics from monitoring modules and writes to a JSON file
that the Next.js dashboard API can read.

Call `aggregate()` periodically from the runner to keep metrics fresh.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from nestquant.core.configuration.constitution import CONSTITUTION
from nestquant.production.monitoring.equity_tracker import EquityTracker
from nestquant.production.monitoring.models import AccountSnapshot, StrategySnapshot


class MetricsAggregator:
    """Collects and persists all dashboard metrics."""

    def __init__(
        self,
        log_dir: str | Path = "logs/shadow_live",
        equity_tracker: Optional[EquityTracker] = None,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_path = self.log_dir / "metrics.json"
        self._equity_tracker = equity_tracker or EquityTracker()
        self._lock = threading.Lock()

        # Trading stats (accumulated over time)
        self._total_trades: int = 0
        self._winning_trades: int = 0
        self._losing_trades: int = 0
        self._total_pnl: float = 0.0
        self._avg_win: float = 0.0
        self._avg_loss: float = 0.0
        self._largest_win: float = 0.0
        self._largest_loss: float = 0.0
        self._current_losing_streak: int = 0
        self._max_losing_streak: int = 0
        self._consecutive_losing_days: int = 0
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._monthly_pnl: float = 0.0
        self._start_of_week: Optional[datetime] = None
        self._start_of_month: Optional[datetime] = None
        self._weekly_start_pnl: float = 0.0
        self._monthly_start_pnl: float = 0.0

        # Execution state
        self._last_signal: Optional[dict] = None
        self._last_trade: Optional[dict] = None
        self._execution_mode: str = "SHADOW"
        self._runner_healthy: bool = True
        self._last_evaluation: Optional[str] = None
        self._data_freshness: Optional[str] = None

    def record_snapshot(
        self,
        equity: float,
        balance: float,
        floating_pnl: float = 0.0,
        realized_pnl: float = 0.0,
    ) -> AccountSnapshot:
        """Record an equity snapshot."""
        with self._lock:
            return self._equity_tracker.record_snapshot(
                equity=equity,
                balance=balance,
                floating_pnl=floating_pnl,
                realized_pnl=realized_pnl,
            )

    def record_trade(
        self,
        pnl: float,
        equity: float,
        pair: str = "",
        direction: str = "",
    ) -> None:
        """Record a completed trade."""
        with self._lock:
            self._total_trades += 1
            self._total_pnl += pnl
            if pnl > 0:
                self._winning_trades += 1
                self._avg_win = (
                    (self._avg_win * (self._winning_trades - 1) + pnl)
                    / self._winning_trades
                )
                self._largest_win = max(self._largest_win, pnl)
                self._current_losing_streak = 0
            else:
                self._losing_trades += 1
                self._avg_loss = (
                    (self._avg_loss * (self._losing_trades - 1) + pnl)
                    / self._losing_trades
                )
                self._largest_loss = min(self._largest_loss, pnl)
                self._current_losing_streak += 1
                self._max_losing_streak = max(
                    self._max_losing_streak, self._current_losing_streak
                )

            self._daily_pnl += pnl

            # Weekly/monthly tracking
            now = datetime.now(UTC)
            if self._start_of_week is None or now.isocalendar()[1] != self._start_of_week.isocalendar()[1]:
                self._start_of_week = now
                self._weekly_start_pnl = self._total_pnl - pnl
            if self._start_of_month is None or now.month != self._start_of_month.month:
                self._start_of_month = now
                self._monthly_start_pnl = self._total_pnl - pnl

            self._weekly_pnl = self._total_pnl - self._weekly_start_pnl
            self._monthly_pnl = self._total_pnl - self._monthly_start_pnl

            self._last_trade = {
                "pair": pair,
                "direction": direction,
                "pnl": pnl,
                "equity": equity,
                "timestamp": now.isoformat(),
            }

    def update_signal(self, signal: dict) -> None:
        """Record the latest signal."""
        with self._lock:
            self._last_signal = signal

    def update_runner_health(self, healthy: bool) -> None:
        """Update runner health status."""
        with self._lock:
            self._runner_healthy = healthy

    def update_evaluation_time(self) -> None:
        """Mark that an evaluation just occurred."""
        with self._lock:
            self._last_evaluation = datetime.now(UTC).isoformat()

    def update_data_freshness(self, timestamp: str) -> None:
        """Update data freshness timestamp."""
        with self._lock:
            self._data_freshness = timestamp

    def aggregate(self) -> dict[str, Any]:
        """Aggregate all metrics and write to JSON file."""
        with self._lock:
            # Get equity tracker data
            latest_snapshot = self._equity_tracker.get_latest()
            dd_info = self._equity_tracker.get_current_drawdown()
            daily_dd = self._equity_tracker.get_daily_drawdown()
            peak_to_trough = self._equity_tracker.get_peak_to_trough()

            # Compute derived metrics
            equity = latest_snapshot.equity if latest_snapshot else 0.0
            balance = latest_snapshot.balance if latest_snapshot else 0.0
            starting_capital = balance - self._total_pnl if balance > 0 else 0.0
            total_return_pct = (
                ((equity - starting_capital) / starting_capital * 100)
                if starting_capital > 0 else 0.0
            )

            win_rate = (
                self._winning_trades / self._total_trades * 100
                if self._total_trades > 0 else 0.0
            )

            gross_wins = self._avg_win * self._winning_trades if self._winning_trades > 0 else 0.0
            gross_losses = abs(self._avg_loss * self._losing_trades) if self._losing_trades > 0 else 0.0
            profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0.0

            expectancy = (
                (self._avg_win * win_rate / 100) + (self._avg_loss * (100 - win_rate) / 100)
                if self._total_trades > 0 else 0.0
            )

            # Risk utilization
            daily_loss_limit = CONSTITUTION.max_daily_loss_pct
            daily_loss_pct = abs(daily_dd) / equity * 100 if equity > 0 else 0.0
            remaining_daily_loss = max(0, daily_loss_limit * 100 - daily_loss_pct)

            dd_limit = CONSTITUTION.max_drawdown_pct
            current_dd_pct = dd_info.get("pct", 0.0)
            remaining_dd = max(0, dd_limit * 100 - current_dd_pct)

            # Health status
            if self._runner_healthy and current_dd_pct < dd_limit * 100:
                health_status = "GREEN"
            elif self._runner_healthy:
                health_status = "AMBER"
            else:
                health_status = "RED"

            metrics = {
                "timestamp": datetime.now(UTC).isoformat(),
                "health_status": health_status,

                # Account
                "account": {
                    "starting_capital": starting_capital,
                    "current_balance": balance,
                    "current_equity": equity,
                    "peak_equity": self._equity_tracker._peak_equity,
                    "available_capital": None,  # not available from MT5 in shadow
                },

                # P&L
                "pnl": {
                    "realized_pnl": latest_snapshot.realized_pnl if latest_snapshot else 0.0,
                    "unrealized_pnl": latest_snapshot.floating_pnl if latest_snapshot else 0.0,
                    "total_pnl": self._total_pnl,
                    "daily_pnl": self._daily_pnl,
                    "weekly_pnl": self._weekly_pnl,
                    "monthly_pnl": self._monthly_pnl,
                    "total_return_pct": round(total_return_pct, 2),
                },

                # Drawdown
                "drawdown": {
                    "current_drawdown_pct": round(current_dd_pct, 2),
                    "maximum_drawdown_pct": round(
                        peak_to_trough / self._equity_tracker._peak_equity * 100
                        if self._equity_tracker._peak_equity > 0 else 0.0, 2
                    ),
                    "daily_drawdown_pct": round(daily_dd, 2),
                    "drawdown_from_peak": round(dd_info.get("absolute", 0.0), 2),
                    "drawdown_from_starting_capital": round(
                        starting_capital - equity, 2
                    ) if starting_capital > 0 else 0.0,
                },

                # Trading
                "trading": {
                    "total_trades": self._total_trades,
                    "winning_trades": self._winning_trades,
                    "losing_trades": self._losing_trades,
                    "win_rate": round(win_rate, 1),
                    "profit_factor": round(profit_factor, 3),
                    "average_win": round(self._avg_win, 2),
                    "average_loss": round(self._avg_loss, 2),
                    "expectancy": round(expectancy, 4),
                    "average_r": None,  # not tracked in live
                    "largest_win": round(self._largest_win, 2),
                    "largest_loss": round(self._largest_loss, 2),
                    "current_losing_streak": self._current_losing_streak,
                    "max_losing_streak": self._max_losing_streak,
                    "open_positions": latest_snapshot.open_positions if latest_snapshot else 0,
                },

                # Risk
                "risk": {
                    "risk_per_trade_pct": CONSTITUTION.risk_per_trade_pct,
                    "daily_loss_limit_pct": CONSTITUTION.max_daily_loss_pct * 100,
                    "current_daily_loss_pct": round(daily_loss_pct, 2),
                    "max_drawdown_limit_pct": CONSTITUTION.max_drawdown_pct * 100,
                    "current_drawdown_pct": round(current_dd_pct, 2),
                    "remaining_daily_loss_pct": round(remaining_daily_loss, 2),
                    "remaining_drawdown_pct": round(remaining_dd, 2),
                    "remaining_trades_today": CONSTITUTION.max_trades_per_day,  # placeholder
                    "max_concurrent_positions": CONSTITUTION.max_concurrent_positions,
                    "max_total_exposure": CONSTITUTION.max_total_exposure,
                    "max_position_size_per_pair": CONSTITUTION.max_position_size_per_pair,
                    "kill_switch_active": False,  # updated by runner
                    "circuit_breaker_status": None,  # updated by runner
                },

                # Execution
                "execution": {
                    "last_signal": self._last_signal,
                    "last_trade": self._last_trade,
                    "execution_mode": self._execution_mode,
                    "mt5_connected": False,  # updated by runner
                    "bridge_health": "unknown",
                    "runner_health": "healthy" if self._runner_healthy else "degraded",
                    "data_freshness": self._data_freshness,
                    "last_evaluation": self._last_evaluation,
                },
            }

        # Atomic write
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, dir=str(self.log_dir), encoding="utf-8"
            ) as tmp:
                json.dump(metrics, tmp, indent=2, default=str)
                tmp_path = Path(tmp.name)
            tmp_path.replace(self.metrics_path)
        except Exception:
            pass

        return metrics
