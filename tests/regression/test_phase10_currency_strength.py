"""Regression tests for Phase 10 Core Economic Validation."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PHASE10_DIR = Path("/root/nestquant/research_data/phase10")


@pytest.fixture(scope="module")
def phase10_results():
    with open(PHASE10_DIR / "phase10_results.json") as f:
        return json.load(f)


class TestImplementationAudit:
    def test_lookbacks_correct(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["strength_lookbacks"] == [[10, 0.4], [20, 0.3], [40, 0.2], [80, 0.1]]

    def test_normalize_window(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["strength_normalize_window"] == 200

    def test_forward_returns_in_pips(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["forward_returns_in_pips"] is True

    def test_no_lookahead(self, phase10_results):
        ia = phase10_results["implementation_audit"]
        assert ia["no_lookahead"] is True


class TestUniverseComparison:
    def test_full_universe_has_1h(self, phase10_results):
        uc = phase10_results["universe_comparison"]
        assert "full_28" in uc
        assert "n" in uc["full_28"]

    def test_full_universe_1h_positive(self, phase10_results):
        m = phase10_results["universe_comparison"]["full_28"]
        assert m["mean_return"] > 0

    def test_full_universe_large_sample(self, phase10_results):
        m = phase10_results["universe_comparison"]["full_28"]
        assert m["n"] > 10000

    def test_tradeable_universe_1h_negative(self, phase10_results):
        m = phase10_results["universe_comparison"]["tradeable_7"]
        assert m["mean_return"] < 0


class TestStrongestVsWeakest:
    def test_all_horizons_present(self, phase10_results):
        sw = phase10_results["strongest_vs_weakest"]["full_28"]
        for h in ["5min", "15min", "30min", "1h", "4h", "8h", "1d"]:
            assert h in sw

    def test_returns_increase_with_horizon(self, phase10_results):
        sw = phase10_results["strongest_vs_weakest"]["full_28"]
        # 4h should be larger than 1h
        assert sw["4h"]["mean_return"] > sw["1h"]["mean_return"]

    def test_sample_sizes_large(self, phase10_results):
        sw = phase10_results["strongest_vs_weakest"]["full_28"]
        for h in ["1h", "4h"]:
            assert sw[h]["n"] > 10000


class TestDecileAnalysis:
    def test_decile_count(self, phase10_results):
        d = phase10_results["deciles"]
        assert "1h" in d
        assert len(d["1h"]) >= 8

    def test_middle_deciles_positive(self, phase10_results):
        decs = phase10_results["deciles"]["1h"]
        # D4-D7 should be positive
        mid = [d for d in decs if 4 <= d["decile"] <= 7]
        assert all(d["mean_return"] > 0 for d in mid)

    def test_extreme_deciles_negative(self, phase10_results):
        decs = phase10_results["deciles"]["1h"]
        # D9-D10 should be negative
        high = [d for d in decs if d["decile"] >= 9]
        assert all(d["mean_return"] < 0 for d in high)


class TestRegimeAnalysis:
    def test_regimes_present(self, phase10_results):
        r = phase10_results["regimes"]
        assert "2016-2018" in r
        assert "2019-2021" in r

    def test_2019_2021_4h_positive(self, phase10_results):
        m = phase10_results["regimes"]["2019-2021"]["4h"]
        assert m["mean_return"] > 0
        assert m["p_value"] < 0.05

    def test_2022_2024_negative(self, phase10_results):
        m = phase10_results["regimes"]["2022-2024"]["4h"]
        assert m["mean_return"] < 0


class TestPairLevel:
    def test_pairs_analyzed(self, phase10_results):
        pl = phase10_results["pair_level"]
        assert len(pl) >= 15

    def test_usdjpy_positive(self, phase10_results):
        pl = phase10_results["pair_level"]
        assert "USD/JPY" in pl
        assert pl["USD/JPY"]["1h"]["mean_return"] > 0

    def test_gbpjpy_positive(self, phase10_results):
        pl = phase10_results["pair_level"]
        assert "GBP/JPY" in pl
        assert pl["GBP/JPY"]["1h"]["mean_return"] > 0

    def test_most_pairs_negative(self, phase10_results):
        pl = phase10_results["pair_level"]
        neg = sum(1 for p in pl if "1h" in pl[p] and pl[p]["1h"]["mean_return"] < 0)
        assert neg > len(pl) * 0.5


class TestAutocorrelation:
    def test_lag1_high(self, phase10_results):
        ac = phase10_results["autocorrelation"]
        assert "1" in ac
        assert ac["1"]["autocorrelation"] > 0.9

    def test_persistence_decays(self, phase10_results):
        ac = phase10_results["autocorrelation"]
        assert ac["1"]["autocorrelation"] > ac["48"]["autocorrelation"]

    def test_lag48_positive(self, phase10_results):
        ac = phase10_results["autocorrelation"]
        assert ac["48"]["autocorrelation"] > 0


class TestPermutation:
    def test_observed_positive(self, phase10_results):
        perm = phase10_results["permutation"]
        assert perm["observed_mean"] > 0

    def test_permutation_not_significant(self, phase10_results):
        perm = phase10_results["permutation"]
        assert perm["permutation_p_value"] > 0.1

    def test_null_mean_near_zero(self, phase10_results):
        perm = phase10_results["permutation"]
        assert abs(perm["null_mean"]) < 0.1


class TestCostSensitivity:
    def test_gross_positive(self, phase10_results):
        cs = phase10_results["cost_sensitivity"]
        assert cs["COST_0"]["net_expectancy"] > 0

    def test_base_costs_destroy_edge(self, phase10_results):
        cs = phase10_results["cost_sensitivity"]
        assert cs["COST_BASE"]["net_expectancy"] < 0

    def test_break_even_between_0_and_low(self, phase10_results):
        cs = phase10_results["cost_sensitivity"]
        assert cs["COST_0"]["net_expectancy"] > 0
        assert cs["COST_LOW"]["net_expectancy"] < 0


class TestClassification:
    def test_classification_c(self, phase10_results):
        assert phase10_results["classification"].startswith("C")

    def test_decision_conditional(self, phase10_results):
        assert "CONDITIONAL" in phase10_results["research_decision"]


class TestOutputFiles:
    def test_results_json_exists(self):
        assert (PHASE10_DIR / "phase10_results.json").exists()

    def test_summary_csv_exists(self):
        assert (PHASE10_DIR / "phase10_summary.csv").exists()

    def test_pair_results_csv_exists(self):
        assert (PHASE10_DIR / "phase10_pair_results.csv").exists()

    def test_audit_exists(self):
        assert (PHASE10_DIR / "PHASE10_IMPLEMENTATION_AUDIT.md").exists()

    def test_report_exists(self):
        assert (PHASE10_DIR / "PHASE10_CORE_ECONOMIC_VALIDATION_REPORT.md").exists()
