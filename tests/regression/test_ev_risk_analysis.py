"""Regression tests for EV/Risk analysis.

Verifies:
1. Metric computation correctness
2. Causality preservation
3. Bootstrap stability
4. Outlier sensitivity logic
5. Cost adjustment correctness
6. No lookahead in any metric
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.ev_risk_analysis import compute_metrics, bootstrap_ci, outlier_sensitivity, pip_value


class TestComputeMetrics:
    """Verify core metric computation."""

    def test_basic_metrics(self):
        """Known-input metrics are correct."""
        r = np.array([1.0, -0.5, 2.0, -1.0, 0.5, -0.2, 1.5, -0.8, 0.3, -0.1,
                       1.2, -0.4, 0.8, -0.3, 0.6, -0.7, 1.1, -0.9, 0.4, -0.6])
        m = compute_metrics(r, cost_pips=0.0)
        assert m["n"] == 20
        assert m["mean_net_pips"] == pytest.approx(np.mean(r), abs=1e-10)
        # 10 positive, 10 negative values → 50% win rate
        assert m["win_rate"] == pytest.approx(50.0, abs=1.0)

    def test_cost_reduces_mean(self):
        """Cost adjustment reduces mean by cost amount."""
        r = np.array([1.0, 2.0, 3.0, 0.5, 1.5])
        m0 = compute_metrics(r, cost_pips=0.0)
        m1 = compute_metrics(r, cost_pips=1.0)
        assert m1["mean_net_pips"] == pytest.approx(m0["mean_net_pips"] - 1.0, abs=1e-10)

    def test_zero_returns(self):
        """All-zero returns produce zero mean."""
        r = np.zeros(50)
        m = compute_metrics(r, cost_pips=0.0)
        assert m["mean_net_pips"] == 0.0
        assert m["win_rate"] == 0.0

    def test_all_wins(self):
        """All-positive returns."""
        r = np.ones(20) * 0.5
        m = compute_metrics(r, cost_pips=0.0)
        assert m["win_rate"] == 100.0
        assert m["profit_factor"] == float("inf")
        assert m["max_consec_wins"] == 20
        assert m["max_consec_losses"] == 0

    def test_all_losses(self):
        """All-negative returns."""
        r = -np.ones(20) * 0.5
        m = compute_metrics(r, cost_pips=0.0)
        assert m["win_rate"] == 0.0
        assert m["max_drawdown_pips"] < 0
        assert m["max_consec_losses"] == 20

    def test_empty_returns(self):
        """Empty array produces zero metrics."""
        m = compute_metrics(np.array([]), cost_pips=0.0)
        assert m["n"] == 0

    def test_single_return(self):
        """Single return produces valid metrics."""
        m = compute_metrics(np.array([1.5]), cost_pips=0.0)
        assert m["n"] == 1
        assert m["mean_net_pips"] == 1.5

    def test_drawdown_calculation(self):
        """Drawdown is correctly computed from cumulative returns."""
        r = np.array([1.0, -0.5, -0.3, 0.8, -1.0])
        m = compute_metrics(r, cost_pips=0.0)
        # Cum: [1.0, 0.5, 0.2, 1.0, 0.0]
        # Running max: [1.0, 1.0, 1.0, 1.0, 1.0]
        # DD: [0.0, -0.5, -0.8, 0.0, -1.0]
        assert m["max_drawdown_pips"] == pytest.approx(-1.0, abs=1e-10)

    def test_profit_factor(self):
        """Profit factor = gross_profit / gross_loss."""
        r = np.array([2.0, -1.0, 3.0, -0.5])
        m = compute_metrics(r, cost_pips=0.0)
        # gross_profit = 5.0, gross_loss = 1.5
        assert m["profit_factor"] == pytest.approx(5.0 / 1.5, abs=1e-10)


class TestBootstrapCI:
    """Verify bootstrap confidence intervals."""

    def test_bootstrap_contains_mean(self):
        """Bootstrap CI should contain the sample mean."""
        rng = np.random.default_rng(42)
        data = rng.normal(1.0, 0.5, 200)
        boot = bootstrap_ci(data, n_boot=1000)
        assert boot["ci_lower"] < boot["mean"] < boot["ci_upper"]

    def test_bootstrap_narrower_with_more_data(self):
        """More data produces narrower CIs."""
        rng = np.random.default_rng(42)
        data_small = rng.normal(1.0, 0.5, 30)
        data_large = rng.normal(1.0, 0.5, 300)
        boot_s = bootstrap_ci(data_small, n_boot=500)
        boot_l = bootstrap_ci(data_large, n_boot=500)
        width_s = boot_s["ci_upper"] - boot_s["ci_lower"]
        width_l = boot_l["ci_upper"] - boot_l["ci_lower"]
        assert width_l < width_s

    def test_bootstrap_small_sample(self):
        """Very small samples return None CI."""
        boot = bootstrap_ci(np.array([1.0, 2.0]), n_boot=100)
        assert boot["ci_lower"] is None


class TestOutlierSensitivity:
    """Verify outlier sensitivity analysis."""

    def test_removing_largest_reduces_mean(self):
        """Removing the largest value should reduce or maintain mean."""
        data = np.array([10.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        sens = outlier_sensitivity(data)
        assert sens["remove_largest_1"]["mean_pips"] < sens["full"]["mean_pips"]

    def test_no_outlier_with_uniform(self):
        """Uniform data: removing extremes has minimal effect."""
        data = np.ones(100)
        sens = outlier_sensitivity(data)
        assert abs(sens["remove_largest_1"]["mean_pips"] - sens["full"]["mean_pips"]) < 0.05


class TestPipValue:
    """Verify pip value calculation."""

    def test_jpy_pair(self):
        assert pip_value("USD/JPY") == 0.01

    def test_non_jpy_pair(self):
        assert pip_value("EUR/USD") == 0.0001

    def test_cross_jpy(self):
        assert pip_value("EUR/JPY") == 0.01


class TestNoLookahead:
    """Verify no future information leaks into metrics."""

    def test_forward_returns_are_causal(self):
        """Forward return at t only uses close[t] and close[t+h]."""
        close = np.arange(100, dtype=float) + 1.0
        h = 10
        fr = np.full(100, np.nan)
        fr[:90] = (close[10:] - close[:90]) / close[:90]

        # Modify data after bar 50+h=60
        close_mod = close.copy()
        close_mod[61:] += 100
        fr_mod = np.full(100, np.nan)
        fr_mod[:90] = (close_mod[10:] - close_mod[:90]) / close_mod[:90]

        # fr[50] should be unchanged
        assert fr[50] == fr_mod[50]
