"""Regression tests for cross-timeframe agreement analysis."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.cross_timeframe_agreement import (
    compute_metrics,
    bootstrap_ci,
    pip_value,
    compute_forward_returns,
)


class TestComputeMetrics:
    def test_basic(self):
        r = np.array([1.0, -0.5, 2.0, -1.0, 0.5, -0.2, 1.5, -0.8, 0.3, -0.1])
        m = compute_metrics(r, cost_pips=0.0)
        assert m["n"] == 10
        assert m["mean_pips"] == pytest.approx(np.mean(r), abs=1e-10)

    def test_cost_reduces_mean(self):
        r = np.array([1.0, 2.0, 3.0, 0.5, 1.5])
        m0 = compute_metrics(r, cost_pips=0.0)
        m1 = compute_metrics(r, cost_pips=1.0)
        assert m1["mean_pips"] == pytest.approx(m0["mean_pips"] - 1.0, abs=1e-10)

    def test_empty(self):
        m = compute_metrics(np.array([]), cost_pips=0.0)
        assert m["n"] == 0

    def test_all_wins(self):
        r = np.ones(20) * 0.5
        m = compute_metrics(r, cost_pips=0.0)
        assert m["win_rate"] == 100.0
        assert m["profit_factor"] == float("inf")


class TestBootstrapCI:
    def test_contains_mean(self):
        rng = np.random.default_rng(42)
        data = rng.normal(1.0, 0.5, 200)
        b = bootstrap_ci(data)
        assert b["ci_lower"] < b["mean"] < b["ci_upper"]

    def test_small_sample(self):
        b = bootstrap_ci(np.array([1.0, 2.0]))
        assert b["ci_lower"] is None


class TestForwardReturns:
    def test_causal(self):
        close = np.arange(100, dtype=float) + 1.0
        h = 10
        fr = compute_forward_returns(close, h)
        expected = (close[10:] - close[:90]) / close[:90]
        np.testing.assert_array_almost_equal(fr[:90], expected)

    def test_nan_at_end(self):
        close = np.ones(50)
        fr = compute_forward_returns(close, 10)
        assert np.all(np.isnan(fr[40:]))
        assert not np.any(np.isnan(fr[:40]))


class TestPipValue:
    def test_jpy(self):
        assert pip_value("USD/JPY") == 0.01

    def test_non_jpy(self):
        assert pip_value("EUR/USD") == 0.0001


class TestNoLookahead:
    def test_forward_returns_invariant(self):
        close = np.arange(100, dtype=float) + 1.0
        h = 10
        fr = np.full(100, np.nan)
        fr[:90] = (close[10:] - close[:90]) / close[:90]
        close_mod = close.copy()
        close_mod[61:] += 100
        fr_mod = np.full(100, np.nan)
        fr_mod[:90] = (close_mod[10:] - close_mod[:90]) / close_mod[:90]
        assert fr[50] == fr_mod[50]
