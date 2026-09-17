"""
R2.1 Realized Volatility and Forward Target Construction
=========================================================

Canonical forward realized-volatility target for R2.1.

For horizon h:
    RV(t, h) = sqrt( sum(r[t+i]^2, i=1..h) )

At h=1:
    RV(t, 1) = |r[t+1]|

Per §C10 and §F4 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def realized_volatility_forward(
    close: pd.Series,
    horizon: int,
) -> pd.Series:
    """Compute forward realized-volatility target.

    Formula: RV(t, h) = sqrt( sum(r[t+i]^2, i=1..h) )

    This is NOT sample standard deviation.
    This is realized volatility: sqrt of realized variance.

    At h=1: RV(t, 1) = |r[t+1]|

    The target is shifted by -horizon to align with forecast timestamp t.

    Args:
        close: Series of close prices with DatetimeIndex.
        horizon: Forecast horizon in bars.

    Returns:
        Series of realized volatility targets.
        The last `horizon` values are NaN (insufficient future data).
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    # Compute log returns
    log_ret = np.log(close / close.shift(1))

    # Compute squared returns
    sq_ret = log_ret ** 2

    # Sum of squared returns over forward window
    # Use rolling sum with min_periods=horizon, then shift backward by horizon
    # so that target at time t uses returns from t+1 to t+horizon
    forward_variance = sq_ret.rolling(window=horizon, min_periods=horizon).sum()
    forward_variance = forward_variance.shift(-horizon)

    # Realized volatility = sqrt(variance)
    return np.sqrt(forward_variance)


def realized_volatility_backward(
    returns: pd.Series,
    window: int,
) -> pd.Series:
    """Compute backward-looking realized volatility (rolling std).

    Formula: RV_t(window) = std(r_{t-window+1}, ..., r_t)

    This is used for model INPUT FEATURES only, NOT for forward targets.

    Args:
        returns: Series of returns.
        window: Rolling window size.

    Returns:
        Series of rolling standard deviation.
    """
    return returns.rolling(window=window, min_periods=window).std()


def realized_variance_forward(
    close: pd.Series,
    horizon: int,
) -> pd.Series:
    """Compute forward realized variance (NOT volatility).

    Formula: RV_var(t, h) = sum(r[t+i]^2, i=1..h)

    This is the variance component before taking sqrt.
    Provided for completeness; use realized_volatility_forward for targets.

    Args:
        close: Series of close prices with DatetimeIndex.
        horizon: Forecast horizon in bars.

    Returns:
        Series of realized variance.
        The last `horizon` values are NaN.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    log_ret = np.log(close / close.shift(1))
    sq_ret = log_ret ** 2

    forward_variance = sq_ret.rolling(window=horizon, min_periods=horizon).sum()
    forward_variance = forward_variance.shift(-horizon)

    return forward_variance
