"""
Regression tests for Phase S4: Walk-Forward + Sensitivity.
"""
import json
import numpy as np
import pytest
from pathlib import Path


RESULTS = Path("research/output/simple_strategies/S4_walk_forward_sensitivity.json")


@pytest.fixture(scope="module")
def s4_results():
    with open(RESULTS) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# S4-A: Walk-Forward
# ═══════════════════════════════════════════════════════════════════════

class TestS4AWalkForward:
    def test_all_windows_positive(self, s4_results):
        for w in s4_results["S4A"]["windows"]:
            assert w["test"]["avg_pnl_pips"] > 0, f"Window {w['window']} negative"

    def test_positive_pct(self, s4_results):
        assert s4_results["S4A"]["summary"]["positive_pct"] >= 80

    def test_min_window_positive(self, s4_results):
        assert s4_results["S4A"]["summary"]["min_test_pnl"] > 0

    def test_average_pnl_positive(self, s4_results):
        assert s4_results["S4A"]["summary"]["avg_test_pnl"] > 5

    def test_has_enough_windows(self, s4_results):
        assert s4_results["S4A"]["summary"]["total_windows"] >= 10


# ═══════════════════════════════════════════════════════════════════════
# S4-B: Parameter Sensitivity
# ═══════════════════════════════════════════════════════════════════════

class TestS4BParamSensitivity:
    @pytest.mark.parametrize("param", [
        "lookback", "sl_mult", "rrr", "max_hold_days", "breakeven_ratio"
    ])
    def test_param_robust(self, s4_results, param):
        assert s4_results["S4B"]["stability"][param]["robust"], f"{param} not robust"

    @pytest.mark.parametrize("param", [
        "lookback", "sl_mult", "rrr", "max_hold_days", "breakeven_ratio"
    ])
    def test_all_variants_positive(self, s4_results, param):
        for r in s4_results["S4B"][param]:
            assert r["avg_pnl_pips"] > 0, f"{param}={r['param_value']} negative"

    @pytest.mark.parametrize("param", [
        "lookback", "sl_mult", "rrr", "max_hold_days", "breakeven_ratio"
    ])
    def test_low_cv(self, s4_results, param):
        assert s4_results["S4B"]["stability"][param]["cv"] < 0.2, f"{param} CV too high"


# ═══════════════════════════════════════════════════════════════════════
# S4-C: Regime-Conditioned
# ═══════════════════════════════════════════════════════════════════════

class TestS4CRegime:
    def test_trending_positive(self, s4_results):
        assert s4_results["S4C"]["trending"]["avg_pnl_pips"] > 0

    def test_ranging_positive(self, s4_results):
        assert s4_results["S4C"]["ranging"]["avg_pnl_pips"] > 0

    def test_high_vol_positive(self, s4_results):
        assert s4_results["S4C"]["high_vol"]["avg_pnl_pips"] > 0

    def test_low_vol_positive(self, s4_results):
        assert s4_results["S4C"]["low_vol"]["avg_pnl_pips"] > 0

    def test_all_regimes_positive(self, s4_results):
        for regime in ["trending", "ranging", "high_vol", "low_vol"]:
            assert s4_results["S4C"][regime]["avg_pnl_pips"] > 0

    def test_has_trades_in_all_regimes(self, s4_results):
        for regime in ["trending", "ranging", "high_vol", "low_vol"]:
            assert s4_results["S4C"][regime]["n"] > 100


# ═══════════════════════════════════════════════════════════════════════
# S4-D: Stress Scenarios
# ═══════════════════════════════════════════════════════════════════════

class TestS4DStress:
    def test_covid_positive(self, s4_results):
        assert s4_results["S4D"]["covid_crash_2020"]["avg_pnl_pips"] > 0

    def test_rate_hike_positive(self, s4_results):
        assert s4_results["S4D"]["rate_hike_2022"]["avg_pnl_pips"] > 0

    def test_severe_cost_positive(self, s4_results):
        assert s4_results["S4D"]["covid_crash_2020_severe_cost"]["avg_pnl_pips"] > 0

    def test_all_scenarios_positive(self, s4_results):
        for scenario in s4_results["S4D"]:
            assert s4_results["S4D"][scenario]["avg_pnl_pips"] > 0, f"{scenario} negative"
