"""Phase 3 — Z-Score Statistical Research Engine.

Loads real data, computes Z-scores, and performs comprehensive analysis.
All computations are causal — no future data used.

Supports multiple timeframes via the `timeframe` parameter.
Forward-return horizons are expressed in bars (not elapsed time).
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from nestquant.research.shared.zscore.regime import classify_regime_chunked
from nestquant.research.shared.zscore.zscore import _zscore_causal_core

DATA_DIR = Path("/root/data")
RESULTS_DIR = Path("research/output/phase3")

# Default forward-return horizons (in bars) per timeframe.
# These are bar counts, NOT elapsed time. The same bar counts are used
# across timeframes so the research can compare behavior at different
# resolutions. Elapsed time = bars * bar_duration.
DEFAULT_HORIZONS = [5, 15, 30, 60, 120, 240]


@dataclass
class ZScoreResearchData:
    """Prepared research data for a single pair.

    All forward-return arrays are keyed by bar-count horizon.
    The `forward_returns` dict maps horizon (int) -> np.ndarray.
    """
    pair: str
    timeframe: str
    timestamps: pd.DatetimeIndex
    close: np.ndarray
    z_scores: np.ndarray
    regime_trend: list[str]
    regime_vol: list[str]
    forward_returns: dict[int, np.ndarray] = field(default_factory=dict)
    years: np.ndarray = field(default_factory=lambda: np.array([]))
    horizons: list[int] = field(default_factory=lambda: DEFAULT_HORIZONS.copy())


def load_pair(pair: str, timeframe: str = "1h") -> pd.DataFrame:
    """Load a single pair from pickle files.

    Tries timeframe subdirectory first, falls back to flat layout.
    """
    pair_file = pair.replace("/", "_")

    # Try timeframe subdirectory
    tf_dir = DATA_DIR / timeframe
    tf_path = tf_dir / f"{pair_file}.pkl"
    if tf_path.exists():
        with open(tf_path, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            return data[pair]
        return data

    # Fallback: flat layout (legacy 1min)
    flat_path = DATA_DIR / f"{pair_file}.pkl"
    if flat_path.exists():
        with open(flat_path, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            return data[pair]
        return data

    raise FileNotFoundError(f"No data found for {pair} at timeframe {timeframe}")


def prepare_pair(
    pair: str,
    timeframe: str = "1h",
    lookback: int = 20,
    horizons: list[int] | None = None,
    ema_span: int = 200,
    atr_period: int = 14,
) -> ZScoreResearchData | None:
    """Load, compute Z-scores, regimes, and forward returns for one pair.

    Args:
        pair: Currency pair (e.g., "EUR/USD")
        timeframe: Data timeframe ("1min", "5min", "15min", "30min", "1h", "4h")
        lookback: Z-score rolling window in bars
        horizons: Forward-return horizons in bars (default: DEFAULT_HORIZONS)
        ema_span: EMA span for regime classification in bars
        atr_period: ATR period for regime classification in bars

    Returns:
        ZScoreResearchData or None if loading fails
    """
    if horizons is None:
        horizons = DEFAULT_HORIZONS.copy()

    try:
        df = load_pair(pair, timeframe)
    except Exception as e:
        print(f"  Error loading {pair}: {e}")
        return None

    close = df["close"].values.astype(np.float64)
    timestamps = df.index
    n = len(close)

    # Compute Z-scores (causal)
    z_scores, rolling_mean, rolling_std = _zscore_causal_core(close, lookback)

    # Compute regimes (causal) — chunked processing with continuous state
    try:
        regimes = classify_regime_chunked(
            close,
            df["high"].values,
            df["low"].values,
            timestamps,
            pair,
            chunk_size=1000,
            ema_span=ema_span,
            atr_period=atr_period,
        )
        regime_trend = [r.trend for r in regimes]
        regime_vol = [r.volatility for r in regimes]
    except Exception:
        regime_trend = ["unknown"] * n
        regime_vol = ["unknown"] * n

    # Compute forward returns (causal: shift backwards)
    # Forward return = (close[t+h] - close[t]) / close[t]
    forward_returns = {}
    for h in horizons:
        fr = np.full(n, np.nan)
        if n > h:
            fr[:n - h] = (close[h:] - close[:n - h]) / close[:n - h]
        forward_returns[h] = fr

    years = np.array([t.year for t in timestamps])

    return ZScoreResearchData(
        pair=pair,
        timeframe=timeframe,
        timestamps=timestamps,
        close=close,
        z_scores=z_scores,
        regime_trend=regime_trend,
        regime_vol=regime_vol,
        forward_returns=forward_returns,
        years=years,
        horizons=horizons,
    )


def characterize_zscore_distribution(z_scores: np.ndarray) -> dict:
    """Compute Z-score distribution statistics."""
    valid = z_scores[~np.isnan(z_scores)]
    if len(valid) == 0:
        return {}

    return {
        "count": len(valid),
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "q5": float(np.percentile(valid, 5)),
        "q25": float(np.percentile(valid, 25)),
        "q50": float(np.percentile(valid, 50)),
        "q75": float(np.percentile(valid, 75)),
        "q95": float(np.percentile(valid, 95)),
        "skewness": float(pd.Series(valid).skew()),
        "kurtosis": float(pd.Series(valid).kurtosis()),
        "pct_below_neg3": float(np.mean(valid < -3) * 100),
        "pct_above_pos3": float(np.mean(valid > 3) * 100),
        "pct_below_neg2": float(np.mean(valid < -2) * 100),
        "pct_above_pos2": float(np.mean(valid > 2) * 100),
        "pct_below_neg1": float(np.mean(valid < -1) * 100),
        "pct_above_pos1": float(np.mean(valid > 1) * 100),
    }


def forward_return_analysis(z_scores: np.ndarray, forward_returns: np.ndarray) -> dict:
    """Analyze relationship between Z-score and forward returns."""
    valid = ~(np.isnan(z_scores) | np.isnan(forward_returns))
    z = z_scores[valid]
    fr = forward_returns[valid]

    if len(z) == 0:
        return {}

    # Overall statistics
    correlation = float(np.corrcoef(z, fr)[0, 1]) if len(z) > 1 else 0.0

    # Conditional means by Z-score sign
    long_mask = z < 0
    short_mask = z > 0

    result = {
        "n_observations": int(np.sum(valid)),
        "correlation": correlation,
        "mean_return_all": float(np.mean(fr)),
        "std_return_all": float(np.std(fr)),
    }

    if np.sum(long_mask) > 0:
        result["mean_return_long_zscore"] = float(np.mean(fr[long_mask]))
        result["median_return_long_zscore"] = float(np.median(fr[long_mask]))
        result["hit_rate_long_zscore"] = float(np.mean(fr[long_mask] > 0) * 100)
        result["n_long"] = int(np.sum(long_mask))

    if np.sum(short_mask) > 0:
        result["mean_return_short_zscore"] = float(np.mean(fr[short_mask]))
        result["median_return_short_zscore"] = float(np.median(fr[short_mask]))
        result["hit_rate_short_zscore"] = float(np.mean(fr[short_mask] < 0) * 100)
        result["n_short"] = int(np.sum(short_mask))

    return result


def binned_analysis(z_scores: np.ndarray, forward_returns: np.ndarray) -> list[dict]:
    """Partition Z-scores into bins and analyze forward returns."""
    valid = ~(np.isnan(z_scores) | np.isnan(forward_returns))
    z = z_scores[valid]
    fr = forward_returns[valid]

    bins = [
        ("< -3", z < -3),
        ("-3 to -2", (z >= -3) & (z < -2)),
        ("-2 to -1", (z >= -2) & (z < -1)),
        ("-1 to 0", (z >= -1) & (z < 0)),
        ("0 to 1", (z >= 0) & (z < 1)),
        ("1 to 2", (z >= 1) & (z < 2)),
        ("2 to 3", (z >= 2) & (z < 3)),
        ("> 3", z >= 3),
    ]

    results = []
    for label, mask in bins:
        n = int(np.sum(mask))
        if n == 0:
            results.append({"bin": label, "n": 0, "mean_return": np.nan, "median_return": np.nan,
                           "std_return": np.nan, "hit_rate": np.nan})
            continue

        bin_returns = fr[mask]
        results.append({
            "bin": label,
            "n": n,
            "mean_return": float(np.mean(bin_returns)),
            "median_return": float(np.median(bin_returns)),
            "std_return": float(np.std(bin_returns)),
            "hit_rate": float(np.mean(bin_returns > 0) * 100),
        })

    return results


def regime_analysis(data: ZScoreResearchData, horizon: int = 60) -> dict:
    """Analyze Z-score relationship by regime.

    Args:
        data: Prepared research data
        horizon: Forward-return horizon in bars (must be in data.horizons)
    """
    if horizon not in data.forward_returns:
        return {"error": f"horizon {horizon} not in {data.horizons}"}
    fr = data.forward_returns[horizon]

    results = {}
    for trend in ["near_ema", "weak_trend", "strong_trend"]:
        for vol in ["low_vol", "mid_vol", "high_vol"]:
            mask = np.array([t == trend and v == vol
                           for t, v in zip(data.regime_trend, data.regime_vol, strict=True)])
            valid = mask & ~np.isnan(data.z_scores) & ~np.isnan(fr)

            if np.sum(valid) < 100:
                results[f"{trend}×{vol}"] = {"n": int(np.sum(valid))}
                continue

            z = data.z_scores[valid]
            returns = fr[valid]

            # Split by Z-score sign
            long_mask = z < -1
            short_mask = z > 1

            results[f"{trend}×{vol}"] = {
                "n": int(np.sum(valid)),
                "mean_return_all": float(np.mean(returns)),
                "mean_return_long_zscore": float(np.mean(returns[long_mask])) if np.sum(long_mask) > 0 else np.nan,
                "mean_return_short_zscore": float(np.mean(returns[short_mask])) if np.sum(short_mask) > 0 else np.nan,
                "hit_rate_long": float(np.mean(returns[long_mask] > 0) * 100) if np.sum(long_mask) > 0 else np.nan,
                "hit_rate_short": float(np.mean(returns[short_mask] < 0) * 100) if np.sum(short_mask) > 0 else np.nan,
            }

    return results


def temporal_analysis(data: ZScoreResearchData, horizon: int = 60) -> dict:
    """Analyze Z-score relationship by year.

    Args:
        data: Prepared research data
        horizon: Forward-return horizon in bars (must be in data.horizons)
    """
    if horizon not in data.forward_returns:
        return {"error": f"horizon {horizon} not in {data.horizons}"}
    fr = data.forward_returns[horizon]

    results = {}
    for year in sorted(set(data.years)):
        mask = data.years == year
        valid = mask & ~np.isnan(data.z_scores) & ~np.isnan(fr)

        if np.sum(valid) < 100:
            results[year] = {"n": int(np.sum(valid))}
            continue

        z = data.z_scores[valid]
        returns = fr[valid]

        long_mask = z < -1
        short_mask = z > 1

        results[year] = {
            "n": int(np.sum(valid)),
            "mean_return_all": float(np.mean(returns)),
            "mean_return_long_zscore": float(np.mean(returns[long_mask])) if np.sum(long_mask) > 0 else np.nan,
            "mean_return_short_zscore": float(np.mean(returns[short_mask])) if np.sum(short_mask) > 0 else np.nan,
            "hit_rate_long": float(np.mean(returns[long_mask] > 0) * 100) if np.sum(long_mask) > 0 else np.nan,
            "hit_rate_short": float(np.mean(returns[short_mask] < 0) * 100) if np.sum(short_mask) > 0 else np.nan,
        }

    return results


def cost_sensitivity(z_scores: np.ndarray, forward_returns: np.ndarray,
                    pip: float, pv: float) -> list[dict]:
    """Test how cost assumptions affect expectancy."""
    valid = ~(np.isnan(z_scores) | np.isnan(forward_returns))
    z = z_scores[valid]
    fr = forward_returns[valid]

    # Only look at extreme Z-scores (|z| > 2)
    extreme_mask = np.abs(z) > 2
    if np.sum(extreme_mask) == 0:
        return []

    z_extreme = z[extreme_mask]
    fr_extreme = fr[extreme_mask]

    # Direction: long if z < -2, short if z > 2
    direction = np.where(z_extreme < 0, 1, -1)
    # Return in pips
    return_pips = fr_extreme / pip * direction

    scenarios = []
    for spread in [0.5, 1.0, 1.5, 2.0, 3.0]:
        for commission in [0.0, 3.50, 7.0]:
            for slippage in [0.0, 0.3, 0.5, 1.0]:
                cost_pips = spread + commission / pv + slippage
                net_return = return_pips - cost_pips
                expectancy = float(np.mean(net_return))
                hit_rate = float(np.mean(net_return > 0) * 100)

                scenarios.append({
                    "spread_pips": spread,
                    "commission_per_lot": commission,
                    "slippage_pips": slippage,
                    "cost_pips": cost_pips,
                    "expectancy_pips": expectancy,
                    "hit_rate": hit_rate,
                    "n_trades": int(np.sum(extreme_mask)),
                })

    return scenarios
