"""Regression tests for Phase 7 OOS Validation.

Tests verify:
1. Validation results exist and are loadable
2. Walk-forward produces results for all splits
3. Pair holdout produces results for all folds
4. Permutation tests exist for all regions
5. Outlier robustness detects outlier dependence
6. Sample power analysis produces valid statistics
7. Cost adversarial produces break-even estimates
8. Fast vs slow MR classification is consistent
9. Hypothesis classification produces verdicts
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


PHASE7_DIR = Path("research/output/phase7")
REGIONS = [
    "Z3-3.5-Vextreme_vol",
    "Z2.5-3-Vextreme_vol",
    "Z3.5-4-Vextreme_vol",
    "Z4-5-Vhigh_vol",
    "Z5+-Vmid_vol",
    "Z3.5-4-Vlow_vol",
]


@pytest.fixture(scope="module")
def phase7_results():
    with open(PHASE7_DIR / "phase7_validation.json") as f:
        return json.load(f)


class TestWalkForward:
    def test_all_splits_present(self, phase7_results):
        wf = phase7_results["walk_forward"]
        assert len(wf) == 5
        for key in ["2016-2020", "2016-2021", "2016-2022", "2016-2023", "2016-2024"]:
            assert key in wf

    def test_splits_have_region_results(self, phase7_results):
        wf = phase7_results["walk_forward"]
        for label, split in wf.items():
            assert "regions" in split
            for reg in REGIONS:
                assert reg in split["regions"], f"{reg} missing in {label}"

    def test_best_region_positive_in_most_splits(self, phase7_results):
        wf = phase7_results["walk_forward"]
        positive = 0
        for label, split in wf.items():
            r = split["regions"]["Z3-3.5-Vextreme_vol"]
            if r.get("n", 0) > 0:
                if r.get("fwd4", {}).get("mean", 0) > 0:
                    positive += 1
        assert positive >= 3, f"Best region should be positive in >= 3 splits, got {positive}"

    def test_sample_sizes_reasonable(self, phase7_results):
        wf = phase7_results["walk_forward"]
        for label, split in wf.items():
            assert split["n"] > 1000, f"Split {label} has too few events: {split['n']}"


class TestPairHoldout:
    def test_all_folds_present(self, phase7_results):
        ho = phase7_results["pair_holdout"]
        assert len(ho) >= 5
        for i in range(1, 6):
            assert f"fold_{i}" in ho

    def test_aggregate_exists(self, phase7_results):
        ho = phase7_results["pair_holdout"]
        assert "aggregate" in ho

    def test_aggregate_has_all_regions(self, phase7_results):
        agg = phase7_results["pair_holdout"]["aggregate"]
        for reg in REGIONS:
            assert reg in agg, f"{reg} missing from aggregate"

    def test_aggregate_fwd4_positive_for_extreme_vol(self, phase7_results):
        agg = phase7_results["pair_holdout"]["aggregate"]
        for reg in ["Z3-3.5-Vextreme_vol", "Z2.5-3-Vextreme_vol", "Z3.5-4-Vextreme_vol"]:
            fwd = agg[reg]["fwd4"]
            assert fwd["mean"] > 0, f"{reg} aggregate fwd4 should be positive"


class TestRegimeStability:
    def test_all_regions_have_periods(self, phase7_results):
        rs = phase7_results["regime_stability"]
        for reg in REGIONS:
            assert reg in rs
            assert "periods" in rs[reg]
            assert len(rs[reg]["periods"]) == 4

    def test_pct_positive_recorded(self, phase7_results):
        rs = phase7_results["regime_stability"]
        for reg in REGIONS:
            assert "pct_positive" in rs[reg]
            assert 0 <= rs[reg]["pct_positive"] <= 100


class TestCostAdversarial:
    def test_all_regions_have_break_even(self, phase7_results):
        ca = phase7_results["cost_adversarial"]
        for reg in REGIONS:
            assert reg in ca
            assert "break_even" in ca[reg]
            assert ca[reg]["break_even"] >= 0

    def test_extreme_vol_survives_commission(self, phase7_results):
        ca = phase7_results["cost_adversarial"]
        for reg in ["Z3-3.5-Vextreme_vol", "Z3.5-4-Vextreme_vol"]:
            assert ca[reg]["break_even"] > 3.5, \
                f"{reg} should survive $3.50 commission, BE={ca[reg]['break_even']}"


class TestOutlierRobustness:
    def test_all_regions_have_stability_ratio(self, phase7_results):
        or_ = phase7_results["outlier_robustness"]
        for reg in REGIONS:
            assert reg in or_
            assert "stability_ratio" in or_[reg]

    def test_all_regions_outlier_dependent(self, phase7_results):
        """All regions should be outlier-dependent (stability ratio near 0)."""
        or_ = phase7_results["outlier_robustness"]
        for reg in REGIONS:
            assert or_[reg]["outlier_dependent"], \
                f"{reg} should be outlier-dependent"


class TestSamplePower:
    def test_all_regions_have_stats(self, phase7_results):
        sp_ = phase7_results["sample_power"]
        for reg in REGIONS:
            assert reg in sp_
            for field in ["n", "mean", "std", "p_value", "cohens_d"]:
                assert field in sp_[reg]

    def test_extreme_vol_significant_on_ttest(self, phase7_results):
        sp_ = phase7_results["sample_power"]
        for reg in ["Z3-3.5-Vextreme_vol", "Z2.5-3-Vextreme_vol", "Z3.5-4-Vextreme_vol"]:
            assert sp_[reg]["sig_005"], f"{reg} should be significant on t-test"

    def test_cohens_d_small(self, phase7_results):
        sp_ = phase7_results["sample_power"]
        for reg in REGIONS:
            assert abs(sp_[reg]["cohens_d"]) < 0.5, \
                f"{reg} Cohen's d should be small: {sp_[reg]['cohens_d']}"


class TestPermutation:
    def test_all_regions_have_perm_p(self, phase7_results):
        perm = phase7_results["permutation"]
        for reg in REGIONS:
            assert reg in perm
            assert "perm_p" in perm[reg]
            assert "vol_p" in perm[reg]

    def test_no_region_significant(self, phase7_results):
        """No region should pass the permutation test at p<0.05."""
        perm = phase7_results["permutation"]
        for reg in REGIONS:
            assert not perm[reg]["perm_sig"], \
                f"{reg} should NOT be permutation-significant (p={perm[reg]['perm_p']})"

    def test_perm_p_above_010(self, phase7_results):
        perm = phase7_results["permutation"]
        for reg in REGIONS:
            assert perm[reg]["perm_p"] > 0.10, \
                f"{reg} perm p={perm[reg]['perm_p']} should be > 0.10"


class TestFastVsSlow:
    def test_fast_positive_slow_negative(self, phase7_results):
        ov = phase7_results["fast_vs_slow"]["overall"]
        assert ov["fast_f4"]["mean"] > 0
        assert ov["slow_f4"]["mean"] < 0

    def test_mannwhitney_significant(self, phase7_results):
        ov = phase7_results["fast_vs_slow"]["overall"]
        assert ov["mannwhitney_p"] < 0.001

    def test_periods_consistent(self, phase7_results):
        r = phase7_results["fast_vs_slow"]
        for label in ["2016-2018", "2019-2021", "2022-2024", "2025-2026"]:
            assert label in r
            assert r[label]["fast_f4"]["mean"] > r[label]["slow_f4"]["mean"]


class TestHypothesisClassification:
    def test_all_regions_classified(self, phase7_results):
        hc = phase7_results.get("hypothesis_classification", [])
        assert len(hc) == len(REGIONS)

    def test_all_inconclusive(self, phase7_results):
        hc = phase7_results.get("hypothesis_classification", [])
        for h in hc:
            assert h["support"] == "INCONCLUSIVE", \
                f"{h['key']} should be INCONCLUSIVE, got {h['support']}"

    def test_perm_p_in_classification(self, phase7_results):
        hc = phase7_results.get("hypothesis_classification", [])
        for h in hc:
            assert "perm_p" in h
            assert h["perm_p"] > 0.10
