"""
Base signal interface for all signal generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class SignalResult:
    """Result of a signal generation step."""

    pair: str
    direction: str  # "BUY", "SELL", or "NEUTRAL"
    strength: float = 0.0  # 0.0 to 1.0
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Return True if this is an actionable signal."""
        return self.direction in ("BUY", "SELL") and self.strength > 0


class BaseSignal(ABC):
    """Abstract base class for all signal generators."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate(self, df: pd.DataFrame, pair: str) -> SignalResult:
        """
        Generate a signal from OHLCV data.

        Args:
            df: OHLCV DataFrame (may be resampled to target timeframe)
            pair: Currency pair identifier

        Returns:
            SignalResult with direction, strength, and pricing
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"
