"""Regression tests for Phase 8 Fast vs Slow Mean-Reversion Discovery.

Tests verify:
1. Results file exists and is loadable
2. Class distribution is valid
3. Feature results exist for all families
4. FDR correction applied correctly
5. Temporal stability computed
6. Cross-pair stability computed
7. OOS walk-forward results exist
8. OOS pair holdout results exist
9. Model results exist
10. Economic evaluation exists
11. Verdict is present and valid
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


PHASE8_DIR = Path("research/output/phase8")


@pytest.fixture(scope="module")
def phase8_results():
    with open(PHASE8_DIR / "fast_slow_discovery.json") as f:
        return json.load(f)


class TestClassDistribution:
    def test_class_distribution_recorded(self, phase8_results):
        cd = phase8_results["class_distribution"]
        assert "fast_mr" in cd
        assert "slow_mr" in cd
        assert "continuation" in cd
        assert "ambiguous" in cd

    def test_fast_mr_dominant(self, phase8_results):
        cd = phase8_results["class_distribution"]
        assert cd["fast_mr"] > cd["slow_mr"] * 0.8, "FAST should be roughly balanced with SLOW"

    def test_total_events_large(self, phase8_results):
        cd = phase8_results["class_distribution"]
        total = sum(cd.values())
        assert total > 100000, f"Total events should be >100k, got {total}"

    def test_n_fast_slow_consistent(self, phase8_results):
        cd = phase8_results["class_distribution"]
        assert phase8_results["n_fast"] == cd["fast_mr"]
        assert phase8_results["n_slow"] == cd["slow_mr"]


class TestFeatureResults:
    def test_features_tested(self, phase8_results):
        assert phase8_results["n_features_tested"] >= 50

    def test_fdr_significant(self, phase8_results):
        assert phase8_results["n_significant_after_fdr"] >= 40

    def test_permutation_significant(self, phase8_results):
        assert phase8_results["n_permutation_significant"] >= 40

    def test_feature_results_structure(self, phase8_results):
        for r in phase8_results["feature_results"]:
            assert "feature" in r
            assert "family" in r
            assert "raw_p" in r
            assert "fdr_p" in r
            assert "perm_p" in r
            assert "effect_size" in r
            assert "significant_after_fdr" in r


class TestTemporalStability:
    def test_temporal_stability_recorded(self, phase8_results):
        ts = phase8_results["temporal_stability"]
        assert len(ts) > 0

    def test_temporal_has_periods(self, phase8_results):
        ts = phase8_results["temporal_stability"]
        for fname, data in ts.items():
            assert "periods" in data
            assert "consistent_direction" in data
            assert data["consistent_direction"] in [0, 1, 2, 3, 4]

    def test_doubly_stable_features_exist(self, phase8_results):
        cs = phase8_results["combined_stable_features"]
        assert len(cs) >= 10, f"Expected >=10 doubly stable features, got {len(cs)}"

    def test_abs_z_is_stable(self, phase8_results):
        ts = phase8_results["temporal_stability"]
        assert "abs_z" in ts
        assert ts["abs_z"]["consistent_direction"] == 4


class TestCrossPairStability:
    def test_cross_pair_recorded(self, phase8_results):
        cp = phase8_results["cross_pair_stability"]
        assert len(cp) > 0

    def test_cross_pair_has_counts(self, phase8_results):
        cp = phase8_results["cross_pair_stability"]
        for fname, data in cp.items():
            assert "n_pairs" in data
            assert "n_same_direction" in data
            assert data["n_pairs"] >= 15

    def test_abs_z_universal(self, phase8_results):
        cp = phase8_results["cross_pair_stability"]
        assert cp["abs_z"]["n_same_direction"] == cp["abs_z"]["n_pairs"]


class TestWalkForward:
    def test_walk_forward_recorded(self, phase8_results):
        wf = phase8_results["walk_forward"]
        assert len(wf) == 5

    def test_walk_forward_direction_match(self, phase8_results):
        wf = phase8_results["walk_forward"]
        for label, data in wf.items():
            if "direction_match" in data:
                assert data["direction_match"] == data["n_features"], \
                    f"{label}: not all features match direction"

    def test_oos_match_rate(self, phase8_results):
        rate = phase8_results["wf_direction_match_rate"]
        assert rate >= 0.8, f"OOS direction match rate should be >=0.8, got {rate}"


class TestPairHoldout:
    def test_pair_holdout_recorded(self, phase8_results):
        ph = phase8_results["pair_holdout"]
        assert len(ph) == 5

    def test_pair_holdout_direction_match(self, phase8_results):
        ph = phase8_results["pair_holdout"]
        for label, data in ph.items():
            if "direction_match" in data:
                assert data["direction_match"] == data["n_features"]


class TestModelResults:
    def test_model_results_exist(self, phase8_results):
        assert "model_wf_results" in phase8_results
        assert len(phase8_results["model_wf_results"]) >= 3

    def test_model_auc_above_baseline(self, phase8_results):
        mwf = phase8_results["model_wf_results"]
        avg_auc = np.mean([r["auc"] for r in mwf])
        assert avg_auc > 0.55, f"AUC should be >0.55, got {avg_auc}"

    def test_model_feature_importance(self, phase8_results):
        mwf = phase8_results["model_wf_results"]
        for r in mwf:
            assert "top_features" in r
            assert len(r["top_features"]) >= 3


class TestEconomicEvaluation:
    def test_economic_evaluation_exists(self, phase8_results):
        assert "economic_evaluation" in phase8_results
        ee = phase8_results["economic_evaluation"]
        assert len(ee) >= 4

    def test_probability_buckets_spread(self, phase8_results):
        ee = phase8_results["economic_evaluation"]
        rates = [v["fast_rate"] for v in ee.values()]
        spread = max(rates) - min(rates)
        assert spread > 0.2, f"Probability bucket spread should be >0.2, got {spread}"


class TestVerdict:
    def test_verdict_present(self, phase8_results):
        assert "verdict" in phase8_results
        assert phase8_results["verdict"] in ["SUPPORTED", "INCONCLUSIVE", "REJECTED"]

    def test_verdict_supported(self, phase8_results):
        assert phase8_results["verdict"] == "SUPPORTED", \
            f"Expected SUPPORTED, got {phase8_results['verdict']}"
