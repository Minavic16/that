"""
Shared test fixtures and environment setup for NestQuant tests.
"""

import os

# Must be set before any nestquant imports
os.environ["NESTQUANT_SKIP_LIVE_CHECK"] = "1"
os.environ["NESTQUANT_SKIP_DASHBOARD_CHECK"] = "1"

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv():
    """Generate a realistic 500-bar OHLCV DataFrame for testing."""
    rng = np.random.default_rng(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 1.1000
    returns = rng.normal(0, 0.0005, n)
    close = base + np.cumsum(returns)
    high = close + rng.uniform(0.0001, 0.002, n)
    low = close - rng.uniform(0.0001, 0.002, n)
    open_ = close + rng.uniform(-0.0005, 0.0005, n)
    volume = rng.uniform(100, 1000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def sample_ohlcv_jpy():
    """Generate a realistic JPY-pair OHLCV DataFrame for testing."""
    rng = np.random.default_rng(123)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 150.0
    returns = rng.normal(0, 0.05, n)
    close = base + np.cumsum(returns)
    high = close + rng.uniform(0.05, 0.5, n)
    low = close - rng.uniform(0.05, 0.5, n)
    open_ = close + rng.uniform(-0.1, 0.1, n)
    volume = rng.uniform(100, 1000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def trending_ohlcv():
    """Generate a strong uptrending OHLCV DataFrame."""
    rng = np.random.default_rng(99)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 1.1000
    # Strong uptrend
    trend = np.linspace(0, 0.05, n)
    noise = rng.normal(0, 0.0003, n)
    close = base + trend + np.cumsum(noise)
    high = close + rng.uniform(0.0001, 0.001, n)
    low = close - rng.uniform(0.0001, 0.001, n)
    open_ = close + rng.uniform(-0.0003, 0.0003, n)
    volume = rng.uniform(100, 1000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def ranging_ohlcv():
    """Generate a range-bound OHLCV DataFrame."""
    rng = np.random.default_rng(77)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 1.1000
    # Oscillate around base
    cycle = 0.003 * np.sin(np.linspace(0, 8 * np.pi, n))
    noise = rng.normal(0, 0.0002, n)
    close = base + cycle + np.cumsum(noise) * 0.3
    high = close + rng.uniform(0.0001, 0.0005, n)
    low = close - rng.uniform(0.0001, 0.0005, n)
    open_ = close + rng.uniform(-0.0002, 0.0002, n)
    volume = rng.uniform(100, 1000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
