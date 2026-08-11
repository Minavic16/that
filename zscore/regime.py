"""Z-Score Research Engine — Causal Regime Classification.

Regime labels at timestamp t depend ONLY on data available at or before t.
Thresholds are fixed defaults — not optimized for historical profitability.
Replace this module without rewriting the Z-score engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from zscore.contracts import RegimeState


def _causal_ema(close: np.ndarray, span: int) -> np.ndarray:
    """Compute causal EMA. EMA[i] depends only on close[0:i+1]."""
    ema = np.full(len(close), np.nan)
    ema[0] = close[0]
    alpha = 2.0 / (span + 1)
    for i in range(1, len(close)):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    return ema


def _causal_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """Causal ATR using simple moving average of true range."""
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


def classify_regime(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    ema_span: int = 200,
    atr_period: int = 14,
    trend_near_threshold: float = 0.002,
    trend_strong_threshold: float = 0.008,
    vol_low_percentile: float = 25.0,
    vol_high_percentile: float = 75.0,
    vol_extreme_percentile: float = 95.0,
) -> list[RegimeState]:
    """Classify regime causally at each bar.

    At bar i:
    - EMA is computed from close[0:i+1]
    - ATR is computed from high/low/close[0:i+1]
    - Percentiles are computed from ATR values available up to bar i

    Args:
        close: closing prices
        high: high prices
        low: low prices
        timestamps: UTC timestamps
        pair: instrument pair name
        ema_span: EMA lookback for trend detection
        atr_period: ATR lookback for volatility
        trend_near_threshold: max distance from EMA to be "near_ema"
        trend_strong_threshold: min distance from EMA for "strong_trend"
        vol_low_percentile: percentile below which vol is "low"
        vol_high_percentile: percentile above which vol is "high"
        vol_extreme_percentile: percentile above which vol is "extreme"

    Returns:
        List of RegimeState, one per bar
    """
    n = len(close)
    ema = _causal_ema(close, ema_span)
    atr = _causal_atr(high, low, close, atr_period)

    regimes: list[RegimeState] = []
    atr_history: list[float] = []

    for i in range(n):
        atr_val = atr[i]
        ema_val = ema[i]

        # Accumulate ATR history for percentile computation (causal: only past)
        if not np.isnan(atr_val):
            atr_history.append(atr_val)

        # --- Volatility classification ---
        if len(atr_history) < atr_period or np.isnan(atr_val) or np.isnan(ema_val):
            vol = "unknown"
            atr_pct = 0.0
        else:
            atr_pct = float(np.searchsorted(sorted(atr_history), atr_val) / len(atr_history) * 100)
            if atr_pct >= vol_extreme_percentile:
                vol = "extreme_vol"
            elif atr_pct >= vol_high_percentile:
                vol = "high_vol"
            elif atr_pct <= vol_low_percentile:
                vol = "low_vol"
            else:
                vol = "mid_vol"

        # --- Trend classification ---
        distance = abs(close[i] - ema_val) / ema_val if ema_val != 0 else 0.0
        if distance <= trend_near_threshold:
            trend = "near_ema"
        elif distance >= trend_strong_threshold:
            trend = "strong_trend"
        else:
            trend = "weak_trend"

        regimes.append(RegimeState(
            pair=pair,
            timestamp=timestamps[i],
            trend=trend,
            volatility=vol,
            atr_percentile=atr_pct,
            is_causal=True,
        ))

    return regimes


def regime_to_dataframe(regimes: list[RegimeState]) -> pd.DataFrame:
    """Convert list of RegimeState to DataFrame for analysis."""
    return pd.DataFrame([
        {
            "pair": r.pair,
            "timestamp": r.timestamp,
            "trend": r.trend,
            "volatility": r.volatility,
            "atr_percentile": r.atr_percentile,
            "is_causal": r.is_causal,
        }
        for r in regimes
    ])
