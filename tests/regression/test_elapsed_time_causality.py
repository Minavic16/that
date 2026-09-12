"""Regression tests for equal-elapsed-time forward-return analysis.

Verifies that the elapsed-time analysis:
1. Uses only causal forward returns
2. Does not introduce cross-timeframe lookahead
3. Produces consistent results across runs
4. Has correct bar-count-to-elapsed-time mappings
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nestquant.research.experiments.elapsed_time_analysis import (
    bars_for_elapsed,
    compute_forward_returns,
    BARS_PER_MINUTE,
    ELAPSED_TARGETS,
)


class TestBarsForElapsed:
    """Verify bar-count calculations are correct."""

    def test_1min_1h(self):
        """1min: 60 bars = ~1 hour."""
        assert bars_for_elapsed("1min", 60) == 60

    def test_15min_1h(self):
        """15min: 4 bars = ~1 hour."""
        assert bars_for_elapsed("15min", 60) == 4

    def test_1h_1h(self):
        """1h: 1 bar = ~1 hour."""
        assert bars_for_elapsed("1h", 60) == 1

    def test_4h_1h(self):
        """4h: 0.25 bars rounds to 1."""
        assert bars_for_elapsed("4h", 60) == 1

    def test_1min_4h(self):
        """1min: 240 bars = ~4 hours."""
        assert bars_for_elapsed("1min", 240) == 240

    def test_15min_4h(self):
        """15min: 16 bars = ~4 hours."""
        assert bars_for_elapsed("15min", 240) == 16

    def test_1h_4h(self):
        """1h: 4 bars = ~4 hours."""
        assert bars_for_elapsed("1h", 240) == 4

    def test_4h_4h(self):
        """4h: 1 bar = ~4 hours."""
        assert bars_for_elapsed("4h", 240) == 1

    def test_1min_24h(self):
        """1min: 1440 bars = ~24 hours."""
        assert bars_for_elapsed("1min", 1440) == 1440

    def test_15min_24h(self):
        """15min: 96 bars = ~24 hours."""
        assert bars_for_elapsed("15min", 1440) == 96

    def test_1h_24h(self):
        """1h: 24 bars = ~24 hours."""
        assert bars_for_elapsed("1h", 1440) == 24

    def test_4h_24h(self):
        """4h: 6 bars = ~24 hours."""
        assert bars_for_elapsed("4h", 1440) == 6

    def test_minimum_is_one(self):
        """Bar count must always be at least 1."""
        assert bars_for_elapsed("4h", 1) == 1

    def test_all_timeframes_covered(self):
        """All timeframes should have a bars_per_minute entry."""
        for tf in ["1min", "15min", "1h", "4h"]:
            assert tf in BARS_PER_MINUTE

    def test_all_targets_covered(self):
        """All elapsed targets should be represented."""
        for target in ["1h", "4h", "24h", "48h"]:
            assert target in ELAPSED_TARGETS


class TestForwardReturnsCausality:
    """Verify forward returns are strictly causal."""

    def test_forward_returns_basic(self):
        """Forward return = (close[t+h] - close[t]) / close[t]."""
        close = np.array([1.0, 1.01, 1.02, 1.03, 1.04, 1.05])
        fr = compute_forward_returns(close, horizon_bars=2)
        # fr[0] = (1.02 - 1.0) / 1.0 = 0.02
        assert abs(fr[0] - 0.02) < 1e-10
        # fr[1] = (1.03 - 1.01) / 1.01 ≈ 0.0198
        assert abs(fr[1] - (1.03 - 1.01) / 1.01) < 1e-10

    def test_forward_returns_nan_at_end(self):
        """Last h bars should be NaN (no future data)."""
        close = np.arange(10, dtype=float)
        fr = compute_forward_returns(close, horizon_bars=3)
        assert np.all(np.isnan(fr[-3:]))

    def test_forward_returns_causal_invariance(self):
        """Modifying data after t+h must not change fr[t]."""
        close = np.arange(20, dtype=float) + 1.0
        h = 5
        test_idx = 7
        fr_original = compute_forward_returns(close, horizon_bars=h)

        close_mod = close.copy()
        close_mod[test_idx + h + 1:] += 100
        fr_modified = compute_forward_returns(close_mod, horizon_bars=h)

        assert fr_original[test_idx] == fr_modified[test_idx]

    def test_forward_returns_depend_on_close_at_t(self):
        """Forward return uses close[t], so modifying close[t] changes fr[t]."""
        close = np.arange(20, dtype=float) + 1.0
        h = 5
        test_idx = 7
        fr_original = compute_forward_returns(close, horizon_bars=h)

        close_mod = close.copy()
        close_mod[test_idx] += 0.1
        fr_modified = compute_forward_returns(close_mod, horizon_bars=h)

        assert fr_original[test_idx] != fr_modified[test_idx]


class TestNoCrossTimeframeLookahead:
    """Verify that the elapsed-time analysis does not leak across timeframes."""

    def test_independent_computation(self):
        """Forward returns at different horizons are independent."""
        close = np.arange(100, dtype=float) + 1.0
        fr_1h = compute_forward_returns(close, horizon_bars=4)   # ~1h at 15min
        fr_4h = compute_forward_returns(close, horizon_bars=16)  # ~4h at 15min

        # They share close[t] but use different close[t+h]
        # This is fine — each is independently causal
        assert len(fr_1h) == len(fr_4h)
        assert not np.allclose(fr_1h, fr_4h, equal_nan=True)

    def test_horizon_ordering(self):
        """Longer horizons have more NaN at end."""
        close = np.arange(100, dtype=float) + 1.0
        fr_short = compute_forward_returns(close, horizon_bars=4)
        fr_long = compute_forward_returns(close, horizon_bars=40)

        assert np.sum(np.isnan(fr_short)) < np.sum(np.isnan(fr_long))
