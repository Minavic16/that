"""
Monitoring Data Models
======================

Shared data types for the monitoring system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional


@dataclass
class MarketSnapshot:
    """Point-in-time market data from MT5."""

    timestamp: str
    symbol: str
    bid: float
    ask: float
    spread: float
    spread_pips: float
    last: float = 0.0
    volume: int = 0
    server_time: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "spread_pips": self.spread_pips,
            "last": self.last,
            "volume": self.volume,
            "server_time": self.server_time,
        }


@dataclass
class ExecutionSnapshot:
    """Execution quality measurement."""

    experiment_id: str = ""
    signal_id: str = ""
    order_id: str = ""
    position_id: str = ""
    requested_price: float = 0.0
    fill_price: float = 0.0
    entry_slippage_pips: float = 0.0
    exit_slippage_pips: float = 0.0
    submission_timestamp: str = ""
    fill_timestamp: str = ""
    execution_latency_ms: float = 0.0
    end_to_end_latency_ms: float = 0.0
    broker_retcode: int = 0
    execution_status: str = ""
    measured: bool = False

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "signal_id": self.signal_id,
            "order_id": self.order_id,
            "position_id": self.position_id,
            "requested_price": self.requested_price,
            "fill_price": self.fill_price,
            "entry_slippage_pips": self.entry_slippage_pips,
            "exit_slippage_pips": self.exit_slippage_pips,
            "submission_timestamp": self.submission_timestamp,
            "fill_timestamp": self.fill_timestamp,
            "execution_latency_ms": self.execution_latency_ms,
            "end_to_end_latency_ms": self.end_to_end_latency_ms,
            "broker_retcode": self.broker_retcode,
            "execution_status": self.execution_status,
            "measured": self.measured,
        }


@dataclass
class AccountSnapshot:
    """Point-in-time account state."""

    timestamp: str
    balance: float = 0.0
    equity: float = 0.0
    floating_pnl: float = 0.0
    realized_pnl: float = 0.0
    daily_pnl: float = 0.0
    peak_equity: float = 0.0
    current_drawdown: float = 0.0
    peak_to_trough_drawdown: float = 0.0
    drawdown_pct: float = 0.0
    open_positions: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "balance": self.balance,
            "equity": self.equity,
            "floating_pnl": self.floating_pnl,
            "realized_pnl": self.realized_pnl,
            "daily_pnl": self.daily_pnl,
            "peak_equity": self.peak_equity,
            "current_drawdown": self.current_drawdown,
            "peak_to_trough_drawdown": self.peak_to_trough_drawdown,
            "drawdown_pct": self.drawdown_pct,
            "open_positions": self.open_positions,
        }


@dataclass
class HealthSnapshot:
    """Point-in-time infrastructure health."""

    timestamp: str
    bridge_healthy: bool = False
    mt5_connected: bool = False
    mt5_initialized: bool = False
    response_time_ms: float = 0.0
    last_error: str = ""
    consecutive_failures: int = 0
    total_checks: int = 0
    total_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "bridge_healthy": self.bridge_healthy,
            "mt5_connected": self.mt5_connected,
            "mt5_initialized": self.mt5_initialized,
            "response_time_ms": self.response_time_ms,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "total_checks": self.total_checks,
            "total_failures": self.total_failures,
        }


@dataclass
class StrategySnapshot:
    """Point-in-time strategy health metrics."""

    timestamp: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    rolling_ev: float = 0.0
    ev_std: float = 0.0
    ev_variance: float = 0.0
    positive_ev_pct: float = 0.0
    current_losing_streak: int = 0
    max_losing_streak: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "rolling_ev": self.rolling_ev,
            "ev_std": self.ev_std,
            "ev_variance": self.ev_variance,
            "positive_ev_pct": self.positive_ev_pct,
            "current_losing_streak": self.current_losing_streak,
            "max_losing_streak": self.max_losing_streak,
        }


@dataclass
class LatencySnapshot:
    """Latency measurement."""

    timestamp: str = ""
    component: str = ""
    latency_ms: float = 0.0
    is_measured: bool = False

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "component": self.component,
            "latency_ms": self.latency_ms,
            "is_measured": self.is_measured,
        }
