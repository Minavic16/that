"""Z-Score Research Engine — Causal Feature Calculation.

All features at timestamp t use only data available at or before t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from zscore.contracts import FeatureSet


def causal_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """Causal Average True Range.

    At bar i, ATR is the rolling mean of true range over the last `period` bars.
    Uses Wilder's smoothing: ATR[i] = (ATR[i-1] * (period-1) + TR[i]) / period.

    NaN behavior: ATR[0:period-1] = NaN (insufficient data for initial mean).
    Warmup: first `period` bars return NaN.
    """
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def causal_realized_volatility(
    close: np.ndarray, period: int, bars_per_day: int = 24
) -> np.ndarray:
    """Causal realized volatility (annualized from log returns).

    RV[i] = std(log(close[j]/close[j-1]) for j in [i-period+1, i]) * sqrt(252 * bars_per_day)
    Computed from `period` log returns ending at bar i.

    Args:
        close: Price array
        period: Number of log-returns in the rolling window
        bars_per_day: Trading bars per day for annualization.
            Defaults to 24 (1H bars). Common values:
            1440=1min, 288=5min, 96=15min, 48=30min, 24=1h, 6=4h, 1=1day.

    NaN behavior: first `period` bars return NaN.
    Warmup: first `period` bars return NaN.
    """
    n = len(close)
    rv = np.full(n, np.nan)
    if n < period + 1:
        return rv
    log_returns = np.diff(np.log(close))
    ann_factor = np.sqrt(252 * bars_per_day)
    for i in range(period, n):
        window = log_returns[i - period:i]
        rv[i] = float(np.std(window, ddof=1)) * ann_factor
    return rv


def causal_ema_distance(close: np.ndarray, span: int) -> np.ndarray:
    """Causal EMA distance: (close - EMA) / EMA.

    At bar i, EMA is computed from close[0:i+1].

    NaN behavior: no NaN output (EMA starts from bar 0).
    Warmup: EMA is biased for first `span` bars, but computation is valid.
    """
    n = len(close)
    ema = np.full(n, np.nan)
    ema[0] = close[0]
    alpha = 2.0 / (span + 1)
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    distance = np.where(ema != 0, (close - ema) / ema, 0.0)
    return distance


def compute_features(
    pair: str,
    timestamps: pd.DatetimeIndex,
    open: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_period: int = 14,
    rv_period: int = 20,
    ema_span: int = 200,
    bars_per_day: int = 24,
) -> FeatureSet:
    """Compute all causal features at each bar.

    Args:
        pair: instrument pair name
        timestamps: UTC timestamps
        open/high/low/close: OHLC arrays
        atr_period: ATR lookback
        rv_period: realized volatility lookback
        ema_span: EMA span for distance calculation
        bars_per_day: Trading bars per day for RV annualization.
            Defaults to 24 (1H bars). Use 1440 for 1min, 24 for 1h, 6 for 4h.

    Returns:
        FeatureSet with ATR%, RV, and EMA distances
    """
    atr = causal_atr(high, low, close, atr_period)
    atr_pct = np.where(close > 0, atr / close * 100, 0.0)
    atr_pct = np.where(np.isnan(atr), np.nan, atr_pct)

    rv = causal_realized_volatility(close, rv_period, bars_per_day=bars_per_day)
    dist_ema200 = causal_ema_distance(close, ema_span)
    dist_ema50 = causal_ema_distance(close, 50)

    return FeatureSet(
        pair=pair,
        timestamps=timestamps,
        atr_pct=atr_pct,
        rv_20=rv,
        dist_ema200=dist_ema200,
        dist_ema50=dist_ema50,
    )
