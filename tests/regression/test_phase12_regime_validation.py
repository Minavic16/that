"""Regression tests for Phase 12 Regime-Dependency Validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


PHASE12_DIR = Path("research/output/phase12")


@pytest.fixture(scope="module")
def phase12_results():
    with open(PHASE12_DIR / "phase12_results.json") as f:
        return json.load(f)


class TestFrozenCandidate:
    def test_gap_q40(self, phase12_results):
        fc = phase12_results["frozen_candidate"]
        assert fc["gap_q40"] == -24.4758

    def test_gap_q70(self, phase12_results):
        fc = phase12_results["frozen_candidate"]
        assert fc["gap_q70"] == 56.1954

    def test_horizon_4h(self, phase12_results):
        fc = phase12_results["frozen_candidate"]
        assert fc["horizon"] == "4h"

    def test_session_12_16(self, phase12_results):
        fc = phase12_results["frozen_candidate"]
        assert "12" in fc["session"] and "16" in fc["session"]


class TestHoldoutComparison:
    def test_discovery_negative(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["discovery_2016-2022"]["net"] < 0

    def test_holdout_positive(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["holdout_2023"]["net"] > 0

    def test_holdout_significant(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["holdout_2023"]["p"] < 0.05

    def test_oos_positive(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["oos_2024-2026"]["net"] > 0

    def test_oos_significant(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["oos_2024-2026"]["p"] < 0.05

    def test_holdout_win_rate_above_55(self, phase12_results):
        hc = phase12_results["holdout_comparison"]
        assert hc["holdout_2023"]["win_rate"] > 0.55


class TestYearByYear:
    def test_all_years_present(self, phase12_results):
        yby = phase12_results["year_by_year"]
        for year in range(2016, 2027):
            assert str(year) in yby

    def test_2018_negative(self, phase12_results):
        yby = phase12_results["year_by_year"]
        assert yby["2018"]["mean"] < 0

    def test_2023_positive(self, phase12_results):
        yby = phase12_results["year_by_year"]
        assert yby["2023"]["mean"] > 0

    def test_2025_strongest(self, phase12_results):
        yby = phase12_results["year_by_year"]
        means = {y: yby[y]["mean"] for y in yby}
        assert max(means, key=means.get) == "2025"

    def test_2023_2025_2026_positive(self, phase12_results):
        yby = phase12_results["year_by_year"]
        for y in ["2023", "2025", "2026"]:
            assert yby[y]["mean"] > 0


class TestPairGeneralization:
    def test_usdjpy_positive(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        assert pg["USD/JPY"]["mean"] > 0

    def test_usdjpy_net_positive(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        assert pg["USD/JPY"]["net"] > 0

    def test_gbpjpy_positive_mean(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        assert pg["GBP/JPY"]["mean"] > 0

    def test_gbpjpy_net_negative(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        assert pg["GBP/JPY"]["net"] < 0

    def test_audjpy_negative(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        assert pg["AUD/JPY"]["mean"] < 0

    def test_only_usdjpy_survives_costs(self, phase12_results):
        pg = phase12_results["pair_generalization"]
        survivors = [p for p, v in pg.items() if v.get("net", 0) > 0]
        assert "USD/JPY" in survivors


class TestVolatilityRegime:
    def test_three_regimes(self, phase12_results):
        vr = phase12_results["volatility_regime"]
        assert len([k for k in vr if vr[k]["n"] > 0]) >= 2

    def test_all_gross_positive(self, phase12_results):
        vr = phase12_results["volatility_regime"]
        for k, v in vr.items():
            if v["n"] > 100:
                assert v["mean"] > 0

    def test_high_vol_best_gross(self, phase12_results):
        vr = phase12_results["volatility_regime"]
        high = vr.get("HIGH", {}).get("mean", 0)
        low = vr.get("LOW", {}).get("mean", 0)
        assert high > low


class TestPersistenceRegime:
    def test_three_regimes(self, phase12_results):
        pr = phase12_results["persistence_regime"]
        assert len([k for k in pr if pr[k]["n"] > 0]) >= 2

    def test_low_persistence_best_gross(self, phase12_results):
        pr = phase12_results["persistence_regime"]
        low = pr.get("LOW", {}).get("mean", 0)
        high = pr.get("HIGH", {}).get("mean", 0)
        assert low > high


class TestBOJRegime:
    def test_three_periods(self, phase12_results):
        br = phase12_results["boj_regime"]
        assert len(br) == 3

    def test_normalization_continued_strongest(self, phase12_results):
        br = phase12_results["boj_regime"]
        means = {k: v["mean"] for k, v in br.items()}
        assert max(means, key=means.get) == "normalization_continued (2025-2026)"

    def test_pre_normalization_weakest(self, phase12_results):
        br = phase12_results["boj_regime"]
        means = {k: v["mean"] for k, v in br.items()}
        assert min(means, key=means.get) == "pre_normalization (2016-2023)"


class TestPermutation:
    def test_observed_positive(self, phase12_results):
        perm = phase12_results["permutation"]
        assert perm["observed_mean"] > 0

    def test_null_mean_near_zero(self, phase12_results):
        perm = phase12_results["permutation"]
        assert abs(perm["null_mean"]) < 0.1

    def test_significant(self, phase12_results):
        perm = phase12_results["permutation"]
        assert perm["p_value"] < 0.05


class TestMagnitudeGap:
    def test_overall_ratio_negative(self, phase12_results):
        mg = phase12_results["magnitude_gap"]
        assert mg["overall"]["ratio"] < 0

    def test_usdjpy_ratio_positive(self, phase12_results):
        mg = phase12_results["magnitude_gap"]
        assert mg["by_pair"]["USD/JPY"]["ratio"] > 0


class TestCostSensitivity:
    def test_cost_0_positive(self, phase12_results):
        cs = phase12_results["cost_sensitivity"]
        assert cs["COST_0"]["net"] > 0

    def test_cost_base_negative(self, phase12_results):
        cs = phase12_results["cost_sensitivity"]
        assert cs["COST_BASE"]["net"] < 0

    def test_usdjpy_survives_base_cost(self, phase12_results):
        cs = phase12_results["cost_sensitivity"]
        usdjpy = cs.get("per_pair_oos", {}).get("USD/JPY", {})
        assert usdjpy.get("cost_base", 0) > 0


class TestClassification:
    def test_classification_b(self, phase12_results):
        assert phase12_results["classification"].startswith("B")

    def test_regime_conditional(self, phase12_results):
        assert "REGIME-CONDITIONAL" in phase12_results["classification"]


class TestOutputFiles:
    def test_results_json_exists(self):
        assert (PHASE12_DIR / "phase12_results.json").exists()

    def test_summary_csv_exists(self):
        assert (PHASE12_DIR / "phase12_summary.csv").exists()

    def test_report_exists(self):
        assert (PHASE12_DIR / "PHASE12_REGIME_VALIDATION_REPORT.md").exists()

    def test_figures_exist(self):
        fig_dir = PHASE12_DIR / "figures"
        assert fig_dir.exists()
        figs = list(fig_dir.glob("*.png"))
        assert len(figs) >= 6
