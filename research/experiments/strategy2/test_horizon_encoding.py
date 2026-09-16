"""
R2.1 Horizon Encoding Regression Test
======================================

Verifies that the active HORIZONS in R2.1_phase1_experiment.py match
the approved R2.1 experiment design (R2.1_EXPERIMENT_DESIGN.md lines 48-53).

This test catches accidental horizon drift in the real experiment config.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _load_experiment_hizons() -> list[int]:
    """Import HORIZONS from the active R2.1 experiment config.

    Uses importlib to load the module and extract the HORIZONS constant.
    This tests the REAL config, not a test-local copy.
    """
    experiment_dir = Path(__file__).parent
    module_path = experiment_dir / "R2.1_phase1_experiment.py"

    if not module_path.exists():
        pytest.skip(f"Experiment file not found: {module_path}")

    # Load module without executing main()
    spec = importlib.util.spec_from_file_location(
        "r21_experiment", str(module_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["r21_experiment"] = module
    spec.loader.exec_module(module)

    return module.HORIZONS


class TestHorizonEncoding:
    """Verify R2.1 horizons match the approved experiment design."""

    def test_horizons_match_approved_spec(self):
        """HORIZONS must be [1, 3, 6, 12] per R2.1_EXPERIMENT_DESIGN.md."""
        actual = _load_experiment_hizons()
        assert actual == [1, 3, 6, 12], (
            f"HORIZONS mismatch: got {actual}, expected [1, 3, 6, 12]. "
            f"Source of truth: R2.1_EXPERIMENT_DESIGN.md lines 48-53"
        )

    def test_horizons_not_legacy_values(self):
        """Legacy horizons [6, 12, 18, 24] must NOT be the active config."""
        actual = _load_experiment_hizons()
        assert actual != [6, 12, 18, 24], (
            "HORIZONS still contains legacy values [6, 12, 18, 24]. "
            "Should be [1, 3, 6, 12] per approved spec."
        )

    def test_no_legacy_horizon_18(self):
        """Horizon 18 (72h) is not in the approved spec."""
        actual = _load_experiment_hizons()
        assert 18 not in actual, (
            f"Legacy horizon 18 (72h) found in HORIZONS={actual}. "
            f"Approved spec does not include 72h."
        )

    def test_no_legacy_horizon_24(self):
        """Horizon 24 (96h) is not in the approved spec."""
        actual = _load_experiment_hizons()
        assert 24 not in actual, (
            f"Legacy horizon 24 (96h) found in HORIZONS={actual}. "
            f"Approved spec does not include 96h."
        )

    def test_horizons_are_sorted(self):
        """Horizons should be in ascending order."""
        actual = _load_experiment_hizons()
        assert actual == sorted(actual), (
            f"HORIZONS not sorted: {actual}"
        )

    def test_horizons_hour_mapping(self):
        """Each horizon maps to correct hours (bar * 4)."""
        actual = _load_experiment_hizons()
        expected_hours = {1: 4, 3: 12, 6: 24, 12: 48}
        for h in actual:
            assert h in expected_hours, (
                f"Horizon {h} not in approved spec mapping {expected_hours}"
            )

    def test_exactly_four_horizons(self):
        """Approved spec defines exactly 4 horizons."""
        actual = _load_experiment_hizons()
        assert len(actual) == 4, (
            f"Expected 4 horizons, got {len(actual)}: {actual}"
        )
