"""
R2.1 Log Return Construction
============================

Canonical log return computation for R2.1.
Returns are computed causally: r_t = log(close_t / close_{t-1}).

Per §C9 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_log_returns(close: pd.Series) -> pd.Series:
    """Compute log returns from close prices.

    Formula: r_t = log(close_t / close_{t-1})

    CAUSAL: Each return uses only the current and previous close.
    No future information is used.

    The first observation has NaN return (no previous close available).

    Args:
        close: Series of close prices with DatetimeIndex.

    Returns:
        Series of log returns, same index as input.
        First value is NaN.
    """
    return np.log(close / close.shift(1))


def verify_log_return(
    close_t: float,
    close_t_minus_1: float,
    expected: float,
    tolerance: float = 1e-10,
) -> bool:
    """Verify a log return matches expected value.

    Useful for hand-calculated regression tests.
    """
    actual = np.log(close_t / close_t_minus_1)
    return abs(actual - expected) < tolerance
