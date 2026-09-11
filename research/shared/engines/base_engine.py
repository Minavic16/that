"""
Base engine interface for trading engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class EngineState:
    """Current state of a trading engine."""

    running: bool = False
    pair: str = ""
    balance: float = 0.0
    equity: float = 0.0
    open_positions: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def profit_factor(self) -> float:
        if self.total_pnl <= 0:
            return 0.0
        return self.balance / (self.balance - self.total_pnl) if self.total_pnl != 0 else 0.0


class BaseEngine(ABC):
    """Abstract base class for trading engines."""

    def __init__(self, name: str):
        self.name = name
        self._state = EngineState()

    @property
    def state(self) -> EngineState:
        return self._state

    @abstractmethod
    def start(self) -> None:
        """Start the engine."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the engine."""
        ...

    @abstractmethod
    def on_bar(self, pair: str, df: pd.DataFrame) -> None:
        """
        Handle new bar data.

        Args:
            pair: Currency pair
            df: OHLCV DataFrame
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name}, running={self._state.running})>"
