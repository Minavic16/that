"""
R2.1 Volatility Structure Research — Data Loading and Preparation
=================================================================

Loads 4H OHLCV data from the shadow runner's bars.jsonl.
Provides causal, time-aligned return and volatility construction.

Phase 1: One pair only (EUR/USD).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BARS_FILE = Path("/root/nestquant/logs/shadow_live/bars.jsonl")
DEFAULT_PAIR = "EUR/USD"


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_bars(pair: str = DEFAULT_PAIR, bars_file: Path = BARS_FILE) -> pd.DataFrame:
    """Load 4H bars from JSONL, filter to one pair.

    Returns DataFrame with columns:
        timestamp (UTC), open, high, low, close, volume, spread
    Index: DatetimeIndex (UTC), sorted ascending.
    """
    rows = []
    with open(bars_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("symbol") != pair:
                continue
            rows.append({
                "timestamp": pd.Timestamp(d["timestamp"]).tz_convert("UTC"),
                "open": float(d["open"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "close": float(d["close"]),
                "volume": float(d.get("volume", 0)),
                "spread": float(d.get("spread", 0)),
            })

    if not rows:
        raise ValueError(f"No bars found for pair={pair} in {bars_file}")

    df = pd.DataFrame(rows)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# ---------------------------------------------------------------------------
# Return Construction
# ---------------------------------------------------------------------------

def compute_log_returns(close: pd.Series) -> pd.Series:
    """Compute log-returns from close prices.

    CAUSAL: return_t = log(close_t / close_{t-1}).
    Uses NO future information. Each return uses only the current
    and previous close.
    """
    return np.log(close / close.shift(1))


def compute_simple_returns(close: pd.Series) -> pd.Series:
    """Compute simple percentage returns from close prices.

    CAUSAL: return_t = (close_t - close_{t-1}) / close_{t-1}.
    """
    return close.pct_change()


# ---------------------------------------------------------------------------
# Volatility Target Construction
# ---------------------------------------------------------------------------

def realized_volatility(close: pd.Series, window: int = 1) -> pd.Series:
    """Compute realized volatility as rolling std of log-returns.

    CAUSAL: sigma_t = std(r_{t-window+1}, ..., r_t).
    Uses only past and present returns. No future information.

    For window=1, this is just the absolute return (degenerate).
    For window>1, this is the rolling standard deviation.
    """
    log_ret = compute_log_returns(close)
    return log_ret.rolling(window=window, min_periods=window).std()


def realized_volatility_forward(close: pd.Series, horizon: int) -> pd.Series:
    """Compute forward-looking realized volatility (THE TARGET).

    CAUSAL ALIGNMENT: target_t = realized_vol over [t+1, t+horizon].
    This is what we are trying to forecast.

    IMPORTANT: In the evaluation loop, target_t is only compared to
    forecast_t AFTER the forecast period has elapsed. The target is
    never used as an input to the forecast.
    """
    log_ret = compute_log_returns(close)
    return log_ret.rolling(window=horizon, min_periods=horizon).std().shift(-horizon)


def realized_volatility_parkinson(high: pd.Series, low: pd.Series,
                                   window: int = 1) -> pd.Series:
    """Parkinson (1980) volatility estimator using high/low range.

    More efficient than close-to-close for a single candle.
    CAUSAL: uses only H and L of the current and past candles.
    """
    log_hl_sq = np.log(high / low) ** 2
    return np.sqrt(log_hl_sq.rolling(window=window, min_periods=window).mean() / (4 * np.log(2)))


# ---------------------------------------------------------------------------
# ATR Baseline
# ---------------------------------------------------------------------------

def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    """Compute Average True Range.

    CAUSAL: ATR_t uses only true ranges up to and including time t.
    True range at t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|).
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Baseline Volatility Models
# ---------------------------------------------------------------------------

def baseline_rolling_vol(close: pd.Series, window: int) -> pd.Series:
    """Baseline: Simple rolling standard deviation of log-returns.

    CAUSAL: sigma_hat_t = std(r_{t-window+1}, ..., r_t).
    Forecast for t+1 is sigma_t (persistence model).
    """
    return realized_volatility(close, window=window)


def baseline_ewma_vol(close: pd.Series, span: int) -> pd.Series:
    """Baseline: Exponentially weighted moving average of squared returns.

    CAUSAL: sigma_hat_t^2 = lambda * r_t^2 + (1-lambda) * sigma_hat_{t-1}^2.
    Uses only past information.
    """
    log_ret = compute_log_returns(close)
    return log_ret.ewm(span=span, min_periods=1).std()


def baseline_naive_vol(close: pd.Series) -> pd.Series:
    """Baseline: Yesterday's volatility (persistence model).

    CAUSAL: sigma_hat_{t+1} = sigma_t.
    """
    return realized_volatility(close, window=1).shift(1)


# ---------------------------------------------------------------------------
# Data Validation
# ---------------------------------------------------------------------------

def validate_data(df: pd.DataFrame, pair: str) -> dict:
    """Run integrity checks on loaded data.

    Returns dict of check_name -> (passed, detail).
    """
    checks = {}

    # Timestamp monotonicity
    is_sorted = df.index.is_monotonic_increasing
    checks["timestamps_sorted"] = (is_sorted, "ascending" if is_sorted else "UNSORTED")

    # No duplicate timestamps
    no_dupes = not df.index.duplicated().any()
    checks["no_duplicates"] = (no_dupes, "clean" if no_dupes else f"{df.index.duplicated().sum()} duplicates")

    # OHLC integrity
    h_ge_l = (df["high"] >= df["low"]).all()
    h_ge_o = (df["high"] >= df["open"]).all()
    h_ge_c = (df["high"] >= df["close"]).all()
    l_le_o = (df["low"] <= df["open"]).all()
    l_le_c = (df["low"] <= df["close"]).all()
    ohlc_valid = h_ge_l and h_ge_o and h_ge_c and l_le_o and l_le_c
    checks["ohlc_integrity"] = (ohlc_valid, "valid" if ohlc_valid else "VIOLATION")

    # No missing close prices
    no_nan_close = not df["close"].isna().any()
    checks["no_nan_close"] = (no_nan_close, "clean" if no_nan_close else f"{df['close'].isna().sum()} NaN")

    # Positive prices
    positive = (df["close"] > 0).all()
    checks["positive_prices"] = (positive, "ok" if positive else "NON-POSITIVE FOUND")

    # Timezone-aware (UTC)
    is_utc = df.index.tz is not None and str(df.index.tz) == "UTC"
    checks["utc_timezone"] = (is_utc, str(df.index.tz) if is_utc else "NOT UTC")

    # Bar count
    checks["bar_count"] = (len(df) >= 2, f"{len(df)} bars")

    # Time gaps (warning, not failure — weekends and runner restarts are expected)
    if len(df) > 1:
        gaps = df.index.to_series().diff().dropna()
        expected = pd.Timedelta(hours=4)
        gap_issues = (gaps != expected).sum()
        # Classify gaps: weekend gaps (2-3 days) vs long gaps (>3 days)
        weekend_gaps = ((gaps > pd.Timedelta(hours=44)) & (gaps < pd.Timedelta(hours=76))).sum()
        long_gaps = (gaps >= pd.Timedelta(days=3)).sum()
        checks["regular_spacing"] = (
            long_gaps == 0,  # Only fail on long gaps (>3 days)
            f"{gap_issues} irregular gaps ({weekend_gaps} weekend, {long_gaps} long)"
        )
    else:
        checks["regular_spacing"] = (True, "single bar")

    return checks


# ---------------------------------------------------------------------------
# Synthetic Data Generator (for causality validation)
# ---------------------------------------------------------------------------

def generate_synthetic_ohlcv(n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic 4H OHLCV data with known volatility structure.

    The data has:
    - Log-normal returns
    - GARCH-like volatility clustering (vol of vol > 0)
    - Known parameters for validation

    CAUSALITY VALIDATION: Because we control the data generation,
    we can verify that no model uses future information by checking
    that forecasts at time t are independent of returns after t.
    """
    rng = np.random.default_rng(seed)

    # Generate returns with volatility clustering
    returns = np.zeros(n_bars)
    sigma = np.zeros(n_bars)
    sigma[0] = 0.01  # initial volatility

    for t in range(1, n_bars):
        sigma[t] = np.sqrt(
            0.00001
            + 0.05 * returns[t - 1] ** 2
            + 0.90 * sigma[t - 1] ** 2
        )
        returns[t] = sigma[t] * rng.standard_normal()

    # Construct prices
    close = 1.1000 * np.exp(np.cumsum(returns))

    # Construct OHLC from close
    noise_h = np.abs(rng.normal(0, 0.001, n_bars))
    noise_l = np.abs(rng.normal(0, 0.001, n_bars))
    high = close * (1 + noise_h)
    low = close * (1 - noise_l)
    open_ = np.roll(close, 1)
    open_[0] = 1.1000

    # Timestamps
    start = pd.Timestamp("2026-01-01", tz="UTC")
    timestamps = pd.date_range(start, periods=n_bars, freq="4h")

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(10000, 100000, n_bars),
        "spread": rng.uniform(0.0001, 0.001, n_bars),
    }, index=timestamps)
    df.index.name = "timestamp"

    return df


if __name__ == "__main__":
    # Quick validation
    print("Loading EUR/USD bars...")
    df = load_bars()
    print(f"  Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    print("\nRunning data validation...")
    checks = validate_data(df, "EUR/USD")
    for name, (passed, detail) in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name} — {detail}")

    print("\nGenerating synthetic data...")
    synth = generate_synthetic_ohlcv(200)
    print(f"  Generated {len(synth)} bars")

    print("\nDone.")
