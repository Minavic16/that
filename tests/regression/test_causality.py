"""Regression tests: causality violations and look-ahead bias detection."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from zscore.zscore import compute_zscore_causal


class TestCausalityRegression:
    """Verify that features at timestamp t are invariant to future data changes."""

    @pytest.fixture
    def price_data(self):
        np.random.seed(123)
        n = 500
        timestamps = pd.date_range('2024-01-02', periods=n, freq='1min', tz='UTC')
        close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0001)
        return timestamps, close

    def test_zscore_invariant_to_future_shift(self, price_data):
        """Z-score at bar t must not change when bars > t are shifted."""
        ts, close = price_data
        test_idx = 300

        obs_orig = compute_zscore_causal(close, ts, 'TEST/USD', lookback=20)
        z_orig = obs_orig[test_idx].z_score

        close_shifted = close.copy()
        close_shifted[test_idx + 1:] += 0.01  # shift future up
        obs_mod = compute_zscore_causal(close_shifted, ts, 'TEST/USD', lookback=20)
        z_mod = obs_mod[test_idx].z_score

        assert z_orig == z_mod

    def test_zscore_invariant_to_future_zeroed(self, price_data):
        """Z-score at bar t must not change when bars > t are zeroed."""
        ts, close = price_data
        test_idx = 250

        obs_orig = compute_zscore_causal(close, ts, 'TEST/USD', lookback=20)
        z_orig = obs_orig[test_idx].z_score

        close_zeroed = close.copy()
        close_zeroed[test_idx + 1:] = 0.0
        obs_mod = compute_zscore_causal(close_zeroed, ts, 'TEST/USD', lookback=20)
        z_mod = obs_mod[test_idx].z_score

        assert z_orig == z_mod

    def test_zscore_invariant_to_future_reversed(self, price_data):
        """Z-score at bar t must not change when bars > t are reversed."""
        ts, close = price_data
        test_idx = 400

        obs_orig = compute_zscore_causal(close, ts, 'TEST/USD', lookback=20)
        z_orig = obs_orig[test_idx].z_score

        close_rev = close.copy()
        close_rev[test_idx + 1:] = close_rev[test_idx + 1:][::-1]
        obs_mod = compute_zscore_causal(close_rev, ts, 'TEST/USD', lookback=20)
        z_mod = obs_mod[test_idx].z_score

        assert z_orig == z_mod

    def test_zscore_multiple_indices(self, price_data):
        """Z-score causality holds at multiple test points."""
        ts, close = price_data
        test_indices = [25, 50, 100, 200, 300, 400, 480]

        for idx in test_indices:
            obs_orig = compute_zscore_causal(close, ts, 'TEST/USD', lookback=20)
            z_orig = obs_orig[idx].z_score

            close_mod = close.copy()
            close_mod[idx + 1:] *= 1.1
            obs_mod = compute_zscore_causal(close_mod, ts, 'TEST/USD', lookback=20)
            z_mod = obs_mod[idx].z_score

            assert z_orig == z_mod, f"Causality violation at bar {idx}"

    def test_expanding_zscore_causality(self, price_data):
        """Expanding-window Z-score is also causal."""
        from zscore.zscore import compute_zscore_expanding

        ts, close = price_data
        test_idx = 300

        obs_orig = compute_zscore_expanding(close, ts, 'TEST/USD', min_periods=20)
        z_orig = obs_orig[test_idx].z_score

        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.005
        obs_mod = compute_zscore_expanding(close_mod, ts, 'TEST/USD', min_periods=20)
        z_mod = obs_mod[test_idx].z_score

        assert z_orig == z_mod
