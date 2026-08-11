"""Shared test fixtures and environment setup for NestQuant tests."""
from __future__ import annotations

import os

os.environ["NESTQUANT_SKIP_LIVE_CHECK"] = "1"
os.environ["NESTQUANT_SKIP_DASHBOARD_CHECK"] = "1"

import numpy as np
import pandas as pd
import pytest

from zscore.contracts import InstrumentMetadata, MarketData


# --- Pre-existing fixtures (used by tests/test_engines.py, test_indicators.py, test_signals.py) ---

@pytest.fixture
def sample_ohlcv():
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
    rng = np.random.default_rng(99)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 1.1000
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
    rng = np.random.default_rng(77)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = 1.1000
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


# --- Z-Score Research Engine fixtures ---

@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    """Generate 500-bar synthetic OHLCV with trend then range."""
    n = 500
    np.random.seed(42)
    timestamps = pd.date_range("2024-01-02 00:00", periods=n, freq="1min", tz="UTC")
    trend = np.concatenate([
        np.linspace(1.1000, 1.1100, 200),
        np.full(300, 1.1100),
    ])
    noise = np.cumsum(np.random.randn(n) * 0.00003)
    close = trend + noise
    spread = np.abs(np.random.randn(n) * 0.00005)
    high = close + spread
    low = close - spread
    open_ = close + np.random.randn(n) * 0.00002
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=timestamps,
    )


@pytest.fixture
def synthetic_market_data(synthetic_ohlcv: pd.DataFrame) -> MarketData:
    df = synthetic_ohlcv
    return MarketData(
        pair="TEST/USD",
        timestamps=df.index,
        open=df["open"].values,
        high=df["high"].values,
        low=df["low"].values,
        close=df["close"].values,
    )


@pytest.fixture
def synthetic_daily(synthetic_ohlcv: pd.DataFrame) -> pd.DataFrame:
    return synthetic_ohlcv.resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna()


@pytest.fixture
def test_metadata() -> InstrumentMetadata:
    return InstrumentMetadata(
        pair="TEST/USD",
        pip_size=0.0001,
        pip_value_per_lot=10.0,
        typical_spread_pips=1.0,
        contract_size=100_000,
    )
