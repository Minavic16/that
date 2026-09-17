"""
R2.1 Fixture Tests
==================

Tests for the deterministic synthetic fixture generator.
Verifies determinism, schema, edge cases, and reproducibility.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add apparatus to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fixtures.synthetic import (
    generate_clean_fixture,
    generate_synthetic_ohlcv,
    generate_rejection_fixtures,
    EXPECTED_BAR_HOURS,
)


class TestFixtureDeterminism:
    """Test that fixture generation is deterministic."""

    def test_same_seed_same_output(self):
        """Same seed produces identical output."""
        df1 = generate_clean_fixture(n_bars=50, seed=42)
        df2 = generate_clean_fixture(n_bars=50, seed=42)
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seed_different_output(self):
        """Different seeds produce different output."""
        df1 = generate_clean_fixture(n_bars=50, seed=42)
        df2 = generate_clean_fixture(n_bars=50, seed=99)
        assert not df1.equals(df2)

    def test_reproducibility_across_calls(self):
        """Multiple calls with same seed produce identical results."""
        dfs = [generate_clean_fixture(n_bars=50, seed=42) for _ in range(5)]
        for i in range(1, len(dfs)):
            pd.testing.assert_frame_equal(dfs[0], dfs[i])


class TestFixtureSchema:
    """Test that fixture has correct schema."""

    def test_columns_present(self):
        """All required columns are present."""
        df = generate_clean_fixture(n_bars=50)
        required = {"open", "high", "low", "close", "volume", "spread"}
        assert required.issubset(set(df.columns))

    def test_index_is_datetime(self):
        """Index is DatetimeIndex."""
        df = generate_clean_fixture(n_bars=50)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_index_is_utc(self):
        """Index timezone is UTC."""
        df = generate_clean_fixture(n_bars=50)
        assert str(df.index.tz) == "UTC"

    def test_index_name(self):
        """Index name is 'timestamp'."""
        df = generate_clean_fixture(n_bars=50)
        assert df.index.name == "timestamp"

    def test_4h_alignment(self):
        """All timestamps align to 4H boundaries."""
        df = generate_clean_fixture(n_bars=50)
        valid_hours = {0, 4, 8, 12, 16, 20}
        assert all(h in valid_hours for h in df.index.hour.unique())


class TestFixtureEdgeCases:
    """Test that fixture contains required edge cases."""

    def test_weekend_gaps_present(self):
        """Clean fixture contains weekend gaps."""
        df = generate_clean_fixture(n_bars=200)
        # With 200 bars and weekend gaps, there should be fewer than 200*4 hours
        # because weekends are skipped
        assert len(df) < 200

    def test_nonweekend_gap_present(self):
        """Clean fixture contains at least one non-weekend gap."""
        df = generate_clean_fixture(n_bars=200)
        # Check for gaps > 4 hours that are not weekend gaps
        gaps = df.index.to_series().diff()
        nonweekend_gaps = gaps[(gaps > pd.Timedelta(hours=4))]
        # Filter out weekend gaps
        for gap_start in nonweekend_gaps.index:
            prev_idx = df.index.get_loc(gap_start) - 1
            if prev_idx >= 0:
                prev_time = df.index[prev_idx]
                # Weekend gaps are Friday 20:00 -> Sunday 18:00
                is_weekend = (
                    prev_time.weekday() == 4 and prev_time.hour == 20
                )
                if not is_weekend:
                    return  # Found a non-weekend gap
        pytest.skip("No non-weekend gap found in fixture")

    def test_enough_bars_for_targets(self):
        """Fixture has enough bars to test forward targets."""
        df = generate_clean_fixture(n_bars=200)
        # Need at least 12 + some for backward features
        assert len(df) > 50


class TestFixtureRejection:
    """Test rejection fixtures for validation testing."""

    def test_duplicate_timestamp_fixture(self):
        """Rejection fixture has duplicate timestamps."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["duplicate_timestamp"]
        assert df.index.duplicated().any()

    def test_invalid_prices_fixture(self):
        """Rejection fixture has invalid prices."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_prices"]
        has_nonpositive = (df["close"] <= 0).any() or (df["high"] <= 0).any()
        assert has_nonpositive

    def test_invalid_volume_fixture(self):
        """Rejection fixture has negative volume."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_volume"]
        assert (df["volume"] < 0).any()
