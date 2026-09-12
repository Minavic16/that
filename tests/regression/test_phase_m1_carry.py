"""Regression tests for Phase M1: Cross-Sectional FX Carry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


PHASE_M1_DIR = Path("research/output/spectrum_m1_carry")


@pytest.fixture(scope="module")
def phase_m1_results():
    with open(PHASE_M1_DIR / "phase_m1_carry_results.json") as f:
        return json.load(f)


class TestSpectrumShape:
    def test_5_holding_horizons(self, phase_m1_results):
        assert len(phase_m1_results["spectrum"]) == 5

    def test_horizons_correct(self, phase_m1_results):
        expected = {"1D", "5D", "10D", "20D", "60D"}
        assert set(phase_m1_results["spectrum"].keys()) == expected


class TestHCMLDirection:
    """All HCML returns should be negative (carry fails)."""

    def test_majority_cells_negative(self, phase_m1_results):
        neg_count = sum(1 for h, c in phase_m1_results["spectrum"].items() if c["mean"] < 0)
        assert neg_count >= 3  # at least 3 of 5 negative

    def test_no_cell_large_positive(self, phase_m1_results):
        for h, c in phase_m1_results["spectrum"].items():
            assert c["mean"] < 0.001, f"{h}: {c['mean']}"  # no cell > 10 bps

    def test_60d_negative(self, phase_m1_results):
        assert phase_m1_results["spectrum"]["60D"]["mean"] < 0

    def test_10d_negative(self, phase_m1_results):
        assert phase_m1_results["spectrum"]["10D"]["mean"] < 0


class TestStatisticalInsignificance:
    def test_no_cells_significant(self, phase_m1_results):
        sig_count = sum(1 for h, c in phase_m1_results["spectrum"].items() if c["p_value"] < 0.05)
        assert sig_count == 0

    def test_avg_tstat_below_1(self, phase_m1_results):
        avg_t = phase_m1_results["stability"]["avg_abs_t_stat"]
        assert avg_t < 1.0

    def test_permutation_not_significant(self, phase_m1_results):
        perm = phase_m1_results["permutation_10D"]
        assert perm["p_value"] > 0.05


class TestMonotonicity:
    def test_avg_monotonicity_non_positive(self, phase_m1_results):
        mono = phase_m1_results["stability"]["avg_monotonicity"]
        assert mono <= 0.1  # not strongly positive

    def test_spearman_near_zero(self, phase_m1_results):
        spear = phase_m1_results["stability"]["avg_spearman_corr"]
        assert abs(spear) < 0.05


class TestTimeStability:
    def test_no_period_significant(self, phase_m1_results):
        for period, data in phase_m1_results["time_stability"]["periods"].items():
            assert data["p_value"] > 0.05, f"{period} significant: p={data['p_value']}"

    def test_years_inconsistent_sign(self, phase_m1_results):
        yby = phase_m1_results["time_stability"]["year_by_year"]
        pos_years = sum(1 for y, d in yby.items() if d["mean"] > 0)
        neg_years = sum(1 for y, d in yby.items() if d["mean"] < 0)
        # Should have both positive and negative years (inconsistent)
        assert pos_years >= 3 and neg_years >= 3


class TestKillCriterion:
    def test_fails_kill_criterion(self, phase_m1_results):
        assert phase_m1_results["stability"]["passes_kill_criterion"] is False

    def test_classification_killed(self, phase_m1_results):
        assert "KILLED" in phase_m1_results["classification"] or "NO" in phase_m1_results["classification"]


class TestOutputFiles:
    def test_results_json_exists(self):
        assert (PHASE_M1_DIR / "phase_m1_carry_results.json").exists()

    def test_spectrum_csv_exists(self):
        assert (PHASE_M1_DIR / "phase_m1_carry_spectrum.csv").exists()

    def test_report_exists(self):
        assert (PHASE_M1_DIR / "PHASE_M1_CARRY_REPORT.md").exists()

    def test_figures_exist(self):
        fig_dir = PHASE_M1_DIR / "figures"
        assert fig_dir.exists()
        figs = list(fig_dir.glob("*.png"))
        assert len(figs) >= 4
