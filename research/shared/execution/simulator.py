"""Strategy-agnostic execution simulator (fills, exits, results).

No imports from production strategy or risk modules. Callers provide signal
intents and optional per-close callbacks (e.g. circuit-breaker recording).
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from nestquant.research.shared.execution.contracts import (
    BacktestConfig,
    SignalIntent,
    Trade,
)
from nestquant.research.shared.execution.portfolio import Portfolio

OnTradeClosed = Callable[[float, float, float], None]


class ExecutionSimulator:
    """Simulates entry fills, SL/TP exits, costs, and result metrics."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.portfolio = Portfolio(config.initial_balance)

    def reset(self, initial_balance: Optional[float] = None) -> None:
        self.portfolio.reset(
            self.config.initial_balance if initial_balance is None else initial_balance
        )

    def open_trade(
        self, intent: SignalIntent, timestamp: pd.Timestamp
    ) -> Optional[Trade]:
        """Open a trade from a signal intent. Returns None if sizing fails."""
        spread_cost = self.config.spread_pips * 0.0001
        slippage_cost = self.config.slippage_pips * 0.0001

        if intent.direction == "BUY":
            entry_price = intent.entry_price + spread_cost / 2 + slippage_cost
        else:
            entry_price = intent.entry_price - spread_cost / 2 - slippage_cost

        risk_amount = self.portfolio.balance * self.config.risk_per_trade
        sl_distance = abs(entry_price - intent.sl_price)

        if sl_distance <= 0:
            return None

        lot_size = risk_amount / (sl_distance * 100000)
        lot_size = max(0.01, round(lot_size, 2))

        trade = Trade(
            pair=intent.pair,
            direction=intent.direction,
            entry_price=entry_price,
            entry_time=timestamp,
            sl_price=intent.sl_price,
            tp_price=intent.tp_price,
            lot_size=lot_size,
        )
        self.portfolio.open(trade)
        return trade

    def check_exits(
        self,
        pair: str,
        df: pd.DataFrame,
        on_close: Optional[OnTradeClosed] = None,
    ) -> list[Trade]:
        """Check SL/TP exits for open trades on this pair.

        on_close(pnl, balance, peak) is invoked after each exit's balance
        update and before the trade is removed from the open list — matching
        legacy circuit-breaker recording order.
        """
        current_high = df["high"].iloc[-1]
        current_low = df["low"].iloc[-1]
        timestamp = df.index[-1]
        slippage = self.config.slippage_pips * 0.0001

        trades_to_close: list[Trade] = []

        for trade in self.portfolio.open_trades:
            if trade.pair != pair:
                continue

            exit_price: Optional[float] = None
            exit_reason = ""

            if trade.direction == "BUY":
                if current_low <= trade.sl_price:
                    exit_price = trade.sl_price
                    exit_reason = "sl"
                elif current_high >= trade.tp_price:
                    exit_price = trade.tp_price
                    exit_reason = "tp"
            else:
                if current_high >= trade.sl_price:
                    exit_price = trade.sl_price
                    exit_reason = "sl"
                elif current_low <= trade.tp_price:
                    exit_price = trade.tp_price
                    exit_reason = "tp"

            if exit_price is None:
                continue

            if exit_reason == "sl":
                exit_price -= slippage
            else:
                exit_price += slippage

            if trade.direction == "BUY":
                pnl = (exit_price - trade.entry_price) * trade.lot_size * 100000
            else:
                pnl = (trade.entry_price - exit_price) * trade.lot_size * 100000

            commission = self.config.commission_per_lot * trade.lot_size
            pnl -= commission

            trade.exit_price = exit_price
            trade.exit_time = timestamp
            trade.pnl = pnl
            trade.exit_reason = exit_reason

            self.portfolio.balance += pnl
            self.portfolio.peak_balance = max(
                self.portfolio.peak_balance, self.portfolio.balance
            )
            trades_to_close.append(trade)

            if on_close is not None:
                on_close(
                    pnl, self.portfolio.balance, self.portfolio.peak_balance
                )

        for trade in trades_to_close:
            if trade in self.portfolio.open_trades:
                self.portfolio.open_trades.remove(trade)

        return trades_to_close

    def get_results(self) -> dict:
        """Compute backtest result metrics from closed trades."""
        closed_trades = [t for t in self.portfolio.trades if not t.is_open]

        if not closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            }

        pnls = [t.pnl for t in closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0.0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float("inf")
        total_pnl = sum(pnls)
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        equity_curve = np.cumsum(pnls) + self.config.initial_balance
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak * 100
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0.0

        if len(pnls) > 1:
            sharpe = (
                np.mean(pnls) / np.std(pnls) * np.sqrt(252)
                if np.std(pnls) > 0
                else 0.0
            )
        else:
            sharpe = 0.0

        return {
            "total_trades": len(closed_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_pnl": total_pnl,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": np.mean(pnls),
            "trades": closed_trades,
        }
