"""Execution-layer data contracts (strategy-agnostic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


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


@dataclass
class SignalIntent:
    """Strategy-agnostic entry intent consumed by the execution core.

    Compatible with research/production SignalResult field names so adapters
    can convert without reshaping strategy output.
    """

    pair: str
    direction: str
    strength: float = 0.0
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.direction in ("BUY", "SELL") and self.strength > 0


def to_signal_intent(signal: Any) -> SignalIntent:
    """Coerce a SignalResult-like object (or SignalIntent) to SignalIntent."""
    if isinstance(signal, SignalIntent):
        return signal
    metadata = getattr(signal, "metadata", None)
    return SignalIntent(
        pair=signal.pair,
        direction=signal.direction,
        strength=float(getattr(signal, "strength", 0.0) or 0.0),
        entry_price=signal.entry_price,
        sl_price=signal.sl_price,
        tp_price=signal.tp_price,
        metadata=dict(metadata) if metadata else {},
    )
