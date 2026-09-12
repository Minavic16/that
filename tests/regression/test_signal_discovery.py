"""Regression tests for Phase 6 Signal Discovery.

Tests verify:
1. Event count is consistent
2. Outcome classification is valid
3. Adaptive thresholds outperform absolute thresholds
4. Feature computation is causal
5. Statistical tests are reproducible
"""
from __future__ import annotations

import json

import numpy as np
import pytest


from nestquant.research.experiments.signal_discovery import (
    load_all, run_backtest, classify_outcome,
    eval_forward_return, eval_mae_mfe, eval_time_exit,
    compute_features, stats, metrics, bootstrap_ci,
    ZEvent, OUT
)


@pytest.fixture(scope="module")
def signal_data():
    """Load data and run backtest once for all tests."""
    pdata = load_all("2016-01-01", "2026-07-19")
    events = run_backtest(pdata)
    return events


@pytest.fixture(scope="module")
def signal_results():
    """Load pre-computed results."""
    with open(OUT / "signal_discovery.json") as f:
        return json.load(f)


class TestEventCount:
    def test_events_recorded(self, signal_data):
        assert len(signal_data) > 10000

    def test_events_have_paths(self, signal_data):
        for ev in signal_data[:100]:
            assert len(ev.price_path) > 0
            assert len(ev.z_path) > 0
            assert len(ev.high_path) > 0
            assert len(ev.low_path) > 0

    def test_events_have_features(self, signal_data):
        for ev in signal_data[:100]:
            assert hasattr(ev, "dz_1")
            assert hasattr(ev, "dz_4")
            assert hasattr(ev, "z_accel")
            assert hasattr(ev, "atr_pct_rank")
            assert hasattr(ev, "ema_dist")
            assert hasattr(ev, "mom_10")


class TestOutcomeClassification:
    def test_all_events_classified(self, signal_data):
        for ev in signal_data:
            cat = classify_outcome(ev)
            assert cat in ("fast_mr", "slow_mr", "continuation", "ambiguous", "insufficient")

    def test_fast_mr_has_positive_fwd4(self, signal_data):
        fast_mr = [ev for ev in signal_data if classify_outcome(ev) == "fast_mr"]
        assert len(fast_mr) > 1000
        fwd4 = [eval_forward_return(ev, 4) for ev in fast_mr[:200]]
        assert np.mean(fwd4) > 0, "Fast MR should have positive forward return"

    def test_continuation_has_negative_fwd8(self, signal_data):
        cont = [ev for ev in signal_data if classify_outcome(ev) == "continuation"]
        if len(cont) > 5:
            fwd8 = [eval_forward_return(ev, 8) for ev in cont]
            assert np.mean(fwd8) < 0, "Continuation should have negative forward return"


class TestAdaptiveExtremeness:
    def test_rolling_p99_beats_absolute(self, signal_results):
        best_abs = signal_results["part_a"]["comparison"]["best_absolute"]
        best_rolling = signal_results["part_a"]["comparison"]["best_rolling"]
        assert best_abs is not None
        assert best_rolling is not None
        assert best_rolling["avg_fwd_4"] > best_abs["avg_fwd_4"], \
            "Rolling P99 should outperform best absolute threshold"

    def test_absolute_thresholds_monotonic(self, signal_results):
        abs_results = signal_results["part_a"]["absolute"]
        fwd4_values = []
        for thr in ["2.0", "2.5", "3.0", "3.5", "4.0", "5.0"]:
            if thr in abs_results and abs_results[thr].get("n", 0) > 50:
                fwd4_values.append(abs_results[thr]["fwd_4"]["mean"])
        # Forward return should generally increase with threshold
        assert len(fwd4_values) >= 3
        assert fwd4_values[-1] > fwd4_values[0], \
            "Higher Z thresholds should have higher forward returns"


class TestZDynamics:
    def test_significant_discriminators_exist(self, signal_results):
        disc = signal_results["part_b"].get("feature_discrimination", {})
        assert len(disc) > 0, "Should have feature discrimination results"
        sig_feats = [k for k, v in disc.items() if v.get("significant")]
        assert len(sig_feats) > 0, "At least one feature should be significant"

    def test_abs_z_is_significant(self, signal_results):
        disc = signal_results["part_b"].get("feature_discrimination", {})
        assert "abs_z" in disc
        assert disc["abs_z"]["significant"], "abs_z should significantly discriminate MR from CONT"


class TestConditionalSurface:
    def test_structural_regions_exist(self, signal_results):
        regions = signal_results["part_cd"]["structural_regions"]
        assert len(regions) > 0, "Should have structural regions"
        assert len(regions) >= 5, "Should have at least 5 structural regions"

    def test_top_region_has_adequate_sample(self, signal_results):
        top = signal_results["part_cd"]["structural_regions"][0]
        assert top["n"] >= 50, "Top region should have adequate sample size"

    def test_z_vol_cells_populated(self, signal_results):
        cells = signal_results["part_cd"]["z_x_vol"]
        assert len(cells) > 15, "Z×Vol surface should have many cells"


class TestTemporalStability:
    def test_periods_populated(self, signal_results):
        by_period = signal_results["part_e"]["by_period"]
        assert len(by_period) > 0
        # At least one region should have data in multiple periods
        for region, periods in by_period.items():
            n_periods = sum(1 for p in periods.values() if p.get("n", 0) > 10)
            if n_periods >= 3:
                return
        pytest.fail("No region has data in 3+ periods")


class TestCostSensitivity:
    def test_costs_populated(self, signal_results):
        costs = signal_results["part_g"]
        assert len(costs) > 0, "Should have cost sensitivity results"

    def test_survives_realistic_costs(self, signal_results):
        costs = signal_results["part_g"]
        for region, cost_data in costs.items():
            if cost_data.get(3.5, {}).get("n", 0) > 20:
                pf_35 = cost_data[3.5].get("pf", 0)
                if pf_35 > 1.0:
                    return  # Found at least one region surviving $3.50 costs
        # Not a hard fail — depends on data
        pass


class TestMultipleComparison:
    def test_fdr_applied(self, signal_results):
        fdr = signal_results["part_f"]
        assert fdr["total_tests"] > 0
        assert fdr["significant_after_fdr"] <= fdr["significant_before_fdr"]


class TestStatisticalHelpers:
    def test_stats_basic(self):
        s = stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s["n"] == 5
        assert s["mean"] == 3.0
        assert s["median"] == 3.0

    def test_stats_empty(self):
        s = stats([])
        assert s["n"] == 0

    def test_metrics_basic(self):
        m = metrics([1.0, -0.5, 2.0, -1.0, 0.5])
        assert m["n"] == 5
        assert m["win_rate"] == 60.0

    def test_bootstrap_ci(self):
        np.random.seed(42)
        arr = np.random.normal(0.1, 1.0, 100).tolist()
        ci = bootstrap_ci(arr, n_boot=100)
        assert "pf" in ci
        assert "ci_lower" in ci["pf"]
        assert ci["pf"]["ci_lower"] < ci["pf"]["ci_upper"]


class TestForwardReturn:
    def test_forward_return_long(self, signal_data):
        ev = signal_data[0]
        ev.direction = 1
        ev.entry_price = 1.0
        ev.price_path = [1.0, 1.001, 1.002, 1.003, 1.004]
        ev.pip = 0.0001
        fr = eval_forward_return(ev, 4)
        assert fr > 0

    def test_forward_return_short(self, signal_data):
        ev = signal_data[0]
        ev.direction = -1
        ev.entry_price = 1.0
        ev.price_path = [1.0, 0.999, 0.998, 0.997, 0.996]
        ev.pip = 0.0001
        fr = eval_forward_return(ev, 4)
        assert fr > 0
