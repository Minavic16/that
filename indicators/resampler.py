"""
OHLCV resampling utilities.
"""

from __future__ import annotations

import pandas as pd

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
    Resample an OHLCV DataFrame to a higher timeframe.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
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


def build_all_timeframes(df_base: pd.DataFrame, base_timeframe: str = "1min") -> dict[str, pd.DataFrame]:
    """
    Pre-build all management timeframes from a base DataFrame.

    Args:
        df_base: OHLCV DataFrame at the base timeframe
        base_timeframe: Timeframe of the input DataFrame (e.g., "1min", "5min", "1h")

    Returns:
        Dict mapping interval string to resampled DataFrame
    """
    tfs: dict[str, pd.DataFrame] = {}
    for iv in ["1min", "5min", "15min", "30min", "1h", "4h", "1day"]:
        if iv == base_timeframe:
            tfs[iv] = df_base
        else:
            try:
                tfs[iv] = resample_ohlcv(df_base, iv)
            except Exception:
                pass
    return tfs
