"""
ATR (Average True Range) calculation using Wilder's smoothing.
"""

from __future__ import annotations

import pandas as pd


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range using Wilder's smoothing (EMA with span=period).

    True Range = max(H-L, |H-Cprev|, |L-Cprev|)

    Args:
        df: OHLCV DataFrame with 'high', 'low', 'close' columns
        period: ATR period (default: 14)

    Returns:
        Series of ATR values
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat(
        [high - low,
         (high - close.shift(1)).abs(),
         (low - close.shift(1)).abs()],
        axis=1
    ).max(axis=1)

    # Wilder smoothing = EMA with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()
