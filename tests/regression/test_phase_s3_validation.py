"""
Regression tests for Phase S3: Independent Validation.
"""
import json
import numpy as np
import pytest
from pathlib import Path


RESULTS = Path("research/output/simple_strategies/S3_independent_validation.json")


@pytest.fixture(scope="module")
def s3_results():
    with open(RESULTS) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# S3-A: Independent Implementation
# ═══════════════════════════════════════════════════════════════════════

class TestS3AIndependent:
    def test_independent_positive(self, s3_results):
        assert s3_results["S3A"]["independent"]["avg_pnl_pips"] > 0

    def test_s0_frozen_positive(self, s3_results):
        assert s3_results["S3A"]["s0_frozen"]["avg_pnl_pips"] > 0

    def test_signal_agreement_high(self, s3_results):
        assert s3_results["S3A"]["comparison"]["signal_agreement"] >= 0.95

    def test_pnl_difference_small(self, s3_results):
        diff = abs(s3_results["S3A"]["comparison"]["difference_pips"])
        assert diff < 5.0

    def test_independent_beats_zero(self, s3_results):
        assert s3_results["S3A"]["independent"]["profit_factor"] > 1.0


# ═══════════════════════════════════════════════════════════════════════
# S3-B: Execution Realism
# ═══════════════════════════════════════════════════════════════════════

class TestS3BExecutionRealism:
    def test_all_scenarios_positive(self, s3_results):
        b = s3_results["S3B"]
        for scenario in ["zero", "base", "conservative", "severe"]:
            assert b[scenario]["avg_pnl_pips"] > 0, f"{scenario} negative"

    def test_costs_reduce_pnl(self, s3_results):
        b = s3_results["S3B"]
        assert b["zero"]["avg_pnl_pips"] > b["base"]["avg_pnl_pips"]
        assert b["base"]["avg_pnl_pips"] > b["severe"]["avg_pnl_pips"]

    def test_breakeven_cost_large(self, s3_results):
        mult = s3_results["S3B"]["breakeven_cost_multiplier"]
        assert isinstance(mult, (int, float))
        assert mult > 5

    def test_delay_0_and_1_same(self, s3_results):
        b = s3_results["S3B"]
        assert b["delay_0bar"]["avg_pnl_pips"] == b["delay_1bar"]["avg_pnl_pips"]


# ═══════════════════════════════════════════════════════════════════════
# S3-C: Timing Audit
# ═══════════════════════════════════════════════════════════════════════

class TestS3CTimingAudit:
    def test_reproducibility_at_bar_close(self, s3_results):
        assert s3_results["S3C"]["reproducibility_at_bar_close"] == 1.0

    def test_signals_checked(self, s3_results):
        assert s3_results["S3C"]["total_signals_checked"] > 10000


# ═══════════════════════════════════════════════════════════════════════
# S3-D: Fresh Holdout
# ═══════════════════════════════════════════════════════════════════════

class TestS3DFreshHoldout:
    def test_train_positive(self, s3_results):
        assert s3_results["S3D"]["train_2016_2023"]["avg_pnl_pips"] > 0

    def test_holdout_positive(self, s3_results):
        assert s3_results["S3D"]["holdout_2024_2026"]["avg_pnl_pips"] > 0

    def test_holdout_retains_most_of_training(self, s3_results):
        deg = s3_results["S3D"]["degradation"]
        assert deg["holdout_retains_pct"] > 60

    def test_no_catastrophic_degradation(self, s3_results):
        deg = s3_results["S3D"]["degradation"]
        assert deg["train_to_holdout_pct"] > -40
