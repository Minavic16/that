"""Z-Score Research Engine — Causal Z-Score Calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from zscore.contracts import ZScoreObservation


def compute_zscore_causal(
    close: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    lookback: int = 20,
) -> list[ZScoreObservation]:
    """Compute Z-score using only data available at each timestamp.

    At bar i, the rolling mean and rolling std are computed from
    close[i-lookback:i]. No future data is used.

    Args:
        close: array of closing prices
        timestamps: corresponding UTC timestamps
        pair: instrument pair name
        lookback: number of bars for rolling window

    Returns:
        List of ZScoreObservation (one per bar, NaN for warmup period)
    """
    n = len(close)
    observations: list[ZScoreObservation] = []

    for i in range(n):
        if i < lookback:
            observations.append(ZScoreObservation(
                pair=pair,
                timestamp=timestamps[i],
                close=float(close[i]),
                z_score=float('nan'),
                rolling_mean=float('nan'),
                rolling_std=float('nan'),
                lookback=lookback,
                is_causal=True,
            ))
            continue

        window = close[i - lookback:i]
        mean = float(np.mean(window))
        std = float(np.std(window, ddof=1))

        z = 0.0 if std == 0 or np.isnan(std) else (close[i] - mean) / std

        observations.append(ZScoreObservation(
            pair=pair,
            timestamp=timestamps[i],
            close=float(close[i]),
            z_score=z,
            rolling_mean=mean,
            rolling_std=std,
            lookback=lookback,
            is_causal=True,
        ))

    return observations


def compute_zscore_expanding(
    close: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    min_periods: int = 20,
) -> list[ZScoreObservation]:
    """Compute Z-score using an expanding window.

    At bar i, the mean and std are computed from close[0:i].
    No future data is used.

    Args:
        close: array of closing prices
        timestamps: corresponding UTC timestamps
        pair: instrument pair name
        min_periods: minimum bars before Z-score is computed

    Returns:
        List of ZScoreObservation
    """
    n = len(close)
    observations: list[ZScoreObservation] = []

    for i in range(n):
        if i < min_periods:
            observations.append(ZScoreObservation(
                pair=pair,
                timestamp=timestamps[i],
                close=float(close[i]),
                z_score=float('nan'),
                rolling_mean=float('nan'),
                rolling_std=float('nan'),
                lookback=i,
                is_causal=True,
            ))
            continue

        window = close[:i]
        mean = float(np.mean(window))
        std = float(np.std(window, ddof=1))

        z = 0.0 if std == 0 or np.isnan(std) else (close[i] - mean) / std

        observations.append(ZScoreObservation(
            pair=pair,
            timestamp=timestamps[i],
            close=float(close[i]),
            z_score=z,
            rolling_mean=mean,
            rolling_std=std,
            lookback=i,
            is_causal=True,
        ))

    return observations


def zscore_to_array(observations: list[ZScoreObservation]) -> np.ndarray:
    """Convert list of ZScoreObservation to numpy array of z-score values."""
    return np.array([o.z_score for o in observations])
