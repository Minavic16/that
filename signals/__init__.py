"""NestQuant signals module."""

from nestquant.signals.base import BaseSignal, SignalResult
from nestquant.signals.breakout import BreakoutSignal
from nestquant.signals.structured_entry import StructuredEntrySignal

__all__ = [
    "BaseSignal",
    "SignalResult",
    "BreakoutSignal",
    "StructuredEntrySignal",
]
