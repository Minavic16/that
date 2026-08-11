"""Unit tests for Z-score calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from zscore.zscore import compute_zscore_causal, compute_zscore_expanding, zscore_to_array


class TestComputeZScoreCausal:
    """Tests for causal rolling-window Z-score."""

    @pytest.fixture
    def simple_prices(self):
        """Known price sequence for deterministic testing."""
        timestamps = pd.date_range('2024-01-02', periods=30, freq='1min', tz='UTC')
        close = np.array([1.0 + i * 0.01 for i in range(30)])
        return timestamps, close

    def test_warmup_returns_nan(self, simple_prices):
        """First lookback bars should have NaN Z-score."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=10)
        for i in range(10):
            assert np.isnan(obs[i].z_score)

    def test_post_warmup_is_finite(self, simple_prices):
        """Bars after warmup should have finite Z-score."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=10)
        for i in range(10, 30):
            assert np.isfinite(obs[i].z_score)

    def test_monotonic_prices_high_zscore(self, simple_prices):
        """Monotonically increasing prices should produce high positive Z-score."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=10)
        # At the end, current price is well above rolling mean
        assert obs[-1].z_score > 1.0

    def test_is_causal_flag(self, simple_prices):
        """All observations should be marked causal."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=10)
        for o in obs:
            assert o.is_causal

    def test_rolling_mean_matches(self, simple_prices):
        """Rolling mean should match manual calculation."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=5)
        for i in range(5, 30):
            expected_mean = np.mean(close[i-5:i])
            assert abs(obs[i].rolling_mean - expected_mean) < 1e-10

    def test_output_length_matches_input(self, simple_prices):
        """Output length should match input length."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'T/USD', lookback=10)
        assert len(obs) == 30

    def test_pair_name_preserved(self, simple_prices):
        """Pair name should be preserved in observations."""
        ts, close = simple_prices
        obs = compute_zscore_causal(close, ts, 'EUR/USD', lookback=10)
        assert obs[0].pair == 'EUR/USD'


class TestComputeZScoreExpanding:
    """Tests for causal expanding-window Z-score."""

    def test_expanding_warmup(self):
        """First min_periods bars should have NaN."""
        timestamps = pd.date_range('2024-01-02', periods=50, freq='1min', tz='UTC')
        close = np.random.RandomState(42).randn(50) + 1.0
        obs = compute_zscore_expanding(close, timestamps, 'T/USD', min_periods=20)
        for i in range(20):
            assert np.isnan(obs[i].z_score)

    def test_expanding_post_warmup(self):
        """Bars after min_periods should have finite Z-score."""
        timestamps = pd.date_range('2024-01-02', periods=50, freq='1min', tz='UTC')
        close = np.random.RandomState(42).randn(50) + 1.0
        obs = compute_zscore_expanding(close, timestamps, 'T/USD', min_periods=20)
        for i in range(20, 50):
            assert np.isfinite(obs[i].z_score)


class TestZScoreToArray:
    """Tests for array conversion."""

    def test_conversion(self):
        timestamps = pd.date_range('2024-01-02', periods=5, freq='1min', tz='UTC')
        close = np.array([1.0, 1.1, 1.0, 0.9, 1.0])
        obs = compute_zscore_causal(close, timestamps, 'T/USD', lookback=3)
        arr = zscore_to_array(obs)
        assert arr.shape == (5,)
        assert np.isnan(arr[0])
        assert np.isnan(arr[1])
        assert np.isnan(arr[2])
