"""
Backtest engine for strategy validation.

Thin adapter: session filter + signal generation + BreakerSuite recording
around the strategy-agnostic execution core in research.shared.execution.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from nestquant.research.shared.engines.base_engine import BaseEngine
from nestquant.core.tooling.indicators.session import is_active_session
from nestquant.production.risk.circuit_breakers import BreakerSuite
from nestquant.research.shared.execution.contracts import (
    BacktestConfig,
    SignalIntent,
    Trade,
    to_signal_intent,
)
from nestquant.research.shared.execution.simulator import ExecutionSimulator

__all__ = ["BacktestConfig", "BacktestEngine", "Trade"]


class BacktestEngine(BaseEngine):
    """
    Backtest engine for strategy validation.

    Simulates trade execution with realistic cost modeling.
    """

    def __init__(
        self,
        signal,
        config: Optional[BacktestConfig] = None,
    ):
        super().__init__("backtest")
        self.signal = signal
        self._sim = ExecutionSimulator(config or BacktestConfig())
        self._breakers = BreakerSuite()

    @property
    def config(self) -> BacktestConfig:
        return self._sim.config

    @config.setter
    def config(self, value: BacktestConfig) -> None:
        self._sim.config = value

    @property
    def _trades(self) -> list[Trade]:
        return self._sim.portfolio.trades

    @property
    def _open_trades(self) -> list[Trade]:
        return self._sim.portfolio.open_trades

    @property
    def _balance(self) -> float:
        return self._sim.portfolio.balance

    @_balance.setter
    def _balance(self, value: float) -> None:
        self._sim.portfolio.balance = value

    @property
    def _peak_balance(self) -> float:
        return self._sim.portfolio.peak_balance

    @_peak_balance.setter
    def _peak_balance(self, value: float) -> None:
        self._sim.portfolio.peak_balance = value

    def start(self) -> None:
        """Start the backtest engine."""
        self._state.running = True
        self._state.balance = self.config.initial_balance
        self._state.equity = self.config.initial_balance
        self._sim.reset()

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

        if not is_active_session(df.index[-1]):
            return

        self._check_exits(pair, df)

        signal = self.signal.generate(df, pair)

        if signal.is_active and len(self._open_trades) < self.config.max_open_trades:
            self._open_trade(signal, df.index[-1])

        self._update_state()

    def _open_trade(self, signal, timestamp: pd.Timestamp) -> None:
        """Open a new trade from a SignalResult-like signal."""
        self._sim.open_trade(to_signal_intent(signal), timestamp)

    def _check_exits(self, pair: str, df: pd.DataFrame) -> None:
        """Check for trade exits (SL/TP hits) and record for circuit breakers."""

        def _record(pnl: float, balance: float, peak: float) -> None:
            self._breakers.record_trade(pnl, balance, peak)

        self._sim.check_exits(pair, df, on_close=_record)

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
        return self._sim.get_results()
