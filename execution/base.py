"""
Base executor interface for trade execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OrderResult:
    """Result of an order execution."""

    success: bool
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    slippage_pips: float = 0.0
    commission: float = 0.0
    error: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        return self.success and self.fill_price is not None


class BaseExecutor(ABC):
    """Abstract base class for trade executors."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def submit_order(
        self,
        pair: str,
        side: str,
        lot_size: float,
        entry_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
    ) -> OrderResult:
        """
        Submit a trade order.

        Args:
            pair: Currency pair
            side: "BUY" or "SELL"
            lot_size: Position size in lots
            entry_price: Limit order price (None for market)
            sl_price: Stop loss price
            tp_price: Take profit price

        Returns:
            OrderResult with execution details
        """
        ...

    @abstractmethod
    def close_position(self, order_id: str) -> OrderResult:
        """
        Close an existing position.

        Args:
            order_id: ID of position to close

        Returns:
            OrderResult with close details
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """
        Get all open positions.

        Returns:
            List of position dictionaries
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"
