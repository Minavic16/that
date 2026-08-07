"""
ADX (Average Directional Index) calculation using Wilder's smoothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index (ADX) using Wilder's smoothing.
    ADX measures trend strength regardless of direction.
    > 25 = trending, < 20 = ranging.

    Args:
        df: OHLCV DataFrame with 'high', 'low', 'close' columns
        period: ADX period (default: 14)

    Returns:
        Series of ADX values
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

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    pos_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    neg_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    tr_smooth = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    pdi = 100.0 * pos_dm.ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan)
    ndi = 100.0 * neg_dm.ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan)

    dx = (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan) * 100.0
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx.fillna(0.0)
