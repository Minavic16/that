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
    Resample a 1-min OHLCV DataFrame to a higher timeframe.

    Args:
        df: 1-min OHLCV DataFrame
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


def build_all_timeframes(df_1min: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Pre-build all management timeframes from a 1-min base DataFrame.

    Args:
        df_1min: 1-minute OHLCV DataFrame

    Returns:
        Dict mapping interval string to resampled DataFrame
    """
    tfs: dict[str, pd.DataFrame] = {}
    for iv in ["1min", "5min", "15min", "30min", "1day"]:
        if iv == "1min":
            tfs[iv] = df_1min
        else:
            try:
                tfs[iv] = resample_ohlcv(df_1min, iv)
            except Exception:
                pass
    return tfs
