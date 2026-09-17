"""
R2.1 Target Construction Tests
==============================

Tests for forward realized-volatility target construction.
Verifies the canonical definition: RV(t,h) = sqrt(sum(r[t+i]^2, i=1..h))

Per §C10 and §F4 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
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


class TestTargetH1:
    """Test horizon=1 target: RV(t,1) = |r[t+1]|."""

    def test_h1_equals_absolute_return(self):
        """h=1 target equals absolute next-bar log return."""
        df = generate_clean_fixture(n_bars=50)
        target = realized_volatility_forward(df["close"], horizon=1)
        log_ret = compute_log_returns(df["close"])

        # For each bar t, target[t] = |log_ret[t+1]|
        for i in range(1, len(df) - 1):
            expected = abs(log_ret.iloc[i + 1])
            actual = target.iloc[i]
            if not np.isnan(expected) and not np.isnan(actual):
                assert abs(actual - expected) < 1e-10, (
                    f"Bar {i}: expected {expected}, got {actual}"
                )

    def test_h1_hand_calculated(self):
        """h=1 target matches hand calculation."""
        close = pd.Series(
            [1.10000, 1.10110, 1.10220, 1.10050, 1.10300],
            index=pd.date_range("2026-01-01", periods=5, freq="4h", tz="UTC"),
        )
        target = realized_volatility_forward(close, horizon=1)
        log_ret = compute_log_returns(close)

        # target at bar 0 = |log_ret[1]| = |log(1.10110/1.10000)|
        expected_0 = abs(np.log(1.10110 / 1.10000))
        assert abs(target.iloc[0] - expected_0) < 1e-10

        # target at bar 1 = |log_ret[2]| = |log(1.10220/1.10110)|
        expected_1 = abs(np.log(1.10220 / 1.10110))
        assert abs(target.iloc[1] - expected_1) < 1e-10


class TestTargetH3:
    """Test horizon=3 target: RV(t,3) = sqrt(r[t+1]^2 + r[t+2]^2 + r[t+3]^2)."""

    def test_h3_hand_calculated(self):
        """h=3 target matches hand calculation."""
        close = pd.Series(
            [1.10000, 1.10110, 1.10220, 1.10050, 1.10300, 1.10150, 1.10400],
            index=pd.date_range("2026-01-01", periods=7, freq="4h", tz="UTC"),
        )
        target = realized_volatility_forward(close, horizon=3)
        log_ret = compute_log_returns(close)

        # target at bar 0 uses returns at bars 1, 2, 3
        r1 = log_ret.iloc[1]
        r2 = log_ret.iloc[2]
        r3 = log_ret.iloc[3]
        expected = np.sqrt(r1**2 + r2**2 + r3**2)
        assert abs(target.iloc[0] - expected) < 1e-10

    def test_h3_not_sample_std(self):
        """h=3 target is NOT sample standard deviation."""
        close = pd.Series(
            [1.10000, 1.10110, 1.10220, 1.10050, 1.10300],
            index=pd.date_range("2026-01-01", periods=5, freq="4h", tz="UTC"),
        )
        target = realized_volatility_forward(close, horizon=3)
        log_ret = compute_log_returns(close)

        # Sample std would be different
        sample_std = log_ret.iloc[1:4].std()
        our_target = target.iloc[0]

        # They should NOT be equal
        assert abs(our_target - sample_std) > 1e-6, (
            "Target should be sqrt(sum(r^2)), not sample std"
        )


class TestTargetH6:
    """Test horizon=6 target."""

    def test_h6_uses_next_6_returns(self):
        """h=6 target uses next 6 returns."""
        df = generate_clean_fixture(n_bars=50)
        target = realized_volatility_forward(df["close"], horizon=6)
        log_ret = compute_log_returns(df["close"])

        # Verify first non-NaN target
        first_valid = target.first_valid_index()
        idx = df.index.get_loc(first_valid)
        returns_window = log_ret.iloc[idx + 1: idx + 7]
        expected = np.sqrt((returns_window ** 2).sum())
        assert abs(target.loc[first_valid] - expected) < 1e-10


class TestTargetH12:
    """Test horizon=12 target."""

    def test_h12_uses_next_12_returns(self):
        """h=12 target uses next 12 returns."""
        df = generate_clean_fixture(n_bars=50)
        target = realized_volatility_forward(df["close"], horizon=12)
        log_ret = compute_log_returns(df["close"])

        first_valid = target.first_valid_index()
        idx = df.index.get_loc(first_valid)
        returns_window = log_ret.iloc[idx + 1: idx + 13]
        expected = np.sqrt((returns_window ** 2).sum())
        assert abs(target.loc[first_valid] - expected) < 1e-10


class TestInsufficientFutureData:
    """Test that insufficient future observations produce NaN."""

    def test_last_h_bars_are_nan(self):
        """Last `horizon` bars have NaN target."""
        df = generate_clean_fixture(n_bars=50)
        for h in [1, 3, 6, 12]:
            target = realized_volatility_forward(df["close"], horizon=h)
            # Last h values should be NaN
            assert target.iloc[-h:].isna().all(), (
                f"Last {h} bars should be NaN for horizon={h}"
            )

    def test_nan_count_matches_horizon(self):
        """Number of NaN values equals horizon."""
        df = generate_clean_fixture(n_bars=50)
        for h in [1, 3, 6, 12]:
            target = realized_volatility_forward(df["close"], horizon=h)
            nan_count = target.isna().sum()
            # NaN count >= horizon (first return is also NaN, plus forward window)
            assert nan_count >= h, (
                f"Expected >= {h} NaN values for horizon={h}, got {nan_count}"
            )


class TestNoLookahead:
    """Test that target construction has no lookahead bias."""

    def test_perturbation_test(self):
        """Modifying a future observation does not change past targets."""
        df = generate_clean_fixture(n_bars=50)
        close_original = df["close"].copy()
        target_original = realized_volatility_forward(close_original, horizon=3)

        # Modify a future observation (bar 40)
        close_modified = close_original.copy()
        close_modified.iloc[40] = close_modified.iloc[40] * 1.01

        target_modified = realized_volatility_forward(close_modified, horizon=3)

        # Targets before bar 37 (= 40 - 3) should be unchanged
        for i in range(37):
            orig = target_original.iloc[i]
            mod = target_modified.iloc[i]
            if not np.isnan(orig) and not np.isnan(mod):
                assert abs(orig - mod) < 1e-15, (
                    f"Bar {i}: target changed when future was modified"
                )


class TestRealizedVariance:
    """Test realized variance (not volatility)."""

    def test_variance_is_squared_volatility(self):
        """Realized variance = realized_volatility^2."""
        df = generate_clean_fixture(n_bars=50)
        vol = realized_volatility_forward(df["close"], horizon=3)
        var = realized_variance_forward(df["close"], horizon=3)

        # Where both are non-NaN
        valid = vol.notna() & var.notna()
        assert (var[valid] - vol[valid] ** 2).abs().max() < 1e-10


class TestNotSampleStd:
    """Test that target is NOT sample standard deviation."""

    def test_h1_not_std(self):
        """h=1 target is not sample std (which would be NaN or 0)."""
        df = generate_clean_fixture(n_bars=50)
        target = realized_volatility_forward(df["close"], horizon=1)

        # h=1 target should be non-zero for most bars
        valid = target.dropna()
        assert (valid > 0).all(), "h=1 target should be positive (|r|)"

        # Sample std with 1 observation and ddof=1 would be NaN
        # Sample std with 1 observation and ddof=0 would be 0
        # Our target is |r| which is > 0
