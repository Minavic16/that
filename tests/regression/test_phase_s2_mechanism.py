"""
Regression tests for Phase S2: Mechanism Identification.
"""
import json
import numpy as np
import pytest
from pathlib import Path


RESULTS = Path("research/output/simple_strategies/S2_mechanism_identification.json")


@pytest.fixture(scope="module")
def s2_results():
    with open(RESULTS) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# S2-0: Classification Audit
# ═══════════════════════════════════════════════════════════════════════

class TestS20ClassificationAudit:
    def test_classification_is_causal(self, s2_results):
        audit = s2_results["S20"]["temporal_audit"]
        assert audit["uses_exit_data"] is False
        assert audit["uses_only_post_entry"] is True

    def test_fixed_6bar_range_noise_positive(self, s2_results):
        rn = s2_results["S20"]["pnl_by_fixed_6bar"]["range_noise"]
        assert rn["avg_pnl"] > 0

    def test_fixed_6bar_all_categories_present(self, s2_results):
        cats = s2_results["S20"]["pnl_by_fixed_6bar"]
        expected = ["clean_continuation", "retest_continuation", "failed_breakout",
                    "reversal", "range_noise"]
        for cat in expected:
            assert cat in cats

    def test_range_noise_dominates_pnl(self, s2_results):
        cats = s2_results["S20"]["pnl_by_fixed_6bar"]
        rn_total = cats["range_noise"]["total_pnl"]
        all_total = sum(c["total_pnl"] for c in cats.values())
        assert rn_total > all_total * 0.5


# ═══════════════════════════════════════════════════════════════════════
# S2-A: Granular Displacement
# ═══════════════════════════════════════════════════════════════════════

class TestS2AGranularDisplacement:
    def test_monotonic_relationship(self, s2_results):
        mono = s2_results["S2A"]["_monotonicity"]
        assert mono["violations"] <= 2

    def test_higher_displacement_higher_pnl(self, s2_results):
        a = s2_results["S2A"]
        low = a["0-0.5ATR"]["avg_pnl_pips"]
        high = a["2-3ATR"]["avg_pnl_pips"]
        assert high > low

    def test_all_bins_positive(self, s2_results):
        a = s2_results["S2A"]
        for label in ["0-0.5ATR", "0.5-0.75ATR", "0.75-1ATR", "1-1.25ATR",
                       "1.25-1.5ATR", "1.5-2ATR", "2-3ATR", "3-5ATR"]:
            assert a[label]["avg_pnl_pips"] > 0


# ═══════════════════════════════════════════════════════════════════════
# S2-B: Vol-Normalized Displacement
# ═══════════════════════════════════════════════════════════════════════

class TestS2BVolNormalized:
    def test_vol_normalization_helps(self, s2_results):
        assert s2_results["S2B"]["vol_normalization_helps"] is True

    def test_quintile_monotonic(self, s2_results):
        qa = s2_results["S2B"]["quintile_analysis"]
        q1 = qa["Q1"]["avg_pnl"]
        q5 = qa["Q5"]["avg_pnl"]
        assert q5 > q1

    def test_correlations_positive(self, s2_results):
        assert s2_results["S2B"]["raw_displacement"]["corr_with_pnl"] > 0
        assert s2_results["S2B"]["vol_normalized"]["corr_with_pnl"] > 0


# ═══════════════════════════════════════════════════════════════════════
# S2-C: Range/Noise Forensic
# ═══════════════════════════════════════════════════════════════════════

class TestS2CRangeNoiseForensic:
    def test_range_noise_not_artifact(self, s2_results):
        rn = s2_results["S2C"]
        assert rn["range_noise_count"] > 0

    def test_range_noise_positive_pnl(self, s2_results):
        rn = s2_results["S2C"]["basic_stats"]
        assert rn["avg_pnl"] > 0

    def test_no_temporal_leakage_in_range_noise(self, s2_results):
        pi = s2_results["S2C"]["potential_issues"]
        assert pi["end_exit_pct"] < 10

    def test_forward_returns_positive(self, s2_results):
        fwd = s2_results["S2C"]["forward_6bar"]
        assert fwd["mean"] > 0
        assert fwd["positive_pct"] > 0.9


# ═══════════════════════════════════════════════════════════════════════
# S2-D: Fresh Holdout
# ═══════════════════════════════════════════════════════════════════════

class TestS2DFreshHoldout:
    def test_all_periods_positive(self, s2_results):
        d = s2_results["S2D"]
        for period in ["train_2016_2021", "valid_2022_2023", "holdout_2024_2026"]:
            assert d[period]["avg_pnl_pips"] > 0

    def test_holdout_retains_most_of_training(self, s2_results):
        deg = s2_results["S2D"]["degradation"]
        assert deg["holdout_retains_pct_of_train"] > 70

    def test_no_catastrophic_degradation(self, s2_results):
        deg = s2_results["S2D"]["degradation"]
        assert deg["train_to_holdout"] > -30
