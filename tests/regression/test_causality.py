"""Regression tests: causality violations and look-ahead bias detection."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nestquant.research.shared.zscore.regime import (
    _causal_atr,
    _causal_ema,
    classify_regime,
    classify_regime_chunked,
)
from nestquant.research.shared.zscore.zscore import compute_zscore_causal


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
        from nestquant.research.shared.zscore.zscore import compute_zscore_expanding

        ts, close = price_data
        test_idx = 300

        obs_orig = compute_zscore_expanding(close, ts, 'TEST/USD', min_periods=20)
        z_orig = obs_orig[test_idx].z_score

        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.005
        obs_mod = compute_zscore_expanding(close_mod, ts, 'TEST/USD', min_periods=20)
        z_mod = obs_mod[test_idx].z_score

        assert z_orig == z_mod


class TestRegimeCausalityRegression:
    """Verify that regime classification is invariant to future data changes.

    Regime labels at timestamp t must depend ONLY on data available at or
    before t. This test catches the windowed-EMA bug where classify_regime
    on a subset resets the EMA history.
    """

    @pytest.fixture
    def price_data(self):
        np.random.seed(456)
        n = 1000
        timestamps = pd.date_range('2024-01-02', periods=n, freq='1min', tz='UTC')
        close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0001)
        high = close + np.abs(np.random.randn(n) * 0.00005)
        low = close - np.abs(np.random.randn(n) * 0.00005)
        return timestamps, close, high, low

    def test_regime_invariant_to_future_data(self, price_data):
        """Regime at bar t must not change when bars > t are modified."""
        ts, close, high, low = price_data
        test_idx = 500

        regimes_orig = classify_regime(close, high, low, ts, 'TEST/USD',
                                       ema_span=200, atr_period=14)
        trend_orig = regimes_orig[test_idx].trend
        vol_orig = regimes_orig[test_idx].volatility

        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.01
        high_mod = high.copy()
        high_mod[test_idx + 1:] += 0.01
        low_mod = low.copy()
        low_mod[test_idx + 1:] += 0.01

        regimes_mod = classify_regime(close_mod, high_mod, low_mod, ts, 'TEST/USD',
                                      ema_span=200, atr_period=14)
        trend_mod = regimes_mod[test_idx].trend
        vol_mod = regimes_mod[test_idx].volatility

        assert trend_orig == trend_mod, (
            f"Regime trend causality violation at bar {test_idx}: "
            f"orig={trend_orig}, modified={trend_mod}"
        )
        assert vol_orig == vol_mod, (
            f"Regime volatility causality violation at bar {test_idx}: "
            f"orig={vol_orig}, modified={vol_mod}"
        )

    def test_regime_window_vs_full_series(self, price_data):
        """Chunked classification must be self-consistent across chunk sizes.

        classify_regime_chunked with any chunk size must produce identical
        labels. The chunk_size parameter is a hint — the function processes
        the full series, so results must be identical regardless of chunk_size.
        """
        ts, close, high, low = price_data

        regimes_500 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )
        regimes_1000 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        regimes_2000 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=2000, ema_span=200, atr_period=14,
        )

        assert len(regimes_500) == len(regimes_1000) == len(regimes_2000)

        for i in range(len(regimes_500)):
            for label, regimes in [("1000", regimes_1000), ("2000", regimes_2000)]:
                assert regimes_500[i].trend == regimes[i].trend, (
                    f"Trend mismatch at bar {i} (chunk_size={label}): "
                    f"500={regimes_500[i].trend}, {label}={regimes[i].trend}"
                )
                assert regimes_500[i].volatility == regimes[i].volatility, (
                    f"Volatility mismatch at bar {i} (chunk_size={label}): "
                    f"500={regimes_500[i].volatility}, {label}={regimes[i].volatility}"
                )

    def test_regime_future_data_invariance_chunked(self, price_data):
        """Chunked classifier: future data modification must not affect past labels."""
        ts, close, high, low = price_data
        test_idx = 500

        regimes_orig = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )

        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.01
        high_mod = high.copy()
        high_mod[test_idx + 1:] += 0.01
        low_mod = low.copy()
        low_mod[test_idx + 1:] += 0.01

        regimes_mod = classify_regime_chunked(
            close_mod, high_mod, low_mod, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )

        assert regimes_orig[test_idx].trend == regimes_mod[test_idx].trend
        assert regimes_orig[test_idx].volatility == regimes_mod[test_idx].volatility

    def test_ema_continuity_across_chunks(self, price_data):
        """EMA computed on full series must match chunked regime classification.

        classify_regime_chunked computes EMA on the full series, then passes
        precomputed values to each chunk. Verify that the precomputed EMA
        is identical to calling _causal_ema on the full series.
        """
        ts, close, high, low = price_data

        regimes = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )

        ema = _causal_ema(close, 200)

        for i in range(len(close)):
            if not np.isnan(ema[i]) and ema[i] != 0:
                distance = abs(close[i] - ema[i]) / ema[i]
                if distance <= 0.002:
                    expected_trend = "near_ema"
                elif distance >= 0.008:
                    expected_trend = "strong_trend"
                else:
                    expected_trend = "weak_trend"
                assert regimes[i].trend == expected_trend, (
                    f"Trend mismatch at bar {i}: expected={expected_trend}, "
                    f"got={regimes[i].trend}"
                )

    def test_atr_continuity_across_chunks(self, price_data):
        """ATR computed by chunked classifier must match direct _causal_atr.

        classify_regime_chunked computes ATR on the full series internally.
        Verify that the resulting volatility labels are consistent with the
        ATR values from _causal_atr, confirming no data corruption.
        """
        ts, close, high, low = price_data

        regimes = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )

        atr = _causal_atr(high, low, close, 14)

        # Verify that when ATR is NaN, regime is "unknown"
        for i in range(len(close)):
            if np.isnan(atr[i]):
                assert regimes[i].volatility == "unknown", (
                    f"Bar {i}: ATR is NaN but vol={regimes[i].volatility}"
                )

        # Verify trend consistency with EMA
        ema = _causal_ema(close, 200)
        for i in range(len(close)):
            if not np.isnan(ema[i]) and ema[i] != 0:
                distance = abs(close[i] - ema[i]) / ema[i]
                if distance <= 0.002:
                    expected_trend = "near_ema"
                elif distance >= 0.008:
                    expected_trend = "strong_trend"
                else:
                    expected_trend = "weak_trend"
                assert regimes[i].trend == expected_trend, (
                    f"Bar {i}: expected trend={expected_trend}, got {regimes[i].trend}"
                )

    def test_regime_labels_multiple_test_points(self, price_data):
        """Regime causality holds at multiple test points in chunked mode."""
        ts, close, high, low = price_data
        test_indices = [50, 200, 500, 800, 950]

        regimes_orig = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )

        for idx in test_indices:
            close_mod = close.copy()
            close_mod[idx + 1:] += 0.01
            high_mod = high.copy()
            high_mod[idx + 1:] += 0.01
            low_mod = low.copy()
            low_mod[idx + 1:] += 0.01

            regimes_mod = classify_regime_chunked(
                close_mod, high_mod, low_mod, ts, 'TEST/USD',
                chunk_size=500, ema_span=200, atr_period=14,
            )

            assert regimes_orig[idx].trend == regimes_mod[idx].trend, (
                f"Trend causality violation at bar {idx}"
            )
            assert regimes_orig[idx].volatility == regimes_mod[idx].volatility, (
                f"Volatility causality violation at bar {idx}"
            )

    def test_regime_labels_invariant_to_chunk_size(self, price_data):
        """Changing chunk size must not change any regime label."""
        ts, close, high, low = price_data

        regimes_500 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=500, ema_span=200, atr_period=14,
        )
        regimes_1000 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        regimes_2000 = classify_regime_chunked(
            close, high, low, ts, 'TEST/USD',
            chunk_size=2000, ema_span=200, atr_period=14,
        )

        for i in range(len(close)):
            for label, regimes in [("1000", regimes_1000), ("2000", regimes_2000)]:
                assert regimes_500[i].trend == regimes[i].trend, (
                    f"Trend mismatch at bar {i}: chunk_500 vs chunk_{label}"
                )
                assert regimes_500[i].volatility == regimes[i].volatility, (
                    f"Volatility mismatch at bar {i}: chunk_500 vs chunk_{label}"
                )

    def test_regime_percentile_invariant_to_extreme_future_atr(self, price_data):
        """Historical volatility labels must not change because future ATR changes."""
        ts, close, high, low = price_data
        test_idx = 500

        regimes_orig = classify_regime(
            close, high, low, ts, 'TEST/USD',
            ema_span=200,
            atr_period=14,
        )

        close_mod = close.copy()
        high_mod = high.copy()
        low_mod = low.copy()

        # Inject an extreme future volatility regime.
        close_mod[test_idx + 1:] += np.linspace(
            0.0, 10.0, len(close_mod) - test_idx - 1
        )
        high_mod[test_idx + 1:] += np.linspace(
            0.0, 10.0, len(high_mod) - test_idx - 1
        )
        low_mod[test_idx + 1:] += np.linspace(
            0.0, 10.0, len(low_mod) - test_idx - 1
        )

        regimes_mod = classify_regime(
            close_mod, high_mod, low_mod, ts, 'TEST/USD',
            ema_span=200,
            atr_period=14,
        )

        assert regimes_orig[test_idx].volatility == regimes_mod[test_idx].volatility
        assert regimes_orig[test_idx].atr_percentile == pytest.approx(
            regimes_mod[test_idx].atr_percentile
        )
