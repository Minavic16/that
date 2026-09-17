"""
R2.1 Deterministic Research Fixture
====================================

Generates synthetic 4H OHLCV data with known volatility structure
for testing the research infrastructure.

This fixture exists ONLY to test machinery. It is NOT research evidence.

Per §N of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# GARCH-like volatility parameters for the synthetic process
DEFAULT_GARCH_PARAMS = {
    "omega": 0.00001,
    "alpha": 0.05,
    "beta": 0.90,
}

# Expected bar-end hours (UTC) for 4H bars
EXPECTED_BAR_HOURS = [0, 4, 8, 12, 16, 20]

# Weekend gap parameters (Friday 20:00 → Sunday 18:00 UTC)
WEEKEND_GAP_MIN_HOURS = 44
WEEKEND_GAP_MAX_HOURS = 76


def generate_synthetic_ohlcv(
    n_bars: int = 200,
    seed: int = 42,
    pair: str = "EUR/USD",
    start_price: float = 1.10000,
    start_date: Optional[datetime] = None,
    include_weekend_gaps: bool = True,
    include_nonweekend_gap: bool = True,
    include_duplicate_timestamp: bool = False,
    include_invalid_prices: bool = False,
    include_invalid_volume: bool = False,
) -> pd.DataFrame:
    """Generate deterministic synthetic 4H OHLCV data.

    The generator produces data with:
    - Known GARCH(1,1)-like volatility process
    - 4H bar-end timestamps (00, 04, 08, 12, 16, 20 UTC)
    - Weekend gaps (Friday 20:00 → Sunday 18:00 UTC)
    - Optional non-weekend gap
    - Optional edge cases for rejection testing

    Args:
        n_bars: Number of valid bars to generate (before edge cases)
        seed: Random seed for reproducibility
        pair: Currency pair name
        start_price: Starting close price
        start_date: Starting datetime (UTC). If None, uses 2026-01-01 04:00 UTC
        include_weekend_gaps: Whether to include weekend gaps in the sequence
        include_nonweekend_gap: Whether to include a non-weekend missing bar
        include_duplicate_timestamp: Whether to add a duplicate timestamp for rejection testing
        include_invalid_prices: Whether to add invalid (non-positive) prices for rejection testing
        include_invalid_volume: Whether to add negative volume for rejection testing

    Returns:
        DataFrame with columns: open, high, low, close, volume, spread
        Index: DatetimeIndex (UTC), bar-end timestamps
    """
    rng = np.random.RandomState(seed)

    if start_date is None:
        start_date = pd.Timestamp("2026-01-01 04:00:00", tz="UTC")

    # Generate GARCH-like returns
    omega, alpha, beta = (
        DEFAULT_GARCH_PARAMS["omega"],
        DEFAULT_GARCH_PARAMS["alpha"],
        DEFAULT_GARCH_PARAMS["beta"],
    )

    returns = np.zeros(n_bars + 12)  # extra for forward targets
    sigma2 = np.zeros(len(returns))
    sigma2[0] = omega / (1 - alpha - beta)  # unconditional variance

    for i in range(1, len(returns)):
        sigma2[i] = omega + alpha * returns[i - 1] ** 2 + beta * sigma2[i - 1]
        returns[i] = np.sqrt(sigma2[i]) * rng.randn()

    # Generate close prices from returns
    closes = np.zeros(n_bars + 12)
    closes[0] = start_price
    for i in range(1, len(closes)):
        closes[i] = closes[i - 1] * np.exp(returns[i])

    # Generate OHLCV from close prices
    timestamps = []
    current_time = start_date

    for i in range(n_bars):
        # Skip weekends if requested
        if include_weekend_gaps:
            # If it's Saturday, skip to Sunday 18:00 UTC
            while current_time.weekday() == 5:  # Saturday
                current_time += timedelta(hours=4)
            # If it's Sunday before 18:00 UTC, skip to 18:00 UTC
            if current_time.weekday() == 6 and current_time.hour < 18:
                current_time = current_time.replace(hour=18, minute=0, second=0, microsecond=0)

        timestamps.append(current_time)
        current_time += timedelta(hours=4)

    # Build the base DataFrame
    data = []
    for i in range(n_bars):
        close = closes[i]
        # Generate OHLV from close
        daily_range = abs(returns[i]) * close * 2
        high = close + abs(rng.randn()) * daily_range * 0.5
        low = close - abs(rng.randn()) * daily_range * 0.5
        open_price = close + (rng.randn() * daily_range * 0.1)

        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        volume = abs(rng.randn()) * 1000 + 500
        spread = abs(rng.randn()) * 0.0002 + 0.0001

        data.append({
            "open": round(open_price, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": round(max(volume, 0), 2),
            "spread": round(max(spread, 0), 5),
        })

    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps, tz="UTC", name="timestamp"))
    df.index.name = "timestamp"

    # Insert a non-weekend gap if requested (remove one bar in the middle)
    if include_nonweekend_gap and n_bars > 20:
        gap_idx = n_bars // 3  # remove bar at 1/3 of the way
        df = pd.concat([
            df.iloc[:gap_idx],
            df.iloc[gap_idx + 1:],
        ])

    # Add duplicate timestamp for rejection testing
    if include_duplicate_timestamp and len(df) > 0:
        dup_row = df.iloc[0:1].copy()
        dup_row.index = [df.index[0]]
        df = pd.concat([dup_row, df])

    # Add invalid prices for rejection testing
    if include_invalid_prices and len(df) > 0:
        invalid_row = df.iloc[0:1].copy()
        invalid_row.loc[:, "close"] = -1.0
        invalid_row.loc[:, "high"] = -1.0
        invalid_row.index = [df.index[0] - timedelta(hours=4)]
        df = pd.concat([invalid_row, df])

    # Add invalid volume for rejection testing
    if include_invalid_volume and len(df) > 0:
        invalid_row = df.iloc[0:1].copy()
        invalid_row.loc[:, "volume"] = -100.0
        invalid_row.index = [df.index[0] - timedelta(hours=8)]
        df = pd.concat([invalid_row, df])

    return df


def generate_clean_fixture(
    n_bars: int = 200,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a clean fixture without edge cases.

    This is the standard fixture for normal testing.
    Includes weekend gaps and one non-weekend gap.
    """
    return generate_synthetic_ohlcv(
        n_bars=n_bars,
        seed=seed,
        include_weekend_gaps=True,
        include_nonweekend_gap=True,
        include_duplicate_timestamp=False,
        include_invalid_prices=False,
        include_invalid_volume=False,
    )


def generate_rejection_fixtures(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Generate fixtures specifically for rejection testing.

    Returns dict of named fixtures with specific edge cases.
    """
    return {
        "duplicate_timestamp": generate_synthetic_ohlcv(
            n_bars=50, seed=seed,
            include_weekend_gaps=False,
            include_nonweekend_gap=False,
            include_duplicate_timestamp=True,
            include_invalid_prices=False,
            include_invalid_volume=False,
        ),
        "invalid_prices": generate_synthetic_ohlcv(
            n_bars=50, seed=seed,
            include_weekend_gaps=False,
            include_nonweekend_gap=False,
            include_duplicate_timestamp=False,
            include_invalid_prices=True,
            include_invalid_volume=False,
        ),
        "invalid_volume": generate_synthetic_ohlcv(
            n_bars=50, seed=seed,
            include_weekend_gaps=False,
            include_nonweekend_gap=False,
            include_duplicate_timestamp=False,
            include_invalid_prices=False,
            include_invalid_volume=True,
        ),
    }

