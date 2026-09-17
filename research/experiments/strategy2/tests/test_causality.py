"""
R2.1 Causality Tests
====================

Perturbation-based tests proving that target construction and derived
features cannot inspect future observations.

Per §D of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from apparatus.features.returns import compute_log_returns
from apparatus.features.volatility import (
    realized_volatility_forward,
    realized_variance_forward,
)
from fixtures.synthetic import generate_clean_fixture


class TestReturnsCausality:
    """Test that returns are causal (no future information)."""

    def test_returns_unaffected_by_future(self):
        """Modifying future closes does not change past returns."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        returns_original = compute_log_returns(close_original)

        # Modify a future close (bar 40)
        close_modified = close_original.copy()
        close_modified.iloc[40] = close_modified.iloc[40] * 1.01

        returns_modified = compute_log_returns(close_modified)

        # Returns before bar 39 should be identical
        for i in range(39):
            orig = returns_original.iloc[i]
            mod = returns_modified.iloc[i]
            if not np.isnan(orig) and not np.isnan(mod):
                assert orig == mod, (
                    f"Return at bar {i} changed when future was modified"
                )

    def test_returns_only_use_current_and_previous_close(self):
        """Each return uses only current and previous close."""
        close = pd.Series(
            [1.10000, 1.10110, 1.10220, 1.10050, 1.10300],
            index=pd.date_range("2026-01-01", periods=5, freq="4h", tz="UTC"),
        )
        ret = compute_log_returns(close)

        # Return at bar 2 = log(close[2] / close[1])
        expected_2 = np.log(1.10220 / 1.10110)
        assert abs(ret.iloc[2] - expected_2) < 1e-10

        # Changing close[3] should NOT change ret[2]
        close_modified = close.copy()
        close_modified.iloc[3] = 1.20000
        ret_modified = compute_log_returns(close_modified)
        assert abs(ret_modified.iloc[2] - expected_2) < 1e-10


class TestTargetCausality:
    """Test that forward targets are causal (no lookahead)."""

    def test_h1_target_unaffected_by_future(self):
        """h=1 target at bar t uses only return at t+1, not t+2."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=1)

        # Modify close at bar 30 (this affects return at bar 30)
        close_modified = close_original.copy()
        close_modified.iloc[30] = close_modified.iloc[30] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=1)

        # Target at bar 28 = |return[29]| = |log(close[29]/close[28])|
        # This should NOT change when close[30] is modified
        orig_28 = target_original.iloc[28]
        mod_28 = target_modified.iloc[28]
        if not np.isnan(orig_28) and not np.isnan(mod_28):
            assert abs(orig_28 - mod_28) < 1e-15, (
                "h=1 target at bar 28 changed when bar 30 was modified"
            )

    def test_h3_target_unaffected_by_distant_future(self):
        """h=3 target at bar t uses returns t+1..t+3, not t+4."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=3)

        # Modify close at bar 40 (affects returns at bar 40 and beyond)
        close_modified = close_original.copy()
        close_modified.iloc[40] = close_modified.iloc[40] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=3)

        # Target at bar 35 = sqrt(r[36]^2 + r[37]^2 + r[38]^2)
        # This should NOT change when bar 40 is modified
        orig_35 = target_original.iloc[35]
        mod_35 = target_modified.iloc[35]
        if not np.isnan(orig_35) and not np.isnan(mod_35):
            assert abs(orig_35 - mod_35) < 1e-15, (
                "h=3 target at bar 35 changed when bar 40 was modified"
            )

    def test_h6_target_unaffected_by_distant_future(self):
        """h=6 target at bar t uses returns t+1..t+6, not t+7."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=6)

        # Modify close at bar 45
        close_modified = close_original.copy()
        close_modified.iloc[45] = close_modified.iloc[45] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=6)

        # Target at bar 38 uses returns 39..44, should not change
        orig_38 = target_original.iloc[38]
        mod_38 = target_modified.iloc[38]
        if not np.isnan(orig_38) and not np.isnan(mod_38):
            assert abs(orig_38 - mod_38) < 1e-15

    def test_h12_target_unaffected_by_distant_future(self):
        """h=12 target at bar t uses returns t+1..t+12, not t+13."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=12)

        # Modify close at bar 48
        close_modified = close_original.copy()
        close_modified.iloc[48] = close_modified.iloc[48] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=12)

        # Target at bar 35 uses returns 36..47, should not change
        orig_35 = target_original.iloc[35]
        mod_35 = target_modified.iloc[35]
        if not np.isnan(orig_35) and not np.isnan(mod_35):
            assert abs(orig_35 - mod_35) < 1e-15


class TestVarianceCausality:
    """Test that realized variance is also causal."""

    def test_variance_unaffected_by_future(self):
        """Realized variance at bar t does not use future observations."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        var_original = realized_variance_forward(close_original, horizon=3)

        close_modified = close_original.copy()
        close_modified.iloc[40] = close_modified.iloc[40] * 1.01

        var_modified = realized_variance_forward(close_modified, horizon=3)

        # Variance at bar 35 should not change
        orig_35 = var_original.iloc[35]
        mod_35 = var_modified.iloc[35]
        if not np.isnan(orig_35) and not np.isnan(mod_35):
            assert abs(orig_35 - mod_35) < 1e-15


class TestCausalityWithPerturbation:
    """Comprehensive perturbation tests."""

    @pytest.mark.parametrize("horizon", [1, 3, 6, 12])
    def test_perturbation_at_various_horizons(self, horizon):
        """For each horizon, perturbation at bar t+horizon+5 does not affect target at bar t."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=horizon)

        # Perturb a bar well beyond the forward window
        perturb_idx = min(5 + horizon + 5, len(df) - 1)
        close_modified = close_original.copy()
        close_modified.iloc[perturb_idx] = close_modified.iloc[perturb_idx] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=horizon)

        # Target at bar 0 should not change (forward window doesn't reach perturb_idx)
        target_end_idx = horizon  # last bar used in target at bar 0
        if perturb_idx > target_end_idx:
            orig_0 = target_original.iloc[0]
            mod_0 = target_modified.iloc[0]
            if not np.isnan(orig_0) and not np.isnan(mod_0):
                assert abs(orig_0 - mod_0) < 1e-15, (
                    f"Target at bar 0 changed for horizon={horizon} "
                    f"when bar {perturb_idx} was perturbed"
                )
