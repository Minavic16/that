"""Portfolio state for the execution core (trades, balance, peak)."""
from __future__ import annotations

from nestquant.research.shared.execution.contracts import Trade


class Portfolio:
    """Holds open/closed trades and cash balance for a backtest run."""

    def __init__(self, initial_balance: float):
        self.trades: list[Trade] = []
        self.open_trades: list[Trade] = []
        self.balance = initial_balance
        self.peak_balance = initial_balance

    def reset(self, initial_balance: float) -> None:
        """Reset cash balance/peak only (trade history is preserved)."""
        self.balance = initial_balance
        self.peak_balance = initial_balance

    def can_open(self, max_open_trades: int) -> bool:
        return len(self.open_trades) < max_open_trades

    def open(self, trade: Trade) -> None:
        self.open_trades.append(trade)
        self.trades.append(trade)

    def apply_exit(self, trade: Trade, pnl: float) -> None:
        """Apply closed-trade PnL to balance/peak (trade must already be closed)."""
        self.balance += pnl
        self.peak_balance = max(self.peak_balance, self.balance)
        if trade in self.open_trades:
            self.open_trades.remove(trade)
