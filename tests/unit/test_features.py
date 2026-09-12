"""Unit tests for causal feature calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from nestquant.research.shared.zscore.features import (
    causal_atr,
    causal_ema_distance,
    causal_realized_volatility,
    compute_features,
)


class TestCausalATR:
    def test_warmup_nan(self):
        high = np.arange(10, dtype=float) + 2.0
        low = np.arange(10, dtype=float)
        close = np.arange(10, dtype=float) + 1.0
        atr = causal_atr(high, low, close, period=5)
        for i in range(4):
            assert np.isnan(atr[i])
        assert np.isfinite(atr[4])

    def test_positive(self):
        np.random.seed(42)
        n = 50
        high = 1.0 + np.abs(np.random.randn(n)) * 0.01 + 0.01
        low = 1.0 - np.abs(np.random.randn(n)) * 0.01
        close = (high + low) / 2
        atr = causal_atr(high, low, close, period=10)
        for i in range(9, n):
            assert atr[i] > 0

    def test_causality(self):
        np.random.seed(42)
        n = 50
        high = 1.0 + np.abs(np.random.randn(n)) * 0.01 + 0.01
        low = 1.0 - np.abs(np.random.randn(n)) * 0.01
        close = (high + low) / 2
        test_idx = 40

        atr_orig = causal_atr(high, low, close, period=5)
        high_mod = high.copy()
        high_mod[test_idx + 1:] += 0.05
        atr_mod = causal_atr(high_mod, low, close, period=5)

        assert atr_orig[test_idx] == atr_mod[test_idx]


class TestCausalRealizedVolatility:
    def test_warmup_nan(self):
        close = np.linspace(1.0, 1.1, 30)
        rv = causal_realized_volatility(close, period=20)
        for i in range(20):
            assert np.isnan(rv[i])

    def test_positive(self):
        np.random.seed(42)
        close = 1.0 + np.cumsum(np.random.randn(50) * 0.001)
        rv = causal_realized_volatility(close, period=10)
        for i in range(10, 50):
            assert rv[i] >= 0

    def test_causality(self):
        np.random.seed(42)
        close = 1.0 + np.cumsum(np.random.randn(50) * 0.001)
        test_idx = 30

        rv_orig = causal_realized_volatility(close, period=10)
        close_mod = close.copy()
        close_mod[test_idx + 1:] *= 1.05
        rv_mod = causal_realized_volatility(close_mod, period=10)

        assert rv_orig[test_idx] == rv_mod[test_idx]


class TestCausalEMADistance:
    def test_no_nan_output(self):
        close = np.linspace(1.0, 1.1, 50)
        dist = causal_ema_distance(close, span=20)
        assert not np.any(np.isnan(dist))

    def test_distance_near_zero_when_at_ema(self):
        close = np.full(50, 1.0)
        dist = causal_ema_distance(close, span=20)
        np.testing.assert_allclose(dist, 0.0, atol=1e-10)

    def test_causality(self):
        np.random.seed(42)
        close = 1.0 + np.cumsum(np.random.randn(50) * 0.001)
        test_idx = 30

        dist_orig = causal_ema_distance(close, span=20)
        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.01
        dist_mod = causal_ema_distance(close_mod, span=20)

        assert dist_orig[test_idx] == dist_mod[test_idx]


class TestComputeFeatures:
    def test_output_length(self):
        n = 100
        np.random.seed(42)
        timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
        close = 1.0 + np.cumsum(np.random.randn(n) * 0.001)
        high = close + 0.0005
        low = close - 0.0005
        open_ = close + np.random.randn(n) * 0.0001

        features = compute_features("T/USD", timestamps, open_, high, low, close)
        assert features.n == n

    def test_pair_preserved(self):
        n = 50
        np.random.seed(42)
        timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
        close = 1.0 + np.cumsum(np.random.randn(n) * 0.001)
        high = close + 0.0005
        low = close - 0.0005
        open_ = close

        features = compute_features("EUR/USD", timestamps, open_, high, low, close)
        assert features.pair == "EUR/USD"
