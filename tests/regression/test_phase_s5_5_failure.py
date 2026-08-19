"""
Regression tests for Phase S5.5: Failure Analysis.
"""
import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RESULTS = Path("/root/nestquant/research_data/simple_strategies/S5_5_failure_analysis.json")


@pytest.fixture(scope="module")
def s55_results():
    with open(RESULTS) as f:
        return json.load(f)


class TestS55Basic:
    def test_8_losing_months(self, s55_results):
        assert s55_results["summary"]["losing_months"] == 8

    def test_127_total_months(self, s55_results):
        assert s55_results["summary"]["total_months"] == 127

    def test_15321_trades(self, s55_results):
        assert s55_results["summary"]["total_trades"] == 15321


class TestS55LosingMonthProfile:
    def test_all_losing_months_have_high_failure_rate(self, s55_results):
        for m in s55_results["losing_month_details"]:
            assert m["failed_breakout_rate"] > 0.86, \
                f"{m['month']} failure rate {m['failed_breakout_rate']:.1%} < 86%"

    def test_losing_months_have_negative_pnl(self, s55_results):
        for m in s55_results["losing_month_details"]:
            assert m["total_pnl"] < 0

    def test_losing_months_have_low_pf(self, s55_results):
        for m in s55_results["losing_month_details"]:
            assert m["profit_factor"] < 1.05

    def test_winning_months_have_positive_pnl(self, s55_results):
        for m in s55_results["winning_month_details"]:
            assert m["total_pnl"] >= 0


class TestS55FailureClustering:
    def test_losing_month_fail_rate_higher(self, s55_results):
        fb = s55_results["failed_breakout"]
        assert fb["losing_month_fail_rate"] > fb["winning_month_fail_rate"]

    def test_fail_rate_ratio_above_1(self, s55_results):
        assert s55_results["failed_breakout"]["fail_rate_ratio"] > 1.0


class TestS55Volatility:
    def test_vol_pnl_positive_correlation(self, s55_results):
        assert s55_results["volatility"]["corr_vol_pnl"] > 0.2

    def test_lowest_vol_bucket_worst_pnl(self, s55_results):
        wr = s55_results["volatility"]["win_rate_by_vol_bucket"]
        if "1" in wr and "4" in wr:
            assert wr["1"]["avg_pnl"] < wr["4"]["avg_pnl"]


class TestS55Directional:
    def test_long_short_symmetric(self, s55_results):
        ds = s55_results["directional"]["direction_stats"]
        assert "long" in ds and "short" in ds
        wr_diff = abs(ds["long"]["win_rate"] - ds["short"]["win_rate"])
        assert wr_diff < 0.05, f"Directional WR diff {wr_diff:.1%} > 5%"

    def test_both_directions_profitable(self, s55_results):
        ds = s55_results["directional"]["direction_stats"]
        assert ds["long"]["avg_pnl"] > 0
        assert ds["short"]["avg_pnl"] > 0


class TestS55Instruments:
    def test_all_instruments_profitable(self, s55_results):
        for inst in s55_results["instrument"]["instrument_stats"]:
            assert inst["total_pnl"] > 0, f"{inst['pair']} unprofitable"


class TestS55LossStreaks:
    def test_max_streak_27(self, s55_results):
        assert s55_results["loss_streaks"]["streak_distribution"]["max_length"] == 27

    def test_streak_mean_under_5(self, s55_results):
        assert s55_results["loss_streaks"]["streak_distribution"]["mean_length"] < 5


class TestS55RegimeTransition:
    def test_transition_correlation_positive(self, s55_results):
        assert s55_results["regime_transition"]["corr_vol_transition_pnl"] > 0

    def test_losing_months_higher_transition_rate(self, s55_results):
        rt = s55_results["regime_transition"]
        if rt["losing_month_transition_rate"] is not None and rt["winning_month_transition_rate"] is not None:
            assert rt["losing_month_transition_rate"] > rt["winning_month_transition_rate"]


class TestS55FailureClassification:
    def test_classification_exists(self, s55_results):
        fc = s55_results["failure_classification"]
        assert len(fc["classifications"]) > 0

    def test_primary_is_not_instrument_or_directional(self, s55_results):
        fc = s55_results["failure_classification"]
        assert "INSTRUMENT" not in fc["primary"]
        assert "DIRECTIONAL" not in fc["primary"]
