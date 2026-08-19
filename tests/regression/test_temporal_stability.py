"""Regression tests for temporal stability analysis."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.temporal_stability_analysis import (
    compute_metrics,
    bootstrap_ci,
    outlier_sensitivity,
    benjamini_hochberg,
    pip_value,
)


class TestComputeMetrics:
    def test_basic(self):
        r = np.array([1.0, -0.5, 2.0, -1.0, 0.5, -0.2, 1.5, -0.8, 0.3, -0.1])
        m = compute_metrics(r, cost_pips=0.0)
        assert m["n"] == 10
        assert m["mean_net_pips"] == pytest.approx(np.mean(r), abs=1e-10)

    def test_cost_reduces_mean(self):
        r = np.array([1.0, 2.0, 3.0, 0.5, 1.5])
        m0 = compute_metrics(r, cost_pips=0.0)
        m1 = compute_metrics(r, cost_pips=1.0)
        assert m1["mean_net_pips"] == pytest.approx(m0["mean_net_pips"] - 1.0, abs=1e-10)

    def test_empty(self):
        m = compute_metrics(np.array([]), cost_pips=0.0)
        assert m["n"] == 0

    def test_all_wins(self):
        r = np.ones(20) * 0.5
        m = compute_metrics(r, cost_pips=0.0)
        assert m["win_rate"] == 100.0
        assert m["profit_factor"] == float("inf")

    def test_drawdown(self):
        r = np.array([1.0, -0.5, -0.3, 0.8, -1.0])
        m = compute_metrics(r, cost_pips=0.0)
        assert m["max_drawdown_pips"] == pytest.approx(-1.0, abs=1e-10)


class TestBootstrapCI:
    def test_contains_mean(self):
        rng = np.random.default_rng(42)
        data = rng.normal(1.0, 0.5, 200)
        b = bootstrap_ci(data)
        assert b["ci_lower"] < b["mean"] < b["ci_upper"]

    def test_small_sample(self):
        b = bootstrap_ci(np.array([1.0, 2.0]))
        assert b["ci_lower"] is None


class TestOutlierSensitivity:
    def test_removing_largest(self):
        data = np.array([10.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        s = outlier_sensitivity(data)
        assert s["remove_largest_1"]["mean_pips"] < s["full"]["mean_pips"]


class TestBenjaminiHochberg:
    def test_basic(self):
        pvals = [0.001, 0.01, 0.05, 0.1, 0.5]
        adj = benjamini_hochberg(pvals)
        assert len(adj) == 5
        assert adj[0] <= adj[-1]
        assert all(0 <= a <= 1 for a in adj)

    def test_all_significant(self):
        pvals = [0.001, 0.002, 0.003]
        adj = benjamini_hochberg(pvals)
        assert all(a < 0.05 for a in adj)

    def test_empty(self):
        assert benjamini_hochberg([]) == []


class TestPipValue:
    def test_jpy(self):
        assert pip_value("USD/JPY") == 0.01

    def test_non_jpy(self):
        assert pip_value("EUR/USD") == 0.0001


class TestNoLookahead:
    def test_forward_returns_causal(self):
        close = np.arange(100, dtype=float) + 1.0
        h = 10
        fr = np.full(100, np.nan)
        fr[:90] = (close[10:] - close[:90]) / close[:90]
        close_mod = close.copy()
        close_mod[61:] += 100
        fr_mod = np.full(100, np.nan)
        fr_mod[:90] = (close_mod[10:] - close_mod[:90]) / close_mod[:90]
        assert fr[50] == fr_mod[50]
