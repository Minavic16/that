"""Regression tests for Phase 9B Corrected Economic Validation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


PHASE9B_DIR = Path("research/output/phase9b")


@pytest.fixture(scope="module")
def phase9b_results():
    with open(PHASE9B_DIR / "phase9b_corrected_validation.json") as f:
        return json.load(f)


class TestAccountingValidation:
    def test_pip_value_eurusd(self, phase9b_results):
        av = phase9b_results["accounting_validation"]
        assert av["pip_value_eurusd"] == 10.0

    def test_pip_value_usdjpy(self, phase9b_results):
        av = phase9b_results["accounting_validation"]
        assert abs(av["pip_value_usdjpy"] - 6.70) < 0.01

    def test_returns_in_pips(self, phase9b_results):
        av = phase9b_results["accounting_validation"]
        assert av["forward_returns_in_pips"] is True

    def test_cost_pair_specific(self, phase9b_results):
        av = phase9b_results["accounting_validation"]
        assert av["cost_pair_specific"] is True


class TestEventSummary:
    def test_events_exist(self, phase9b_results):
        es = phase9b_results["event_summary"]
        assert es["total"] > 200000

    def test_fast_mr_dominant(self, phase9b_results):
        es = phase9b_results["event_summary"]
        assert es["fast_mr"] > es["slow_mr"]


class TestGlobalThresholds:
    def test_all_thresholds_present(self, phase9b_results):
        gt = phase9b_results["global_thresholds"]
        assert len(gt) == 10

    def test_thresholds_vary(self, phase9b_results):
        gt = phase9b_results["global_thresholds"]
        n_values = [gt[str(t)]["n_trades"] for t in [0.50, 0.70, 0.90]]
        assert n_values[0] > n_values[2], "Higher threshold should have fewer trades"

    def test_cost_scenarios_present(self, phase9b_results):
        gt = phase9b_results["global_thresholds"]
        for thr in ["0.5", "0.7", "0.9"]:
            assert "cost_scenarios" in gt[thr]


class TestWalkForward:
    def test_all_folds_present(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        assert len(wf) == 5

    def test_threshold_selected(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "selected_threshold" in r
            assert 0.50 <= r["selected_threshold"] <= 0.95

    def test_gated_results_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "gated" in r
            assert r["gated"]["n_trades"] > 0

    def test_baseline_results_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "baseline" in r
            assert r["baseline"]["n_trades"] > 1000

    def test_oracle_results_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "oracle" in r

    def test_cost_scenarios_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "cost_scenarios" in r
            assert len(r["cost_scenarios"]) == 4

    def test_threshold_robustness_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "threshold_robustness" in r

    def test_random_control_exist(self, phase9b_results):
        wf = phase9b_results["wf_results"]
        for label, r in wf.items():
            assert "random_control" in r


class TestAggregatedOOS:
    def test_baseline_exists(self, phase9b_results):
        agg = phase9b_results["aggregated"]
        assert agg["baseline"]["n_trades"] > 50000

    def test_oracle_exists(self, phase9b_results):
        agg = phase9b_results["aggregated"]
        assert agg["oracle"]["n_trades"] > 20000

    def test_gated_070_exists(self, phase9b_results):
        agg = phase9b_results["aggregated"]
        assert "gated_070" in agg


class TestPairHoldout:
    def test_five_folds(self, phase9b_results):
        ph = phase9b_results["aggregated"]["pair_holdout"]
        assert len(ph) == 5

    def test_all_have_threshold(self, phase9b_results):
        ph = phase9b_results["aggregated"]["pair_holdout"]
        for fold in ph:
            assert "threshold" in fold
            assert fold["threshold"] > 0


class TestRegime:
    def test_four_periods(self, phase9b_results):
        regime = phase9b_results["aggregated"]["regime"]
        assert len(regime) == 4

    def test_all_have_trades(self, phase9b_results):
        regime = phase9b_results["aggregated"]["regime"]
        for period, data in regime.items():
            assert data["n_trades"] > 1000


class TestCalibration:
    def test_brier_score(self, phase9b_results):
        cal = phase9b_results["aggregated"]["calibration"]
        assert 0 < cal["brier_score"] < 1

    def test_calibration_error(self, phase9b_results):
        cal = phase9b_results["aggregated"]["calibration"]
        assert 0 <= cal["calibration_error"] < 0.10


class TestDeciles:
    def test_ten_deciles(self, phase9b_results):
        dec = phase9b_results["aggregated"]["deciles"]
        assert len(dec) == 10

    def test_monotonic_actual_rate(self, phase9b_results):
        dec = phase9b_results["aggregated"]["deciles"]
        rates = [d["actual_fast_rate"] for d in dec]
        assert rates[-1] > rates[0], "Higher decile should have higher actual fast rate"


class TestVerdict:
    def test_verdict_present(self, phase9b_results):
        assert "verdict" in phase9b_results

    def test_verdict_valid(self, phase9b_results):
        valid = {"SUPPORTED — TRADABLE", "SUPPORTED — BUT COST SENSITIVE",
                 "STATISTICALLY SUPPORTED — NOT ECONOMICALLY VIABLE",
                 "REGIME DEPENDENT", "UNSTABLE", "REJECTED"}
        assert phase9b_results["verdict"] in valid

    def test_verdict_not_rejected(self, phase9b_results):
        assert phase9b_results["verdict"] != "REJECTED"
