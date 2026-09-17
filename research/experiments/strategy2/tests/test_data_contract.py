"""
R2.1 Data Contract Tests
========================

Tests for data validation against the approved contract.
Covers timestamps, OHLCV schema, duplicates, prices, gaps.

Per §C of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from apparatus.data.validate import (
    validate_timestamps,
    validate_4h_alignment,
    validate_duplicates,
    validate_prices,
    validate_volume_spread,
    validate_gaps,
    validate_monotonic_index,
    run_all_validations,
    gate1_passed,
    classify_gap,
    detect_gaps,
)
from fixtures.synthetic import generate_clean_fixture, generate_rejection_fixtures


class TestTimestampValidation:
    """Test timestamp validation."""

    def test_valid_utc_timestamps(self):
        """Valid UTC timestamps pass."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_timestamps(df)
        assert result.passed

    def test_non_datetime_index_fails(self):
        """Non-DatetimeIndex fails."""
        df = pd.DataFrame({"close": [1.0, 2.0]}, index=[0, 1])
        result = validate_timestamps(df)
        assert not result.passed

    def test_non_utc_timezone_fails(self):
        """Non-UTC timezone fails."""
        df = generate_clean_fixture(n_bars=50)
        # Use a fixed-offset timezone instead of US/Eastern (requires tzdata)
        import datetime as dt
        df.index = df.index.tz_convert(dt.timezone(dt.timedelta(hours=5)))
        result = validate_timestamps(df)
        assert not result.passed


class Test4HAlignment:
    """Test 4H bar alignment."""

    def test_valid_4h_alignment(self):
        """Valid 4H timestamps pass."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_4h_alignment(df)
        assert result.passed

    def test_invalid_hour_fails(self):
        """Timestamps with invalid hours fail."""
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-01-01 01:00:00", tz="UTC"),
            pd.Timestamp("2026-01-01 05:00:00", tz="UTC"),
        ])
        df = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
        result = validate_4h_alignment(df)
        assert not result.passed


class TestDuplicateValidation:
    """Test duplicate timestamp rejection."""

    def test_no_duplicates_pass(self):
        """No duplicates passes."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_duplicates(df)
        assert result.passed

    def test_duplicates_fail(self):
        """Duplicate timestamps fail."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["duplicate_timestamp"]
        result = validate_duplicates(df)
        assert not result.passed


class TestPriceValidation:
    """Test OHLC price constraints."""

    def test_valid_prices_pass(self):
        """Valid OHLC prices pass."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_prices(df)
        assert result.passed

    def test_negative_close_fails(self):
        """Negative close price fails."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_prices"]
        result = validate_prices(df)
        assert not result.passed

    def test_zero_price_fails(self):
        """Zero price fails."""
        df = generate_clean_fixture(n_bars=50)
        df.iloc[0, df.columns.get_loc("close")] = 0.0
        result = validate_prices(df)
        assert not result.passed


class TestVolumeSpreadValidation:
    """Test volume and spread constraints."""

    def test_valid_volume_spread_pass(self):
        """Valid volume and spread pass."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_volume_spread(df)
        assert result.passed

    def test_negative_volume_fails(self):
        """Negative volume fails."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_volume"]
        result = validate_volume_spread(df)
        assert not result.passed


class TestGapDetection:
    """Test gap detection and classification."""

    def test_gap_classification_weekend(self):
        """Weekend gaps are classified correctly."""
        # 48 hours = Friday 20:00 to Sunday 20:00 = weekend gap
        assert classify_gap(48) == "weekend_gap"

    def test_gap_classification_runner(self):
        """Runner gaps are classified correctly."""
        assert classify_gap(8) == "runner_gap"

    def test_gap_classification_holiday(self):
        """Holiday gaps are classified correctly."""
        assert classify_gap(96) == "holiday_gap"

    def test_gap_classification_corruption(self):
        """Corruption gaps are classified correctly."""
        assert classify_gap(150) == "corruption_gap"

    def test_detect_gaps_clean_fixture(self):
        """Clean fixture has expected gaps."""
        df = generate_clean_fixture(n_bars=200)
        gaps = detect_gaps(df)
        # Should have weekend gaps and one non-weekend gap
        assert len(gaps) > 0

    def test_no_corruption_gaps_in_clean_fixture(self):
        """Clean fixture has no corruption gaps."""
        df = generate_clean_fixture(n_bars=200)
        gaps = detect_gaps(df)
        corruption = [g for g in gaps if g["gap_type"] == "corruption_gap"]
        assert len(corruption) == 0


class TestMonotonicIndex:
    """Test monotonic index validation."""

    def test_monotonic_pass(self):
        """Monotonic index passes."""
        df = generate_clean_fixture(n_bars=50)
        result = validate_monotonic_index(df)
        assert result.passed

    def test_non_monotonic_fail(self):
        """Non-monotonic index fails."""
        df = generate_clean_fixture(n_bars=50)
        df = df.iloc[::-1]  # Reverse
        result = validate_monotonic_index(df)
        assert not result.passed


class TestGate1:
    """Test Gate 1 overall validation."""

    def test_clean_fixture_passes_gate1(self):
        """Clean fixture passes all Gate 1 checks."""
        df = generate_clean_fixture(n_bars=100)
        results = run_all_validations(df)
        for r in results:
            assert r.passed, f"Gate 1 failed: {r}"
        assert gate1_passed(df)

    def test_duplicate_fixture_fails_gate1(self):
        """Fixture with duplicates fails Gate 1."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["duplicate_timestamp"]
        assert not gate1_passed(df)

    def test_invalid_price_fixture_fails_gate1(self):
        """Fixture with invalid prices fails Gate 1."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_prices"]
        assert not gate1_passed(df)

    def test_invalid_volume_fixture_fails_gate1(self):
        """Fixture with invalid volume fails Gate 1."""
        fixtures = generate_rejection_fixtures()
        df = fixtures["invalid_volume"]
        assert not gate1_passed(df)
