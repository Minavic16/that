"""
Backtest engine for strategy validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from nestquant.engines.base_engine import BaseEngine
from nestquant.indicators.session import is_active_session
from nestquant.risk.circuit_breakers import BreakerSuite
from nestquant.signals.base import BaseSignal, SignalResult


@dataclass
class Trade:
    """Represents a single trade."""

    pair: str
    direction: str
    entry_price: float
    entry_time: pd.Timestamp
    sl_price: float
    tp_price: float
    lot_size: float
    exit_price: Optional[float] = None
    exit_time: Optional[pd.Timestamp] = None
    pnl: float = 0.0
    exit_reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def duration(self) -> Optional[pd.Timedelta]:
        if self.entry_time and self.exit_time:
            return self.exit_time - self.entry_time
        return None


@dataclass
class BacktestConfig:
    """Backtest engine configuration."""

    initial_balance: float = 10000.0
    risk_per_trade: float = 0.02
    max_open_trades: int = 1
    commission_per_lot: float = 6.0
    spread_pips: float = 1.0
    slippage_pips: float = 0.1


class BacktestEngine(BaseEngine):
    """
    Backtest engine for strategy validation.

    Simulates trade execution with realistic cost modeling.
    """

    def __init__(
        self,
        signal: BaseSignal,
        config: Optional[BacktestConfig] = None,
    ):
        super().__init__("backtest")
        self.signal = signal
        self.config = config or BacktestConfig()
        self._trades: list[Trade] = []
        self._open_trades: list[Trade] = []
        self._balance = self.config.initial_balance
        self._peak_balance = self.config.initial_balance
        self._breakers = BreakerSuite()

    def start(self) -> None:
        """Start the backtest engine."""
        self._state.running = True
        self._state.balance = self.config.initial_balance
        self._state.equity = self.config.initial_balance
        self._balance = self.config.initial_balance
        self._peak_balance = self.config.initial_balance

    def stop(self) -> None:
        """Stop the backtest engine."""
        self._state.running = False

    def on_bar(self, pair: str, df: pd.DataFrame) -> None:
        """
        Process new bar data.

        Args:
            pair: Currency pair
            df: OHLCV DataFrame
        """
        if not self._state.running:
            return

        # Check session filter
        if not is_active_session(df.index[-1]):
            return

        # Close existing trades (check SL/TP)
        self._check_exits(pair, df)

        # Generate new signal
        signal = self.signal.generate(df, pair)

        if signal.is_active and len(self._open_trades) < self.config.max_open_trades:
            self._open_trade(signal, df.index[-1])

        # Update state
        self._update_state()

    def _open_trade(self, signal: SignalResult, timestamp: pd.Timestamp) -> None:
        """Open a new trade."""
        # Apply spread and slippage
        spread_cost = self.config.spread_pips * 0.0001  # Convert to price
        slippage_cost = self.config.slippage_pips * 0.0001

        if signal.direction == "BUY":
            entry_price = signal.entry_price + spread_cost / 2 + slippage_cost
        else:
            entry_price = signal.entry_price - spread_cost / 2 - slippage_cost

        # Calculate position size
        risk_amount = self._balance * self.config.risk_per_trade
        sl_distance = abs(entry_price - signal.sl_price)

        if sl_distance <= 0:
            return

        lot_size = risk_amount / (sl_distance * 100000)  # Standard lot = 100k units
        lot_size = max(0.01, round(lot_size, 2))  # Round to min lot

        trade = Trade(
            pair=signal.pair,
            direction=signal.direction,
            entry_price=entry_price,
            entry_time=timestamp,
            sl_price=signal.sl_price,
            tp_price=signal.tp_price,
            lot_size=lot_size,
        )

        self._open_trades.append(trade)
        self._trades.append(trade)

    def _check_exits(self, pair: str, df: pd.DataFrame) -> None:
        """Check for trade exits (SL/TP hits)."""
        current_high = df["high"].iloc[-1]
        current_low = df["low"].iloc[-1]
        timestamp = df.index[-1]

        trades_to_close = []

        for trade in self._open_trades:
            if trade.pair != pair:
                continue

            exit_price = None
            exit_reason = ""

            if trade.direction == "BUY":
                # Check SL
                if current_low <= trade.sl_price:
                    exit_price = trade.sl_price
                    exit_reason = "sl"
                # Check TP
                elif current_high >= trade.tp_price:
                    exit_price = trade.tp_price
                    exit_reason = "tp"
            else:  # SELL
                # Check SL
                if current_high >= trade.sl_price:
                    exit_price = trade.sl_price
                    exit_reason = "sl"
                # Check TP
                elif current_low <= trade.tp_price:
                    exit_price = trade.tp_price
                    exit_reason = "tp"

            if exit_price is not None:
                # Apply slippage
                slippage = self.config.slippage_pips * 0.0001
                if exit_reason == "sl":
                    exit_price -= slippage  # Slippage against us on SL
                else:
                    exit_price += slippage  # Slippage against us on TP

                # Calculate PnL
                if trade.direction == "BUY":
                    pnl = (exit_price - trade.entry_price) * trade.lot_size * 100000
                else:
                    pnl = (trade.entry_price - exit_price) * trade.lot_size * 100000

                # Subtract commission
                commission = self.config.commission_per_lot * trade.lot_size
                pnl -= commission

                trade.exit_price = exit_price
                trade.exit_time = timestamp
                trade.pnl = pnl
                trade.exit_reason = exit_reason

                self._balance += pnl
                self._peak_balance = max(self._peak_balance, self._balance)

                trades_to_close.append(trade)

                # Record for circuit breakers
                self._breakers.record_trade(pnl, self._balance, self._peak_balance)

        # Remove closed trades
        for trade in trades_to_close:
            self._open_trades.remove(trade)

    def _update_state(self) -> None:
        """Update engine state."""
        self._state.balance = self._balance
        self._state.equity = self._balance
        self._state.open_positions = len(self._open_trades)
        self._state.total_trades = len([t for t in self._trades if not t.is_open])
        self._state.winning_trades = len([t for t in self._trades if t.pnl > 0])
        self._state.losing_trades = len([t for t in self._trades if t.pnl < 0])
        self._state.total_pnl = sum(t.pnl for t in self._trades)

    def get_results(self) -> dict:
        """Get backtest results."""
        closed_trades = [t for t in self._trades if not t.is_open]

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

        # Calculate metrics
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float("inf")
        total_pnl = sum(pnls)
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        # Max drawdown
        equity_curve = np.cumsum(pnls) + self.config.initial_balance
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak * 100
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0.0

        # Sharpe ratio (simplified)
        if len(pnls) > 1:
            sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0.0
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
