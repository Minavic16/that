"""Regression tests for Phase 11 Economic Conditional Structure."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PHASE11_DIR = Path("/root/nestquant/research_data/phase11")


@pytest.fixture(scope="module")
def phase11_results():
    with open(PHASE11_DIR / "phase11_results.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def trade_results():
    rows = []
    with open(PHASE11_DIR / "phase11_trade_results.csv") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


class TestImplementationAudit:
    def test_pip_value_correct(self, phase11_results):
        ia = phase11_results["implementation_audit"]
        assert ia["pip_value_eurusd"] == 10.0
        assert abs(ia["pip_value_usdjpy"] - 6.70) < 0.01

    def test_returns_in_pips(self, phase11_results):
        ia = phase11_results["implementation_audit"]
        assert ia["forward_returns_in_pips"] is True

    def test_costs_pair_specific(self, phase11_results):
        ia = phase11_results["implementation_audit"]
        assert ia["cost_pair_specific"] is True

    def test_no_lookahead(self, phase11_results):
        ia = phase11_results["implementation_audit"]
        assert ia["no_lookahead"] is True


class TestEventSummary:
    def test_total_events(self, phase11_results):
        es = phase11_results["event_summary"]
        assert es["total"] > 200000

    def test_oos_events(self, phase11_results):
        es = phase11_results["event_summary"]
        assert es["oos"] > 100000

    def test_oos_less_than_total(self, phase11_results):
        es = phase11_results["event_summary"]
        assert es["oos"] < es["total"]


class TestSignalBinResults:
    def test_bin_count(self, phase11_results):
        assert len(phase11_results["signal_bin_results"]) == 10

    def test_monotonicity_violated(self, phase11_results):
        bins = phase11_results["signal_bin_results"]
        returns = [b["mean_return"] for b in bins]
        # Returns should NOT be monotonic (this is the key finding)
        # Check that at least one bin > 0 and one bin < 0
        has_positive = any(r > 0 for r in returns)
        has_negative = any(r < 0 for r in returns)
        assert has_positive and has_negative

    def test_peak_at_075_080(self, phase11_results):
        bins = phase11_results["signal_bin_results"]
        returns = [b["mean_return"] for b in bins]
        # Peak should be at bin index 5 (0.75-0.80)
        peak_idx = np.argmax(returns)
        assert peak_idx == 5

    def test_high_confidence_negative(self, phase11_results):
        bins = phase11_results["signal_bin_results"]
        last_bin = bins[-1]
        assert last_bin["mean_return"] < 0

    def test_calibration(self, phase11_results):
        bins = phase11_results["signal_bin_results"]
        for b in bins:
            # Predicted probability should be close to actual fast rate
            diff = abs(b["mean_pred_p"] - b["actual_fast_rate"])
            assert diff < 0.1, f"Calibration off for {b['bin_label']}: {diff}"


class TestCostBreakpoint:
    def test_overall_median(self, phase11_results):
        cb = phase11_results["cost_breakpoint"]["overall"]
        assert abs(cb["median"] - 0.10) < 0.01

    def test_surviving_1pip(self, phase11_results):
        cb = phase11_results["cost_breakpoint"]["overall"]
        assert 40 < cb["pct_surviving_10"] < 55

    def test_by_pair_exists(self, phase11_results):
        cb = phase11_results["cost_breakpoint"]["by_pair"]
        assert len(cb) >= 15


class TestPairSelectResults:
    def test_all_rules_present(self, phase11_results):
        psr = phase11_results["pair_select_results"]
        assert "all_pairs" in psr
        assert "positive_exp" in psr
        assert "be_gte_05" in psr
        assert "be_gte_075" in psr
        assert "be_gte_10" in psr

    def test_baseline_mean_return(self, phase11_results):
        psr = phase11_results["pair_select_results"]
        assert abs(psr["all_pairs"]["mean_return"] - 0.08) < 0.1

    def test_all_negative_after_base_costs(self, phase11_results):
        psr = phase11_results["pair_select_results"]
        for rule, d in psr.items():
            assert d["net_exp_base"] < 0, f"{rule} should be negative after base costs"


class TestRegimeConditional:
    def test_low_vol_negative(self, phase11_results):
        rc = phase11_results["regime_conditional"]
        assert rc["vol_low_vol"]["mean_return"] < 0

    def test_strong_trend_positive(self, phase11_results):
        rc = phase11_results["regime_conditional"]
        assert rc["trend_strong_trend"]["mean_return"] > 0

    def test_ny_session_negative(self, phase11_results):
        rc = phase11_results["regime_conditional"]
        assert rc["session_new_york"]["mean_return"] < -1.0

    def test_overlap_best_session(self, phase11_results):
        rc = phase11_results["regime_conditional"]
        assert rc["session_overlap"]["mean_return"] > rc["session_london"]["mean_return"]
        assert rc["session_overlap"]["mean_return"] > rc["session_new_york"]["mean_return"]


class TestEconVsClass:
    def test_direction_corr_near_zero(self, phase11_results):
        ec = phase11_results["econ_vs_class"]
        assert abs(ec["corr_pfast_return"]) < 0.01

    def test_direction_not_significant(self, phase11_results):
        ec = phase11_results["econ_vs_class"]
        assert ec["p_value_direction"] > 0.1

    def test_abs_return_corr_positive(self, phase11_results):
        ec = phase11_results["econ_vs_class"]
        assert ec["corr_pfast_abs_return"] > 0.03

    def test_abs_return_corr_significant(self, phase11_results):
        ec = phase11_results["econ_vs_class"]
        assert ec["p_value_abs"] < 0.001


class TestMultipleTesting:
    def test_many_tests(self, phase11_results):
        mt = phase11_results["multiple_testing"]
        assert mt["n_subgroup_tests"] > 100

    def test_bonferroni_alpha(self, phase11_results):
        mt = phase11_results["multiple_testing"]
        assert mt["bonferroni_alpha"] < 0.001


class TestClassification:
    def test_classification_a(self, phase11_results):
        assert phase11_results["classification"].startswith("A")

    def test_research_decision_no(self, phase11_results):
        assert phase11_results["research_decision"].startswith("NO")

    def test_low_profitable_ratio(self, phase11_results):
        assert phase11_results["n_profitable_pair_thr"] < 20
        ratio = phase11_results["n_profitable_pair_thr"] / max(phase11_results["n_total_pair_thr"], 1)
        assert ratio < 0.15


class TestTradeResults:
    def test_row_count(self, trade_results):
        assert len(trade_results) > 100000

    def test_columns_present(self, trade_results):
        row = trade_results[0]
        assert "pair" in row
        assert "fwd_ret_pips" in row
        assert "pfast" in row
        assert "outcome" in row

    def test_pfast_range(self, trade_results):
        for row in trade_results:
            p = float(row["pfast"])
            assert 0.0 <= p <= 1.0


class TestPairResults:
    def test_csv_exists(self):
        assert (PHASE11_DIR / "phase11_pair_results.csv").exists()

    def test_regime_csv_exists(self):
        assert (PHASE11_DIR / "phase11_regime_results.csv").exists()


class TestConsistencyWithPhase10:
    def test_gross_edge_matches(self, phase11_results):
        # Phase 10 reported +0.082 pip gross edge
        # Phase 11 all_pairs baseline should be close
        psr = phase11_results["pair_select_results"]
        assert abs(psr["all_pairs"]["mean_return"] - 0.082) < 0.02

    def test_oos_count_matches(self, phase11_results):
        es = phase11_results["event_summary"]
        assert abs(es["oos"] - 114330) < 100
