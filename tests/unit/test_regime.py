"""Unit tests for regime classification."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from zscore.regime import _causal_atr, _causal_ema, classify_regime


class TestCausalEMA:
    def test_ema_starts_at_first_close(self):
        close = np.array([1.0, 1.1, 1.2, 1.3])
        ema = _causal_ema(close, span=3)
        assert ema[0] == 1.0

    def test_ema_is_causal(self):
        np.random.seed(42)
        close = 1.0 + np.cumsum(np.random.randn(100) * 0.01)
        ema = _causal_ema(close, span=20)

        close_mod = close.copy()
        close_mod[50:] += 0.1
        ema_mod = _causal_ema(close_mod, span=20)

        np.testing.assert_array_equal(ema[:50], ema_mod[:50])

    def test_ema_follows_trend(self):
        close = np.linspace(1.0, 2.0, 100)
        ema = _causal_ema(close, span=10)
        assert ema[-1] > ema[0]


class TestCausalATR:
    def test_atr_warmup_nan(self):
        high = np.array([1.1, 1.2, 1.3, 1.4, 1.5])
        low = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
        close = np.array([1.05, 1.15, 1.25, 1.35, 1.45])
        atr = _causal_atr(high, low, close, period=5)
        for i in range(4):
            assert np.isnan(atr[i])

    def test_atr_positive_after_warmup(self):
        np.random.seed(42)
        n = 50
        high = 1.0 + np.abs(np.random.randn(n)) * 0.01 + 0.01
        low = 1.0 - np.abs(np.random.randn(n)) * 0.01
        close = (high + low) / 2
        atr = _causal_atr(high, low, close, period=10)
        for i in range(9, n):
            assert atr[i] > 0


class TestClassifyRegime:
    @pytest.fixture
    def trending_data(self):
        n = 300
        np.random.seed(42)
        timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
        close = np.linspace(1.1000, 1.1200, n) + np.random.randn(n) * 0.00001
        high = close + 0.0001
        low = close - 0.0001
        return timestamps, high, low, close

    @pytest.fixture
    def ranging_data(self):
        n = 300
        np.random.seed(42)
        timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
        close = 1.1000 + np.sin(np.linspace(0, 8 * np.pi, n)) * 0.001 + np.random.randn(n) * 0.00001
        high = close + 0.00005
        low = close - 0.00005
        return timestamps, high, low, close

    def test_output_length(self, trending_data):
        ts, high, low, close = trending_data
        regimes = classify_regime(close, high, low, ts, "T/USD")
        assert len(regimes) == 300

    def test_all_causal(self, trending_data):
        ts, high, low, close = trending_data
        regimes = classify_regime(close, high, low, ts, "T/USD")
        for r in regimes:
            assert r.is_causal

    def test_warmup_unknown_volatility(self, trending_data):
        ts, high, low, close = trending_data
        regimes = classify_regime(close, high, low, ts, "T/USD", atr_period=14, ema_span=200)
        # ATR needs `atr_period` bars before it has data, so first 14 bars should be unknown
        for i in range(14):
            assert regimes[i].volatility == "unknown"

    def test_trending_detected(self, trending_data):
        ts, high, low, close = trending_data
        regimes = classify_regime(
            close, high, low, ts, "T/USD",
            ema_span=20, atr_period=5,
            trend_near_threshold=0.0001,
            trend_strong_threshold=0.001,
        )
        late_trend = [r.trend for r in regimes[250:]]
        assert "strong_trend" in late_trend or "weak_trend" in late_trend

    def test_ranging_near_ema(self, ranging_data):
        ts, high, low, close = ranging_data
        regimes = classify_regime(
            close, high, low, ts, "T/USD",
            ema_span=20, atr_period=5,
            trend_near_threshold=0.01,
        )
        near_count = sum(1 for r in regimes[50:] if r.trend == "near_ema")
        assert near_count > 100

    def test_causality(self, trending_data):
        """Regime at bar t must not change when future bars are modified."""
        ts, high, low, close = trending_data
        test_idx = 250

        regimes_orig = classify_regime(close, high, low, ts, "T/USD", ema_span=20, atr_period=5)

        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.01
        regimes_mod = classify_regime(close_mod, high, low, ts, "T/USD", ema_span=20, atr_period=5)

        assert regimes_orig[test_idx].trend == regimes_mod[test_idx].trend
        assert regimes_orig[test_idx].volatility == regimes_mod[test_idx].volatility
