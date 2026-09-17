"""
R2.1 Return Construction Tests
==============================

Tests for log return computation.
Verifies correctness, causality, and hand-calculated values.

Per §C9 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from apparatus.features.returns import compute_log_returns, verify_log_return
from fixtures.synthetic import generate_clean_fixture


class TestLogReturnCorrectness:
    """Test log return correctness against hand-calculated values."""

    def test_hand_calculated_example(self):
        """Log return matches hand calculation.

        close_{t-1} = 1.10000, close_t = 1.10110
        r_t = log(1.10110 / 1.10000) = log(1.001) ≈ 0.0009995003
        """
        expected = np.log(1.10110 / 1.10000)
        assert verify_log_return(1.10110, 1.10000, expected)

    def test_log_return_formula(self):
        """Log return is log(close_t / close_{t-1})."""
        close = pd.Series([1.0, 1.01, 1.02, 1.03])
        ret = compute_log_returns(close)

        # First return is NaN
        assert np.isnan(ret.iloc[0])

        # Second return: log(1.01 / 1.0) = log(1.01) ≈ 0.00995033
        assert abs(ret.iloc[1] - np.log(1.01)) < 1e-10

        # Third return: log(1.02 / 1.01) ≈ 0.00985308
        assert abs(ret.iloc[2] - np.log(1.02 / 1.01)) < 1e-10

    def test_returns_from_fixture(self):
        """Returns from fixture are computed correctly."""
        df = generate_clean_fixture(n_bars=50)
        ret = compute_log_returns(df["close"])

        # First return is NaN
        assert np.isnan(ret.iloc[0])

        # All other returns are finite
        assert np.all(np.isfinite(ret.iloc[1:]))

        # Verify against manual calculation
        for i in range(1, min(10, len(df))):
            expected = np.log(df["close"].iloc[i] / df["close"].iloc[i - 1])
            assert abs(ret.iloc[i] - expected) < 1e-10


class TestFirstObservation:
    """Test first observation behavior."""

    def test_first_return_is_nan(self):
        """First return is NaN (no previous close)."""
        close = pd.Series([1.0, 1.01, 1.02])
        ret = compute_log_returns(close)
        assert np.isnan(ret.iloc[0])

    def test_first_return_with_fixture(self):
        """First return in fixture is NaN."""
        df = generate_clean_fixture(n_bars=50)
        ret = compute_log_returns(df["close"])
        assert np.isnan(ret.iloc[0])


class TestDeterminism:
    """Test that return computation is deterministic."""

    def test_same_input_same_output(self):
        """Same input produces same output."""
        df = generate_clean_fixture(n_bars=50)
        ret1 = compute_log_returns(df["close"])
        ret2 = compute_log_returns(df["close"])
        pd.testing.assert_series_equal(ret1, ret2)

    def test_different_input_different_output(self):
        """Different input produces different output."""
        df1 = generate_clean_fixture(n_bars=50, seed=42)
        df2 = generate_clean_fixture(n_bars=50, seed=99)
        ret1 = compute_log_returns(df1["close"])
        ret2 = compute_log_returns(df2["close"])
        assert not ret1.equals(ret2)


class TestReturnProperties:
    """Test mathematical properties of log returns."""

    def test_returns_are_finite(self):
        """All returns (except first) are finite."""
        df = generate_clean_fixture(n_bars=100)
        ret = compute_log_returns(df["close"])
        assert np.all(np.isfinite(ret.iloc[1:]))

    def test_returns_can_be_positive_or_negative(self):
        """Returns can be positive or negative."""
        df = generate_clean_fixture(n_bars=100)
        ret = compute_log_returns(df["close"])
        assert (ret.iloc[1:] > 0).any()
        assert (ret.iloc[1:] < 0).any()

    def test_returns_preserve_index(self):
        """Returns have the same index as input."""
        df = generate_clean_fixture(n_bars=50)
        ret = compute_log_returns(df["close"])
        pd.testing.assert_index_equal(ret.index, df.index)
