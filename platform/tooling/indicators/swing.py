"""
Swing high/low detection for trailing stop placement.
"""

from __future__ import annotations

import pandas as pd


def swing_low_series(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Returns a Series where each bar holds the price of the most recent
    confirmed swing low (useful for trailing stop placement on BUY trades).

    Uses center=True internally for correct swing identification, then shifts
    by `lookback` to eliminate lookahead bias — the swing is only recognized
    after confirmation bars have elapsed.

    Args:
        df: OHLCV DataFrame with 'low' column
        lookback: Number of bars on each side to confirm swing (default: 5)

    Returns:
        Series of confirmed swing low prices
    """
    lows = df["low"]
    window = 2 * lookback + 1
    rolling_min = lows.rolling(window, center=True, min_periods=window).min()
    is_swing = lows == rolling_min

    # Shift by lookback to remove lookahead bias from center=True
    result = lows.where(is_swing).shift(lookback).ffill()
    return result


def swing_high_series(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Most recent confirmed swing high — for trailing stops on SELL trades.
    Shifted by lookback to avoid lookahead bias.

    Args:
        df: OHLCV DataFrame with 'high' column
        lookback: Number of bars on each side to confirm swing (default: 5)

    Returns:
        Series of confirmed swing high prices
    """
    highs = df["high"]
    window = 2 * lookback + 1
    rolling_max = highs.rolling(window, center=True, min_periods=window).max()
    is_swing = highs == rolling_max

    result = highs.where(is_swing).shift(lookback).ffill()
    return result
