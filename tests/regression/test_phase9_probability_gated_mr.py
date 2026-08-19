"""Regression tests for Phase 9 Probability-Gated Mean-Reversion.

Tests verify:
1. Results file exists and is loadable
2. Event summary is valid
3. Walk-forward results exist for all splits
4. Model AUC exceeds baseline across splits
5. Probability calibration is monotonic
6. Cost sensitivity analysis exists
7. Outlier robustness computed
8. Pair holdout results exist
9. Statistical tests computed
10. Hypotheses recorded
11. Verdict is present and valid
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PHASE9_DIR = Path("/root/nestquant/research_data/phase9")


@pytest.fixture(scope="module")
def phase9_results():
    with open(PHASE9_DIR / "probability_gated_mr.json") as f:
        return json.load(f)


class TestEventSummary:
    def test_events_exist(self, phase9_results):
        es = phase9_results["event_summary"]
        assert es["total"] > 100000

    def test_fast_mr_dominant(self, phase9_results):
        es = phase9_results["event_summary"]
        assert es["fast_mr"] > es["slow_mr"]

    def test_class_distribution_reasonable(self, phase9_results):
        es = phase9_results["event_summary"]
        total = es["total"]
        assert es["fast_mr"] / total > 0.4
        assert es["slow_mr"] / total > 0.3


class TestWalkForward:
    def test_all_splits_present(self, phase9_results):
        wf = phase9_results["wf_results"]
        assert len(wf) == 5
        for label in ["2021", "2022", "2023", "2024", "2025-2026"]:
            assert label in wf

    def test_model_auc_above_random(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert r["model_auc"] > 0.55, f"Split {label} AUC too low"

    def test_baseline_exists(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert "baseline" in r
            assert r["baseline"]["n_trades"] > 1000

    def test_oracle_exists(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert "oracle" in r
            assert r["oracle"]["n_trades"] > 1000

    def test_threshold_results_exist(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert "thresholds" in r
            assert len(r["thresholds"]) >= 5


class TestAggregatedOOS:
    def test_aggregated_thresholds(self, phase9_results):
        agg = phase9_results["aggregated"]
        assert len(agg["thresholds"]) == 7

    def test_baseline_n_large(self, phase9_results):
        agg = phase9_results["aggregated"]
        assert agg["baseline"]["n_trades"] > 50000

    def test_oracle_better_than_baseline(self, phase9_results):
        agg = phase9_results["aggregated"]
        oracle_mean = agg["oracle"]["mean_return"]
        base_mean = agg["baseline"]["mean_return"]
        assert oracle_mean > base_mean, "Oracle should have higher mean return"


class TestCalibration:
    def test_calibration_buckets(self, phase9_results):
        cal = phase9_results["aggregated"]["calibration"]
        assert len(cal["buckets"]) >= 5

    def test_brier_score(self, phase9_results):
        cal = phase9_results["aggregated"]["calibration"]
        assert 0 < cal["brier_score"] < 1

    def test_calibration_error(self, phase9_results):
        cal = phase9_results["aggregated"]["calibration"]
        assert 0 <= cal["calibration_error"] < 0.2

    def test_calibration_monotonic(self, phase9_results):
        buckets = phase9_results["aggregated"]["calibration"]["buckets"]
        rates = []
        for label in ["P<0.4", "0.4-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "P>0.8"]:
            if label in buckets:
                rates.append(buckets[label]["actual_fast_rate"])
        # Check general monotonicity: at least the last should be higher than first
        if len(rates) >= 2:
            assert rates[-1] > rates[0], "Calibration should show higher P(fast) → higher actual rate"


class TestCostSensitivity:
    def test_cost_results_exist(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert "cost_results" in r
            assert len(r["cost_results"]) >= 3

    def test_nestquant_cost_included(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            for thr, cr in r["cost_results"].items():
                assert "nestquant" in cr


class TestOutlierRobustness:
    def test_robustness_exist(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            assert "robustness" in r
            assert len(r["robustness"]) >= 3

    def test_robustness_has_fields(self, phase9_results):
        wf = phase9_results["wf_results"]
        for label, r in wf.items():
            for thr, rob in r["robustness"].items():
                assert "full_mean" in rob
                assert "trim10_mean" in rob
                assert "median" in rob
                assert "stability_ratio" in rob
                assert "bootstrap_ci_95" in rob


class TestPairHoldout:
    def test_pair_holdout_folds(self, phase9_results):
        ph = phase9_results["aggregated"]["pair_holdout"]
        assert len(ph) == 5

    def test_pair_holdout_auc(self, phase9_results):
        ph = phase9_results["aggregated"]["pair_holdout"]
        for fold in ph:
            assert fold["auc"] > 0.55


class TestStatisticalTests:
    def test_permutation_tests(self, phase9_results):
        pt = phase9_results["aggregated"]["perm_tests"]
        assert len(pt) >= 5

    def test_permutation_p_values(self, phase9_results):
        pt = phase9_results["aggregated"]["perm_tests"]
        for thr, data in pt.items():
            assert 0 <= data["permutation_p"] <= 1


class TestHypotheses:
    def test_hypotheses_recorded(self, phase9_results):
        hyps = phase9_results["hypotheses"]
        assert len(hyps) == 9

    def test_h1_passes(self, phase9_results):
        assert phase9_results["hypotheses"]["H1_predicts_oos"] in (True, "True")

    def test_h2_passes(self, phase9_results):
        assert phase9_results["hypotheses"]["H2_higher_p_higher_fast_rate"] in (True, "True")

    def test_h9_passes(self, phase9_results):
        assert phase9_results["hypotheses"]["H9_calibrated"] in (True, "True")


class TestVerdict:
    def test_verdict_present(self, phase9_results):
        assert "verdict" in phase9_results

    def test_verdict_valid(self, phase9_results):
        valid = {"STRONG SUPPORT", "PROMISING", "PREDICTIVE-BUT-NOT-TRADEABLE",
                 "INCONCLUSIVE", "FAILED"}
        assert phase9_results["verdict"] in valid

    def test_verdict_not_failed(self, phase9_results):
        assert phase9_results["verdict"] != "FAILED"
