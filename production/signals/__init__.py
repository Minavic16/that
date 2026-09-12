"""NestQuant signals module."""

from nestquant.production.signals.base import BaseSignal, SignalResult
from nestquant.production.signals.breakout import BreakoutSignal

__all__ = [
    "BaseSignal",
    "SignalResult",
    "BreakoutSignal",
]
