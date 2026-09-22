"""Canonical return/volatility feature boundaries.

Canonical pure functions for log-return construction and realized
volatility (backward features and forward targets).

These intentionally live HERE rather than re-exporting R2.1
`apparatus/features/` code: the Research OS data layer must not
import workload-specific packages (dependency direction is
workloads → Research OS, never the reverse; see package `__init__`).
Behavioral equivalence with the R2.1 implementations is pinned by
hand-computed expectations in `tests/research/test_data_loader.py`
(`test_ohlcv_with_features`), not by cross-package imports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_log_returns(close: pd.Series) -> pd.Series:
    """Compute log returns: r_t = log(close_t / close_{t-1}).

    CAUSAL: each return uses only the current and previous close.
    The first observation is NaN (no previous close available).
    """
    return np.log(close / close.shift(1))


def realized_volatility_forward(close: pd.Series, horizon: int) -> pd.Series:
    """Compute forward realized-volatility target.

    RV(t, h) = sqrt(sum(r[t+i]^2, i=1..h)) — realized volatility
    (sqrt of realized variance), NOT sample standard deviation.
    At h=1 this reduces cleanly to |r[t+1]|.

    The result is shifted by -horizon to align with forecast time t.
    The last `horizon` values are NaN (insufficient future data).
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    log_ret = np.log(close / close.shift(1))
    forward_variance = log_ret.pow(2).rolling(window=horizon, min_periods=horizon).sum()
    return np.sqrt(forward_variance.shift(-horizon))


def realized_volatility_backward(returns: pd.Series, window: int) -> pd.Series:
    """Compute backward-looking realized volatility (rolling std).

    RV_t(window) = std(r_{t-window+1}, ..., r_t).
    For model INPUT FEATURES only, never for forward targets.
    """
    return returns.rolling(window=window, min_periods=window).std()
