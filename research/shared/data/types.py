"""Canonical market data types.

`MarketBar` is the atomic unit of market data. `OHLCVFrame` is the
canonical in-memory representation of a bar time series:

- `pd.DataFrame` with a UTC `pd.DatetimeIndex` (bar-end timestamps)
- columns: open, high, low, close, volume, spread (see `schema.py`)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

# Canonical timestamp type: always timezone-aware UTC.
Timestamp = pd.Timestamp

# Canonical bar collection type.
# Contract (enforced by `validate.validate_ohlcv`, not by the type system):
#   - index is a monotonically increasing UTC DatetimeIndex
#   - required columns: open, high, low, close
#   - optional columns: volume, spread
OHLCVFrame = pd.DataFrame


@dataclass(frozen=True)
class MarketBar:
    """Single OHLCV bar — the atomic unit of market data.

    Frozen: bars are immutable observations. Timestamp marks the END
    of the bar period and must be timezone-aware UTC.
    """

    timestamp: pd.Timestamp  # UTC, timezone-aware, bar-end
    pair: str  # e.g. "EUR/USD"
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float | None = None

    def validate(self) -> list[str]:
        """Self-validation. Returns error strings; empty list if valid."""
        errors: list[str] = []

        if not isinstance(self.timestamp, pd.Timestamp):
            errors.append(f"timestamp is {type(self.timestamp)}, expected pd.Timestamp")
        else:
            if self.timestamp.tz is None:
                errors.append("timestamp is timezone-naive, expected UTC")
            elif str(self.timestamp.tz) != "UTC":
                errors.append(f"timestamp tz is {self.timestamp.tz}, expected UTC")

        if not isinstance(self.pair, str) or not self.pair:
            errors.append(f"pair is {self.pair!r}, expected non-empty str")

        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or value != value:  # NaN check
                errors.append(f"{name} is {value!r}, expected a real number")
            elif not math.isfinite(value):
                errors.append(f"{name} is {value}, expected a finite number")
            elif value <= 0:
                errors.append(f"{name} is {value}, expected > 0")

        prices_valid = not any(e.split(" ")[0] in ("open", "high", "low", "close") for e in errors)
        if prices_valid:
            if self.high < self.low:
                errors.append(f"high ({self.high}) < low ({self.low})")
            if self.high < self.open:
                errors.append(f"high ({self.high}) < open ({self.open})")
            if self.high < self.close:
                errors.append(f"high ({self.high}) < close ({self.close})")
            if self.low > self.open:
                errors.append(f"low ({self.low}) > open ({self.open})")
            if self.low > self.close:
                errors.append(f"low ({self.low}) > close ({self.close})")

        if not isinstance(self.volume, (int, float)) or self.volume != self.volume:
            errors.append(f"volume is {self.volume!r}, expected a real number")
        elif not math.isfinite(self.volume):
            errors.append(f"volume is {self.volume}, expected a finite number")
        elif self.volume < 0:
            errors.append(f"volume is {self.volume}, expected >= 0")

        if self.spread is not None:
            if not isinstance(self.spread, (int, float)) or self.spread != self.spread:
                errors.append(f"spread is {self.spread!r}, expected a real number or None")
            elif not math.isfinite(self.spread):
                errors.append(f"spread is {self.spread}, expected a finite number or None")
            elif self.spread < 0:
                errors.append(f"spread is {self.spread}, expected >= 0")

        return errors
