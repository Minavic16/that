"""Z-Score Research Engine — Causal Z-Score Calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit
from zscore.contracts import ZScoreObservation


@njit(cache=True)
def _zscore_causal_core(
    close: np.ndarray, lookback: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numba-accelerated rolling Z-score computation.

    Returns (z_scores, rolling_mean, rolling_std) arrays.
    z_scores[i] = NaN for i < lookback.
    """
    n = len(close)
    z_out = np.empty(n)
    mean_out = np.empty(n)
    std_out = np.empty(n)

    for i in range(n):
        if i < lookback:
            z_out[i] = np.nan
            mean_out[i] = np.nan
            std_out[i] = np.nan
            continue

        window = close[i - lookback:i]
        m = 0.0
        for j in range(lookback):
            m += window[j]
        m /= lookback

        var = 0.0
        for j in range(lookback):
            diff = window[j] - m
            var += diff * diff
        var /= (lookback - 1)
        s = np.sqrt(var)

        mean_out[i] = m
        std_out[i] = s
        if s < 1e-10:
            z_out[i] = 0.0
        else:
            z_out[i] = (close[i] - m) / s

    return z_out, mean_out, std_out


def compute_zscore_causal(
    close: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    lookback: int = 20,
) -> list[ZScoreObservation]:
    """Compute Z-score using only data available at each timestamp.

    At bar i, the rolling mean and rolling std are computed from
    close[i-lookback:i]. No future data is used.

    Uses numba JIT compilation for performance on large datasets.

    Args:
        close: array of closing prices
        timestamps: corresponding UTC timestamps
        pair: instrument pair name
        lookback: number of bars for rolling window

    Returns:
        List of ZScoreObservation (one per bar, NaN for warmup period)
    """
    close_f64 = close.astype(np.float64)
    z_scores, rolling_mean, rolling_std = _zscore_causal_core(close_f64, lookback)

    return [
        ZScoreObservation(
            pair=pair,
            timestamp=timestamps[i],
            close=float(close[i]),
            z_score=z_scores[i],
            rolling_mean=rolling_mean[i],
            rolling_std=rolling_std[i],
            lookback=lookback,
            is_causal=True,
        )
        for i in range(len(close))
    ]


@njit(cache=True)
def _zscore_expanding_core(
    close: np.ndarray, min_periods: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numba-accelerated expanding Z-score computation."""
    n = len(close)
    z_out = np.empty(n)
    mean_out = np.empty(n)
    std_out = np.empty(n)

    for i in range(n):
        if i < min_periods:
            z_out[i] = np.nan
            mean_out[i] = np.nan
            std_out[i] = np.nan
            continue

        m = 0.0
        for j in range(i):
            m += close[j]
        m /= i

        var = 0.0
        for j in range(i):
            diff = close[j] - m
            var += diff * diff
        var /= (i - 1)
        s = np.sqrt(var)

        mean_out[i] = m
        std_out[i] = s
        if s < 1e-10:
            z_out[i] = 0.0
        else:
            z_out[i] = (close[i] - m) / s

    return z_out, mean_out, std_out


def compute_zscore_expanding(
    close: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    min_periods: int = 20,
) -> list[ZScoreObservation]:
    """Compute Z-score using an expanding window.

    At bar i, the mean and std are computed from close[0:i].
    No future data is used.
    """
    close_f64 = close.astype(np.float64)
    z_scores, rolling_mean, rolling_std = _zscore_expanding_core(close_f64, min_periods)

    return [
        ZScoreObservation(
            pair=pair,
            timestamp=timestamps[i],
            close=float(close[i]),
            z_score=z_scores[i],
            rolling_mean=rolling_mean[i],
            rolling_std=rolling_std[i],
            lookback=i if i < min_periods else min_periods,
            is_causal=True,
        )
        for i in range(len(close))
    ]


def zscore_to_array(observations: list[ZScoreObservation]) -> np.ndarray:
    """Convert list of ZScoreObservation to numpy array of z-score values."""
    return np.array([o.z_score for o in observations])
