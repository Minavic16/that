"""
Regression tests for Phase S6: Adaptive Risk & Challenge Optimization.
"""
import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RESULTS = Path("/root/nestquant/research_data/simple_strategies/S6_adaptive_risk_challenge.json")


@pytest.fixture(scope="module")
def s6_results():
    with open(RESULTS) as f:
        return json.load(f)


class TestS6ABaseline:
    def test_trades_reproduced(self, s6_results):
        assert s6_results["S6A"]["n"] == 15321

    def test_win_rate(self, s6_results):
        assert 0.35 < s6_results["S6A"]["win_rate"] < 0.37

    def test_avg_pnl(self, s6_results):
        assert 17 < s6_results["S6A"]["avg_pnl_pips"] < 20

    def test_profit_factor(self, s6_results):
        assert 1.9 < s6_results["S6A"]["profit_factor"] < 2.1

    def test_8_losing_months(self, s6_results):
        assert s6_results["S6A"]["losing_months"] == 8

    def test_max_dd_r(self, s6_results):
        assert s6_results["S6A"]["max_dd_r"] > 15

    def test_max_loss_streak(self, s6_results):
        assert s6_results["S6A"]["max_loss_streak"] >= 15


class TestS6BVolQuality:
    def test_vq_50_half_reduces_dd(self, s6_results):
        s6b = s6_results["S6B"]["vq_50"]["low_quality_half"]
        baseline_dd = abs(s6_results["S6A"]["max_dd_pips"])
        assert abs(s6b["max_dd_pips"]) < baseline_dd

    def test_vq_50_half_retains_return(self, s6_results):
        s6b = s6_results["S6B"]["vq_50"]["low_quality_half"]
        assert s6b["retention_pct"] >= 95

    def test_all_vq_variants_profitable(self, s6_results):
        for vname in ["vq_20", "vq_50", "vq_100"]:
            for rname in ["low_quality_half", "low_quality_07"]:
                m = s6_results["S6B"][vname][rname]
                assert m["avg_pnl_pips"] > 0, f"{vname}/{rname} unprofitable"


class TestS6DRegimeTransition:
    def test_div_03_reduces_dd(self, s6_results):
        s6d = s6_results["S6D"]["div_03"]
        baseline_dd = abs(s6_results["S6A"]["max_dd_pips"])
        assert abs(s6d["max_dd_pips"]) < baseline_dd

    def test_div_03_retains_return(self, s6_results):
        s6d = s6_results["S6D"]["div_03"]
        assert s6d["retention_pct"] >= 98

    def test_all_transition_variants_profitable(self, s6_results):
        for vname in ["div_03", "div_05", "div_07"]:
            m = s6_results["S6D"][vname]
            assert m["avg_pnl_pips"] > 0, f"{vname} unprofitable"


class TestS6ECircuitBreaker:
    def test_cb_increases_dd(self, s6_results):
        baseline_dd = abs(s6_results["S6A"]["max_dd_pips"])
        for key in ["cb1_streak10", "cb2_streak15", "cb3_streak20"]:
            cb_dd = abs(s6_results["S6E"][key]["max_dd_pips"])
            assert cb_dd >= baseline_dd, f"{key} reduced DD (unexpected)"

    def test_cb_retains_return(self, s6_results):
        for key in ["cb1_streak10", "cb2_streak15", "cb3_streak20"]:
            assert s6_results["S6E"][key]["retention_pct"] >= 98


class TestS6FChallenge:
    def test_low_risk_survives(self, s6_results):
        for risk in ["risk_0.25%", "risk_0.30%", "risk_0.40%"]:
            cr = s6_results["S6F"][risk]
            assert cr["reached_target"] is True
            assert cr["violated_dd"] is False

    def test_025_risk_safe(self, s6_results):
        cr = s6_results["S6F"]["risk_0.25%"]
        assert cr["max_dd_pct"] < 5
        assert cr["prob_exceed_dd_monthly"] == 0

    def test_050_risk_marginal(self, s6_results):
        cr = s6_results["S6F"]["risk_0.50%"]
        assert cr["max_dd_pct"] < 10

    def test_100_risk_violates(self, s6_results):
        cr = s6_results["S6F"]["risk_1.00%"]
        assert cr["max_dd_pct"] > 10


class TestS6GMonteCarlo:
    def test_025_mc_safe(self, s6_results):
        mc = s6_results["S6H"]["risk_0.25%"]
        assert mc["prob_gt_10pct_dd"] < 0.05
        assert mc["prob_reached_target"] > 0.95

    def test_050_mc_marginal(self, s6_results):
        mc = s6_results["S6H"]["risk_0.50%"]
        assert mc["prob_gt_10pct_dd"] < 0.50

    def test_100_mc_dangerous(self, s6_results):
        mc = s6_results["S6H"]["risk_1.00%"]
        assert mc["prob_gt_10pct_dd"] > 0.80


class TestS6ICorrelation:
    def test_low_cross_pair_correlation(self, s6_results):
        assert s6_results["S6I"]["avg_cross_pair_correlation"] < 0.3

    def test_positive_sharpe(self, s6_results):
        assert s6_results["S6I"]["monthly_sharpe"] > 0.5
