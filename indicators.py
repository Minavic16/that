"""
indicators.py — Technical Indicators
======================================
ATR, swing high/low detection, session filter, OHLCV resampling.
All functions are pure (stateless) — they take DataFrames and return Series.
"""

import numpy as np
import pandas as pd
from config import (SESSION_OPEN_UTC, SESSION_CLOSE_UTC,
                    SKIP_MONDAY_OPEN, SKIP_FRIDAY_CLOSE)


# ── ATR ───────────────────────────────────────────────────────────────────────

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range using Wilder's smoothing (EMA with span=period).

    True Range = max(H-L, |H-Cprev|, |L-Cprev|)
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tr = pd.concat(
        [high - low,
         (high - close.shift(1)).abs(),
         (low  - close.shift(1)).abs()],
        axis=1
    ).max(axis=1)

    # Wilder smoothing = EMA with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ── Swing Highs / Lows ────────────────────────────────────────────────────────

def swing_low_series(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Returns a Series where each bar holds the price of the most recent
    confirmed swing low (useful for trailing stop placement on BUY trades).

    Uses center=True internally for correct swing identification, then shifts
    by `lookback` to eliminate lookahead bias — the swing is only recognized
    after confirmation bars have elapsed.
    """
    lows      = df["low"]
    window    = 2 * lookback + 1
    rolling_min = lows.rolling(window, center=True, min_periods=window).min()
    is_swing  = lows == rolling_min

    # Shift by lookback to remove lookahead bias from center=True
    result = lows.where(is_swing).shift(lookback).ffill()
    return result


def swing_high_series(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Most recent confirmed swing high — for trailing stops on SELL trades.
    Shifted by lookback to avoid lookahead bias.
    """
    highs     = df["high"]
    window    = 2 * lookback + 1
    rolling_max = highs.rolling(window, center=True, min_periods=window).max()
    is_swing  = highs == rolling_max

    result = highs.where(is_swing).shift(lookback).ffill()
    return result


# ── Session Filter ────────────────────────────────────────────────────────────

def is_active_session(dt: pd.Timestamp) -> bool:
    """
    Return True if dt falls within the London–New York overlap session (UTC).

    Filters applied:
        • Weekends excluded entirely
        • Monday 00:00–SESSION_OPEN_UTC skipped (erratic open)  [if configured]
        • Friday after 17:00 skipped (liquidity dries up)       [if configured]
        • Exact session window: SESSION_OPEN_UTC ≤ hour < SESSION_CLOSE_UTC

    💡 IMPROVEMENT SUGGESTION:
        Also filter out the Asian session for this strategy — the currency
        strength edge is weakest when only Tokyo is open and trends are ranging.
        The London–NY overlap (roughly 13:00–17:00 UTC) is the sweet spot
        where both sessions actively push the same currencies.
    """
    if dt.weekday() >= 5:
        return False  # Saturday / Sunday

    if SKIP_MONDAY_OPEN and dt.weekday() == 0 and dt.hour < SESSION_OPEN_UTC:
        return False

    if SKIP_FRIDAY_CLOSE and dt.weekday() == 4 and dt.hour >= 17:
        return False

    return SESSION_OPEN_UTC <= dt.hour < SESSION_CLOSE_UTC


# ── OHLCV Resampling ─────────────────────────────────────────────────────────

_RESAMPLE_RULES = {
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "H",
    "4h": "4H",
    "1day": "D",
}

def resample_ohlcv(df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """
    Resample a 1-min OHLCV DataFrame to a higher timeframe.

    Args:
        df:              1-min OHLCV DataFrame
        target_interval: One of "5min", "15min", "30min", "1h", "4h", "1day"

    Returns:
        Resampled DataFrame; rows with all-NaN (e.g. weekend gaps) removed.
    """
    rule = _RESAMPLE_RULES.get(target_interval)
    if rule is None:
        raise ValueError(
            f"Unknown interval '{target_interval}'. "
            f"Valid: {list(_RESAMPLE_RULES.keys())}"
        )

    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    agg = {k: v for k, v in agg.items() if k in df.columns}

    resampled = df.resample(rule).agg(agg).dropna(subset=["close"])
    return resampled


def build_all_timeframes(df_1min: pd.DataFrame) -> dict:
    """
    Pre-build all management timeframes from a 1-min base DataFrame.
    Returns dict: {interval_string: DataFrame}
    """
    tfs = {}
    for iv in ["1min", "5min", "15min", "30min", "1day"]:
        if iv == "1min":
            tfs[iv] = df_1min
        else:
            try:
                tfs[iv] = resample_ohlcv(df_1min, iv)
            except Exception:
                pass
    return tfs


# ── ADX ───────────────────────────────────────────────────────────────────────

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index (ADX) using Wilder's smoothing.
    ADX measures trend strength regardless of direction.
    > 25 = trending, < 20 = ranging.
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
    pos_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    neg_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr_smooth = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    pdi = 100.0 * pos_dm.ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan)
    ndi = 100.0 * neg_dm.ewm(alpha=1.0 / period, adjust=False).mean() / tr_smooth.replace(0, np.nan)

    dx = (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan) * 100.0
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx.fillna(0.0)


# ── Pip / Price Helpers ───────────────────────────────────────────────────────

def pip_size(pair: str) -> float:
    """Return pip size for a pair (0.01 for JPY pairs, 0.0001 otherwise)."""
    return 0.01 if "JPY" in pair.upper() else 0.0001


def price_to_pips(price_diff: float, pair: str) -> float:
    """Convert a raw price difference to pips."""
    return abs(price_diff) / pip_size(pair)


def pips_to_price(pips: float, pair: str) -> float:
    """Convert pips to raw price units."""
    return pips * pip_size(pair)