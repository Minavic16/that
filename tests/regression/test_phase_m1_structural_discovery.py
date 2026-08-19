"""Regression tests for Phase M1: Structural Discovery — FX Currency Momentum."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PHASE_M1_DIR = Path("/root/nestquant/research_data/phase_m1")


@pytest.fixture(scope="module")
def phase_m1_results():
    with open(PHASE_M1_DIR / "phase_m1_results.json") as f:
        return json.load(f)


class TestSpectrumShape:
    def test_8_formation_horizons(self, phase_m1_results):
        assert len(phase_m1_results["spectrum"]) == 8

    def test_6_holding_horizons(self, phase_m1_results):
        first_formation = list(phase_m1_results["spectrum"].values())[0]
        assert len(first_formation) == 6

    def test_48_total_cells(self, phase_m1_results):
        total = sum(len(v) for v in phase_m1_results["spectrum"].values())
        assert total == 48


class TestMomentumDirection:
    """The core finding: ALL cells should be NEGATIVE (reversal, not momentum)."""

    def test_majority_cells_negative(self, phase_m1_results):
        neg_count = 0
        for f_key, holdings in phase_m1_results["spectrum"].items():
            for h_key, cell in holdings.items():
                if cell["mean"] < 0:
                    neg_count += 1
        assert neg_count >= 40  # at least 40 of 48 cells negative

    def test_no_cell_positive_large(self, phase_m1_results):
        """No cell should have mean > +0.0001 (i.e., no momentum)."""
        for f_key, holdings in phase_m1_results["spectrum"].items():
            for h_key, cell in holdings.items():
                assert cell["mean"] < 0.0001, f"{f_key}->{h_key}: {cell['mean']}"

    def test_short_horizon_strongly_negative(self, phase_m1_results):
        """1D formation should have strongly negative WML."""
        cell_1d_1d = phase_m1_results["spectrum"]["1D"]["1D"]
        assert cell_1d_1d["mean"] < -0.00005


class TestStatisticalSignificance:
    def test_majority_cells_significant(self, phase_m1_results):
        sig_count = 0
        for f_key, holdings in phase_m1_results["spectrum"].items():
            for h_key, cell in holdings.items():
                if cell["p_value"] < 0.05:
                    sig_count += 1
        assert sig_count >= 20  # at least 20 of 48 significant

    def test_short_horizon_highly_significant(self, phase_m1_results):
        cell_1d_1d = phase_m1_results["spectrum"]["1D"]["1D"]
        assert cell_1d_1d["p_value"] < 0.001

    def test_t_stats_negative(self, phase_m1_results):
        for f_key, holdings in phase_m1_results["spectrum"].items():
            for h_key, cell in holdings.items():
                if abs(cell["t_stat"]) > 1.0:
                    assert cell["t_stat"] < 0, f"{f_key}->{h_key}: t={cell['t_stat']}"


class TestDecileMonotonicity:
    def test_avg_monotonicity_negative(self, phase_m1_results):
        stab = phase_m1_results["stability"]
        assert stab["avg_decile_monotonicity"] < -0.5

    def test_monotonicity_near_perfect(self, phase_m1_results):
        stab = phase_m1_results["stability"]
        assert stab["avg_decile_monotonicity"] < -0.7


class TestPermutation:
    def test_observed_negative(self, phase_m1_results):
        perm = phase_m1_results["permutation_20D_10D"]
        assert perm["observed_mean"] < 0

    def test_significant(self, phase_m1_results):
        perm = phase_m1_results["permutation_20D_10D"]
        assert perm["p_value"] < 0.05


class TestStability:
    def test_sign_consistency_high(self, phase_m1_results):
        stab = phase_m1_results["stability"]
        assert stab["sign_consistency_pct"] > 90

    def test_kill_criterion_fails(self, phase_m1_results):
        stab = phase_m1_results["stability"]
        assert stab["passes_kill_criterion"] is False


class TestClassification:
    def test_no_structure(self, phase_m1_results):
        assert "NO" in phase_m1_results["classification"] or "KILL" in phase_m1_results["classification"]


class TestOutputFiles:
    def test_results_json_exists(self):
        assert (PHASE_M1_DIR / "phase_m1_results.json").exists()

    def test_spectrum_csv_exists(self):
        assert (PHASE_M1_DIR / "phase_m1_spectrum.csv").exists()

    def test_report_exists(self):
        assert (PHASE_M1_DIR / "PHASE_M1_STRUCTURAL_DISCOVERY_REPORT.md").exists()

    def test_figures_exist(self):
        fig_dir = PHASE_M1_DIR / "figures"
        assert fig_dir.exists()
        figs = list(fig_dir.glob("*.png"))
        assert len(figs) >= 4
