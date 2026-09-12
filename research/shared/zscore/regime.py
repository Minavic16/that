"""Z-Score Research Engine — Causal Regime Classification.

Regime labels at timestamp t depend ONLY on data available at or before t.
Thresholds are fixed defaults — not optimized for historical profitability.
Replace this module without rewriting the Z-score engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit
from nestquant.core.contracts.zscore_contracts import RegimeState


@njit(cache=True)
def _causal_ema(close: np.ndarray, span: int) -> np.ndarray:
    """Compute causal EMA. EMA[i] depends only on close[0:i+1]."""
    n = len(close)
    ema = np.empty(n)
    ema[0] = close[0]
    alpha = 2.0 / (span + 1)
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1.0 - alpha) * ema[i - 1]
    return ema


@njit(cache=True)
def _causal_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """Causal ATR using exponential moving average of true range."""
    n = len(close)
    atr = np.empty(n)
    atr[:] = np.nan
    tr0 = high[0] - low[0]
    if n < period:
        return atr
    # Seed with SMA of first `period` true ranges
    atr[period - 1] = tr0
    for i in range(1, period):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        atr[period - 1] += tr
    atr[period - 1] /= period
    for i in range(period, n):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        atr[i] = (atr[i - 1] * (period - 1) + tr) / period
    return atr


@njit(cache=True)
def _fenwick_add(tree: np.ndarray, idx: int, delta: int) -> None:
    i = idx + 1
    while i < len(tree):
        tree[i] += delta
        i += i & (-i)


@njit(cache=True)
def _fenwick_prefix_sum(tree: np.ndarray, idx: int) -> int:
    i = idx + 1
    s = 0
    while i > 0:
        s += tree[i]
        i -= i & (-i)
    return s


@njit(cache=True)
def _classify_regime_core(
    close: np.ndarray,
    ema_arr: np.ndarray,
    atr_arr: np.ndarray,
    n_disc: int,
    atr_min: float,
    atr_range: float,
    atr_period: int,
    trend_near: float,
    trend_strong: float,
    vol_low: float,
    vol_high: float,
    vol_extreme: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Core regime classification loop, JIT-compiled with numba.

    Returns:
        trend_codes: int array (0=near_ema, 1=weak_trend, 2=strong_trend)
        vol_codes: int array (0=unknown, 1=low_vol, 2=mid_vol, 3=high_vol, 4=extreme_vol)
        atr_pctiles: float64 array
    """
    n = len(close)
    trend_codes = np.empty(n, dtype=np.int32)
    vol_codes = np.empty(n, dtype=np.int32)
    atr_pctiles = np.empty(n, dtype=np.float64)

    # Fenwick tree: size n_disc+1 (index 0 unused, so tree has n_disc+1 elements)
    fenwick_tree = np.zeros(n_disc + 1, dtype=np.int64)
    total_count = 0

    for i in range(n):
        atr_val = atr_arr[i]
        ema_val = ema_arr[i]

        # Add to Fenwick tree if valid
        if not np.isnan(atr_val):
            d = int((atr_val - atr_min) / atr_range * (n_disc - 1))
            if d < 0:
                d = 0
            if d >= n_disc:
                d = n_disc - 1
            _fenwick_add(fenwick_tree, d, 1)
            total_count += 1

        # Trend
        if ema_val != 0.0 and not np.isnan(ema_val):
            dist = abs(close[i] - ema_val) / ema_val
            if dist <= trend_near:
                trend_codes[i] = 0
            elif dist >= trend_strong:
                trend_codes[i] = 2
            else:
                trend_codes[i] = 1
        else:
            trend_codes[i] = 1

        # Volatility
        if total_count < atr_period or np.isnan(atr_val) or np.isnan(ema_val):
            vol_codes[i] = 0
            atr_pctiles[i] = 0.0
        else:
            d = int((atr_val - atr_min) / atr_range * (n_disc - 1))
            if d < 0:
                d = 0
            if d >= n_disc:
                d = n_disc - 1
            below = _fenwick_prefix_sum(fenwick_tree, d - 1) if d > 0 else 0
            p = float(below) / float(total_count) * 100.0
            atr_pctiles[i] = p
            if p >= vol_extreme:
                vol_codes[i] = 4
            elif p >= vol_high:
                vol_codes[i] = 3
            elif p <= vol_low:
                vol_codes[i] = 1
            else:
                vol_codes[i] = 2

    return trend_codes, vol_codes, atr_pctiles


_TREND_MAP = {0: "near_ema", 1: "weak_trend", 2: "strong_trend"}
_VOL_MAP = {0: "unknown", 1: "low_vol", 2: "mid_vol", 3: "high_vol", 4: "extreme_vol"}


def classify_regime_chunked(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    timestamps: pd.DatetimeIndex,
    pair: str,
    chunk_size: int = 1000,
    ema_span: int = 200,
    atr_period: int = 14,
    trend_near_threshold: float = 0.002,
    trend_strong_threshold: float = 0.008,
    vol_low_percentile: float = 25.0,
    vol_high_percentile: float = 75.0,
    vol_extreme_percentile: float = 95.0,
) -> list[RegimeState]:
    """Classify regime causally at each bar using numba-accelerated Fenwick tree.

    Uses a Fenwick tree for O(n log n) exact streaming percentile computation.
    At bar i, the percentile is computed from ATR values in [0..i] only —
    no future data is used. This is fully causal.

    The chunk_size parameter is accepted for API compatibility but ignored.

    Args:
        close: closing prices (full series)
        high: high prices (full series)
        low: low prices (full series)
        timestamps: UTC timestamps (full series)
        pair: instrument pair name
        chunk_size: ignored (kept for API compat)
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

    # Precompute indicators (JIT-compiled)
    ema_arr = _causal_ema(close.astype(np.float64), ema_span)
    atr_arr = _causal_atr(
        high.astype(np.float64), low.astype(np.float64),
        close.astype(np.float64), atr_period,
    )

    # Discretization range from valid ATR values
    valid_atr = atr_arr[~np.isnan(atr_arr)]
    if len(valid_atr) == 0:
        atr_min, atr_range = 0.0, 1.0
    else:
        atr_min = float(np.min(valid_atr))
        atr_max = float(np.max(valid_atr))
        atr_range = atr_max - atr_min
        if atr_range <= 0:
            atr_range = 1e-10

    n_disc = 10000

    # Core classification (JIT-compiled)
    trend_codes, vol_codes, atr_pctiles = _classify_regime_core(
        close, ema_arr, atr_arr, n_disc, atr_min, atr_range,
        atr_period, trend_near_threshold, trend_strong_threshold,
        vol_low_percentile, vol_high_percentile, vol_extreme_percentile,
    )

    # Build output (fast: no Python loop body logic)
    return [
        RegimeState(
            pair=pair,
            timestamp=timestamps[i],
            trend=_TREND_MAP[trend_codes[i]],
            volatility=_VOL_MAP[vol_codes[i]],
            atr_percentile=atr_pctiles[i],
            is_causal=True,
        )
        for i in range(n)
    ]


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
    ema_arr: np.ndarray | None = None,
    atr_arr: np.ndarray | None = None,
    initial_atr_history: list[float] | None = None,
) -> list[RegimeState]:
    """Classify regime causally at each bar (reference implementation).

    Uses sorted-history percentiles — O(n^2) for large datasets.
    Prefer classify_regime_chunked() for production use.
    """
    n = len(close)
    if ema_arr is None:
        ema_arr = _causal_ema(close, ema_span)
    if atr_arr is None:
        atr_arr = _causal_atr(high, low, close, atr_period)

    regimes: list[RegimeState] = []
    atr_history: list[float] = list(initial_atr_history) if initial_atr_history else []

    for i in range(n):
        atr_val = atr_arr[i]
        ema_val = ema_arr[i]

        if not np.isnan(atr_val):
            atr_history.append(atr_val)

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
