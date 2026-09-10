"""NestQuant signals module."""

from nestquant.signals.base import BaseSignal, SignalResult
from nestquant.signals.breakout import BreakoutSignal

__all__ = [
    "BaseSignal",
    "SignalResult",
    "BreakoutSignal",
]
