"""
EMA (Exponential Moving Average) calculation.
"""

from __future__ import annotations

import pandas as pd


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Exponential Moving Average.

    Args:
        df: DataFrame with 'close' column
        period: EMA period

    Returns:
        Series of EMA values
    """
    return df["close"].ewm(span=period, adjust=False).mean()
