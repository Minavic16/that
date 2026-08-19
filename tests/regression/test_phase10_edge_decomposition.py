"""Regression tests for Phase 10 Economic Edge Decomposition."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PHASE10_DIR = Path("/root/nestquant/research_data/phase10")


@pytest.fixture(scope="module")
def phase10_results():
    with open(PHASE10_DIR / "phase10_economic_edge_results.json") as f:
        return json.load(f)


class TestImplementationAudit:
    def test_pip_value_correct(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["pip_value_eurusd"] == 10.0
        assert abs(ia["pip_value_usdjpy"] - 6.70) < 0.01

    def test_returns_in_pips(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["forward_returns_in_pips"] is True

    def test_status_corrected(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["status"] == "CORRECTED"


class TestEdgeDistribution:
    def test_outcome_classes(self, phase10_results):
        ed = phase10_results["edge_distribution"]
        assert "outcome_fast_mr" in ed
        assert "outcome_slow_mr" in ed

    def test_fast_mr_positive(self, phase10_results):
        ed = phase10_results["edge_distribution"]
        assert ed["outcome_fast_mr"]["mean"] > 0

    def test_prediction_correctness(self, phase10_results):
        ed = phase10_results["edge_distribution"]
        assert "pred_correct" in ed
        assert "pred_incorrect" in ed
        assert ed["pred_correct"]["mean"] > ed["pred_incorrect"]["mean"]


class TestEdgeConcentration:
    def test_top3_concentration(self, phase10_results):
        ec = phase10_results["edge_concentration"]
        assert "top3_contribution_pct" in ec
        assert ec["top3_contribution_pct"] > 0

    def test_year_data(self, phase10_results):
        ec = phase10_results["edge_concentration"]
        assert len(ec["by_year"]) >= 4


class TestCostBreakpoint:
    def test_overall_break_even(self, phase10_results):
        cb = phase10_results["cost_breakpoint"]["overall"]
        assert cb["median"] > 0
        assert cb["mean"] > 0
        assert cb["min"] <= cb["median"] <= cb["max"]


class TestExpectancyDecomposition:
    def test_decomposition_exists(self, phase10_results):
        ed = phase10_results["expectancy_decomposition"]
        assert "p_win" in ed
        assert "avg_win" in ed
        assert "expectancy" in ed

    def test_win_loss_balance(self, phase10_results):
        ed = phase10_results["expectancy_decomposition"]
        assert 0.4 < ed["p_win"] < 0.6  # Win rate should be near 50%


class TestSignalMonotonicity:
    def test_ten_deciles(self, phase10_results):
        sm = phase10_results["signal_monotonicity"]
        assert len(sm) == 10

    def test_actual_rate_increases(self, phase10_results):
        sm = phase10_results["signal_monotonicity"]
        rates = [d["actual_fast_rate"] for d in sm]
        assert rates[-1] > rates[0]


class TestCrossPairHeterogeneity:
    def test_all_pairs_present(self, phase10_results):
        cp = phase10_results["cross_pair_heterogeneity"]
        assert len(cp) >= 15

    def test_has_positive_pairs(self, phase10_results):
        cp = phase10_results["cross_pair_heterogeneity"]
        pos = sum(1 for d in cp.values() if d["mean_return"] > 0)
        assert pos > 0


class TestTemporalStability:
    def test_rolling_windows(self, phase10_results):
        ts = phase10_results["temporal_stability"]
        assert len(ts["rolling_6m"]) > 20

    def test_positive_windows_exist(self, phase10_results):
        ts = phase10_results["temporal_stability"]
        pos = sum(1 for r in ts["rolling_6m"] if r["mean_return"] > 0)
        assert pos > 0


class TestRandomization:
    def test_permutation_p(self, phase10_results):
        rn = phase10_results["randomization"]
        assert 0 <= rn["permutation_p"] <= 1

    def test_observed_vs_null(self, phase10_results):
        rn = phase10_results["randomization"]
        # Observed should be within reasonable range of null
        assert abs(rn["observed_expectancy"] - rn["null_mean"]) < 1.0


class TestClassification:
    def test_valid_classification(self, phase10_results):
        valid = {"A. NO SIGNAL", "B. PREDICTIVE BUT ECONOMICALLY USELESS",
                 "C. WEAK ECONOMIC EDGE", "D. ROBUST ECONOMIC EDGE",
                 "E. STRONG ECONOMIC EDGE"}
        assert phase10_results["final_classification"] in valid

    def test_classification_matches_metrics(self, phase10_results):
        # If classified as NO SIGNAL, AUC should be low or p high
        cls = phase10_results["final_classification"]
        if cls == "A. NO SIGNAL":
            assert (phase10_results["classification_vs_trading"]["auc"] < 0.52 or
                    phase10_results["randomization"]["permutation_p"] > 0.20)
