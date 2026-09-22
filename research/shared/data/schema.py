"""Canonical OHLCV schema definition.

Column names, types, and constraints for `OHLCVFrame`.
Required columns are the minimum for a valid frame; volume and
spread are optional so the schema works for any OHLCV research
program (not only programs that record volume/spread).
"""

from __future__ import annotations

import pandas as pd

# Full canonical column set.
OHLCV_COLUMNS: list[str] = ["open", "high", "low", "close", "volume", "spread"]

# Minimum columns for a frame to be loadable/validatable.
OHLCV_REQUIRED_COLUMNS: list[str] = ["open", "high", "low", "close"]

# Expected storage types for canonical columns.
OHLCV_COLUMN_TYPES: dict[str, type] = {
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
    "spread": float,
}

# Valid 4H bar-end hours (UTC).
FOUR_H_BAR_HOURS: set[int] = {0, 4, 8, 12, 16, 20}

# Expected interval between consecutive 4H bars, in hours.
# Plain int (not pd.Timedelta) to avoid import-time numeric-unit warnings.
FOUR_H_BAR_INTERVAL_HOURS: int = 4


def has_required_columns(df: pd.DataFrame) -> bool:
    """Check that all required OHLCV columns are present."""
    return all(c in df.columns for c in OHLCV_REQUIRED_COLUMNS)
