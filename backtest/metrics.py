"""
Backtest performance metrics calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class BacktestMetrics:
    """Comprehensive backtest metrics."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_duration: Optional[float] = None


def calculate_metrics(
    pnls: list[float],
    initial_balance: float = 10000.0,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """
    Calculate comprehensive backtest metrics.

    Args:
        pnls: List of trade P&L values
        initial_balance: Starting balance
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino

    Returns:
        BacktestMetrics with all calculated metrics
    """
    if not pnls:
        return BacktestMetrics()

    pnls_array = np.array(pnls)
    wins = pnls_array[pnls_array > 0]
    losses = pnls_array[pnls_array < 0]

    # Basic metrics
    total_trades = len(pnls)
    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
    total_pnl = float(np.sum(pnls_array))

    # Profit factor
    profit_factor = float(np.sum(wins) / abs(np.sum(losses))) if len(losses) > 0 else float("inf")

    # Expectancy
    expectancy = float(np.mean(pnls_array))

    # Win/Loss metrics
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    largest_win = float(np.max(wins)) if len(wins) > 0 else 0.0
    largest_loss = float(np.min(losses)) if len(losses) > 0 else 0.0

    # Drawdown calculation
    equity_curve = np.cumsum(pnls_array) + initial_balance
    peak = np.maximum.accumulate(equity_curve)
    drawdown = peak - equity_curve
    drawdown_pct = drawdown / peak * 100

    max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
    max_drawdown_pct = float(np.max(drawdown_pct)) if len(drawdown_pct) > 0 else 0.0

    # Sharpe ratio (annualized)
    if len(pnls_array) > 1 and np.std(pnls_array) > 0:
        excess_returns = pnls_array - risk_free_rate
        sharpe_ratio = float(np.mean(excess_returns) / np.std(pnls_array) * np.sqrt(252))
    else:
        sharpe_ratio = 0.0

    # Sortino ratio (annualized)
    downside_returns = pnls_array[pnls_array < 0]
    if len(downside_returns) > 0 and np.std(downside_returns) > 0:
        downside_std = np.sqrt(np.mean(downside_returns**2))
        sortino_ratio = float(np.mean(pnls_array) / downside_std * np.sqrt(252))
    else:
        sortino_ratio = 0.0

    # Recovery factor
    recovery_factor = float(total_pnl / max_drawdown) if max_drawdown > 0 else 0.0

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        recovery_factor=recovery_factor,
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
    )
