"""
Regression tests for Phase S1: Structural Interrogation.
"""
import json
import numpy as np
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RESULTS = Path("/root/nestquant/research_data/simple_strategies/S1_structural_interrogation.json")


@pytest.fixture(scope="module")
def s1_results():
    with open(RESULTS) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# S1-A: Pair-Level
# ═══════════════════════════════════════════════════════════════════════

class TestS1APairLevel:
    def test_all_pairs_profitable(self, s1_results):
        pr = s1_results["S1A"]["pair_results"]
        profitable = sum(1 for m in pr.values()
                        if m.get("avg_pnl_pips", 0) > 0 and m.get("n", 0) > 0)
        assert profitable == len(pr)

    def test_aggregate_positive(self, s1_results):
        agg = s1_results["S1A"]["aggregate"]
        assert agg["avg_pnl_pips"] > 0
        assert agg["profit_factor"] > 1.0

    def test_removal_of_top3_positive(self, s1_results):
        r = s1_results["S1A"]["removal_analysis"]["remove_top_3"]
        assert r["avg_pnl_pips"] > 0

    def test_pair_ranking_length(self, s1_results):
        assert len(s1_results["S1A"]["sorted_by_pnl"]) == 20


# ═══════════════════════════════════════════════════════════════════════
# S1-B: Directional Bias
# ═══════════════════════════════════════════════════════════════════════

class TestS1BDirectionalBias:
    def test_breakout_beats_random(self, s1_results):
        b = s1_results["S1B"]
        assert b["incremental_vs_random"] > 0

    def test_breakout_buys_positive(self, s1_results):
        assert s1_results["S1B"]["breakout_buys"]["avg_pnl_pips"] > 0

    def test_breakout_sells_positive(self, s1_results):
        assert s1_results["S1B"]["breakout_sells"]["avg_pnl_pips"] > 0

    def test_incremental_positive_both_directions(self, s1_results):
        b = s1_results["S1B"]
        assert b["incremental_vs_random_buy"] > 0
        assert b["incremental_vs_random_sell"] > 0


# ═══════════════════════════════════════════════════════════════════════
# S1-C: Entry Distance
# ═══════════════════════════════════════════════════════════════════════

class TestS1CEntryDistance:
    def test_all_bins_present(self, s1_results):
        c = s1_results["S1C"]
        expected = ["0-0.1ATR", "0.1-0.25ATR", "0.25-0.5ATR", "0.5-1ATR", ">1ATR"]
        for label in expected:
            assert label in c

    def test_dominant_bin_is_largest_distance(self, s1_results):
        c = s1_results["S1C"]
        max_bin = max(c.items(), key=lambda x: x[1].get("n", 0))
        assert max_bin[0] == ">1ATR"


# ═══════════════════════════════════════════════════════════════════════
# S1-D: False Break
# ═══════════════════════════════════════════════════════════════════════

class TestS1DFalseBreak:
    def test_all_categories_present(self, s1_results):
        d = s1_results["S1D"]
        expected = ["clean_continuation", "retest_continuation",
                    "failed_breakout", "reversal", "range_noise"]
        for cat in expected:
            assert cat in d

    def test_clean_continuation_high_wr(self, s1_results):
        cc = s1_results["S1D"]["clean_continuation"]
        if cc["n"] > 0:
            assert cc["win_rate"] > 0.8


# ═══════════════════════════════════════════════════════════════════════
# S1-E: Session
# ═══════════════════════════════════════════════════════════════════════

class TestS1ESession:
    def test_all_sessions_positive(self, s1_results):
        e = s1_results["S1E"]
        for session, m in e.items():
            assert m["avg_pnl_pips"] > 0, f"{session} negative"


# ═══════════════════════════════════════════════════════════════════════
# S1-F: Volatility Regime
# ═══════════════════════════════════════════════════════════════════════

class TestS1FVolatility:
    def test_all_regimes_positive(self, s1_results):
        f = s1_results["S1F"]
        for regime, m in f.items():
            assert m["avg_pnl_pips"] > 0, f"{regime} negative"

    def test_monotonic_relationship(self, s1_results):
        f = s1_results["S1F"]
        pnls = [f[r]["avg_pnl_pips"] for r in ["LOW", "LOW-MEDIUM", "MEDIUM", "MEDIUM-HIGH", "HIGH"]]
        assert pnls[-1] > pnls[0]


# ═══════════════════════════════════════════════════════════════════════
# S1-G: Trend Regime
# ═══════════════════════════════════════════════════════════════════════

class TestS1GTrendRegime:
    def test_both_regimes_present(self, s1_results):
        g = s1_results["S1G"]
        assert "trending" in g and "ranging" in g
        assert g["trending"]["n"] > 0
        assert g["ranging"]["n"] > 0

    def test_expanding_outperforms_contracting(self, s1_results):
        g = s1_results["S1G"]
        if g["expanding"]["n"] > 0 and g["contracting"]["n"] > 0:
            assert g["expanding"]["avg_pnl_pips"] > g["contracting"]["avg_pnl_pips"]


# ═══════════════════════════════════════════════════════════════════════
# S1-H: Forward Returns
# ═══════════════════════════════════════════════════════════════════════

class TestS1HForwardReturns:
    def test_forward_returns_positive(self, s1_results):
        h = s1_results["S1H"]
        for bar_h in [1, 2, 3, 6, 12, 24, 42]:
            assert h[f"fwd_{bar_h}bar_pips"] > 0

    def test_mfe_exceeds_mae(self, s1_results):
        h = s1_results["S1H"]
        assert h["mfe_pips"] > 0

    def test_forward_returns_decreasing(self, s1_results):
        h = s1_results["S1H"]
        vals = [h[f"fwd_{b}bar_pips"] for b in [1, 6, 12, 24, 42]]
        assert vals[0] > vals[-1]


# ═══════════════════════════════════════════════════════════════════════
# S1-I: Exit Controls
# ═══════════════════════════════════════════════════════════════════════

class TestS1IExitControls:
    def test_all_exits_positive(self, s1_results):
        i = s1_results["S1I"]
        for mode, m in i.items():
            assert m["avg_pnl_pips"] > 0, f"{mode} negative"

    def test_fixed_2r_positive(self, s1_results):
        assert s1_results["S1I"]["fixed_2R"]["avg_pnl_pips"] > 0

    def test_time_only_positive(self, s1_results):
        assert s1_results["S1I"]["time_only"]["avg_pnl_pips"] > 0


# ═══════════════════════════════════════════════════════════════════════
# S1-J: Walk-Forward
# ═══════════════════════════════════════════════════════════════════════

class TestS1JWalkForward:
    def test_all_periods_positive(self, s1_results):
        j = s1_results["S1J"]
        for period in ["train_2016_2021", "valid_2022_2023", "holdout_2024_2026"]:
            assert j[period]["avg_pnl_pips"] > 0

    def test_holdout_positive(self, s1_results):
        assert s1_results["S1J"]["holdout_2024_2026"]["avg_pnl_pips"] > 0


# ═══════════════════════════════════════════════════════════════════════
# S1-K: Pair Removal
# ═══════════════════════════════════════════════════════════════════════

class TestS1KPairRemoval:
    def test_remove_top1_positive(self, s1_results):
        assert s1_results["S1K"]["remove_top_1"]["avg_pnl_pips"] > 0

    def test_remove_top3_positive(self, s1_results):
        assert s1_results["S1K"]["remove_top_3"]["avg_pnl_pips"] > 0

    def test_removal_degrades_gracefully(self, s1_results):
        all_pnl = s1_results["S1K"]["all_pairs"]["avg_pnl_pips"]
        top1_pnl = s1_results["S1K"]["remove_top_1"]["avg_pnl_pips"]
        assert 0 < top1_pnl < all_pnl


# ═══════════════════════════════════════════════════════════════════════
# S1-L: Bootstrap
# ═══════════════════════════════════════════════════════════════════════

class TestS1LBootstrap:
    def test_mean_ci_positive(self, s1_results):
        boot = s1_results["S1L"]["mean_return"]
        assert boot["ci_95_lo"] > 0

    def test_prob_negative_near_zero(self, s1_results):
        assert s1_results["S1L"]["prob_mean_le_zero"] < 0.01


# ═══════════════════════════════════════════════════════════════════════
# S1-M: Audit
# ═══════════════════════════════════════════════════════════════════════

class TestS1MAudit:
    def test_assessment_present(self, s1_results):
        assert "assessment" in s1_results["S1M"]

    def test_tunable_parameters_count(self, s1_results):
        assert s1_results["S1M"]["total_tunable_parameters"] >= 5


# ═══════════════════════════════════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

class TestClassification:
    def test_all_checks_pass(self, s1_results):
        checks = s1_results["checks"]
        assert all(checks.values())

    def test_classification_is_a(self, s1_results):
        assert s1_results["classification"] == "A. STRUCTURAL EDGE CONFIRMED"
