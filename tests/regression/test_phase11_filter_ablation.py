"""Regression tests for Phase 11 Filter Ablation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


PHASE11_DIR = Path("research/output/phase11_currency")


@pytest.fixture(scope="module")
def phase11_results():
    with open(PHASE11_DIR / "phase11_results.json") as f:
        return json.load(f)


class TestFilterCount:
    def test_six_filters(self, phase11_results):
        assert len(phase11_results["filters"]) == 6

    def test_all_filters_have_hypothesis(self, phase11_results):
        for fname, fdata in phase11_results["filters"].items():
            assert "hypothesis" in fdata, f"{fname} missing hypothesis"

    def test_all_filters_have_oos(self, phase11_results):
        for fname, fdata in phase11_results["filters"].items():
            assert "oos_filtered" in fdata, f"{fname} missing oos_filtered"


class TestGapRangeFilter:
    def test_gap_thresholds(self, phase11_results):
        f = phase11_results["filters"]["gap_range"]
        t = f["discovery_thresholds"]
        assert t["gap_q40"] < t["gap_q70"]

    def test_gap_filtered_reduces_sample(self, phase11_results):
        f = phase11_results["filters"]["gap_range"]
        for h in ["1h", "4h"]:
            assert f["discovery_filtered"][h]["n"] < f["discovery_all"][h]["n"]


class TestJPYFilter:
    def test_jpy_reduces_sample(self, phase11_results):
        f = phase11_results["filters"]["jpy_crosses"]
        for h in ["1h", "4h"]:
            assert f["discovery_filtered"][h]["n"] < f["discovery_all"][h]["n"]

    def test_jpy_discovery_positive(self, phase11_results):
        f = phase11_results["filters"]["jpy_crosses"]
        assert f["discovery_filtered"]["4h"]["mean_return"] > 0


class TestSessionFilter:
    def test_session_reduces_sample(self, phase11_results):
        f = phase11_results["filters"]["session_overlap"]
        for h in ["1h", "4h"]:
            assert f["discovery_filtered"][h]["n"] < f["discovery_all"][h]["n"]


class TestTrendFilter:
    def test_trend_reduces_sample(self, phase11_results):
        f = phase11_results["filters"]["trend_alignment"]
        for h in ["1h", "4h"]:
            assert f["discovery_filtered"][h]["n"] < f["discovery_all"][h]["n"]


class TestCurrencyStructureFilter:
    def test_rank_threshold(self, phase11_results):
        f = phase11_results["filters"]["currency_structure"]
        assert f["discovery_thresholds"]["gap_abs_q90"] > 0

    def test_rank_reduces_sample(self, phase11_results):
        f = phase11_results["filters"]["currency_structure"]
        for h in ["1h", "4h"]:
            assert f["discovery_filtered"][h]["n"] < f["discovery_all"][h]["n"]


class TestCombinations:
    def test_combo_count(self, phase11_results):
        assert len(phase11_results["combinations"]) == 4

    def test_gap_only_has_4h(self, phase11_results):
        c = phase11_results["combinations"]["gap_only"]
        assert "4h" in c["oos"]

    def test_gap_jpy_session_4h_positive_oos(self, phase11_results):
        c = phase11_results["combinations"]["gap_jpy_session"]
        assert c["oos"]["4h"]["mean_return"] > 0

    def test_gap_jpy_session_4h_significant(self, phase11_results):
        c = phase11_results["combinations"]["gap_jpy_session"]
        assert c["oos"]["4h"]["p_value"] < 0.05

    def test_gap_jpy_session_4h_net_positive(self, phase11_results):
        c = phase11_results["combinations"]["gap_jpy_session"]
        assert c["oos"]["4h"]["net_expectancy"] > 0

    def test_combo_filters_additive(self, phase11_results):
        c = phase11_results["combinations"]
        n_gap = c["gap_only"]["oos"]["4h"]["n"]
        n_jpy = c["gap_plus_jpy"]["oos"]["4h"]["n"]
        n_sess = c["gap_jpy_session"]["oos"]["4h"]["n"]
        assert n_jpy <= n_gap
        assert n_sess <= n_jpy


class TestClassifications:
    def test_all_filters_classified(self, phase11_results):
        cl = phase11_results["classifications"]
        for fname in phase11_results["filters"]:
            for h in ["1h", "4h"]:
                assert f"{fname}_{h}" in cl

    def test_gap_jpy_session_4h_is_a(self, phase11_results):
        cl = phase11_results["classifications"]
        assert cl["combo_gap_jpy_session_4h"].startswith("A")


class TestResearchDecision:
    def test_decision_proceed(self, phase11_results):
        assert "PROCEED" in phase11_results["research_decision"]


class TestOutputFiles:
    def test_results_json_exists(self):
        assert (PHASE11_DIR / "phase11_results.json").exists()

    def test_summary_csv_exists(self):
        assert (PHASE11_DIR / "phase11_summary.csv").exists()

    def test_report_exists(self):
        assert (PHASE11_DIR / "PHASE11_FILTER_ABLATION_REPORT.md").exists()
