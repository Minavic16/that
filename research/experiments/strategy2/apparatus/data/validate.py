"""
R2.1 Data Validation
====================

Gate 1 data integrity checks for canonical 4H OHLCV data.
Validates timestamps, schema, gaps, duplicates, and price constraints.

Per §C of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    severity: str = "ERROR"  # ERROR or WARNING

    def __repr__(self) -> str:
        status = "PASS" if self.passed else f"FAIL({self.severity})"
        return f"{status}: {self.name} — {self.message}"


def validate_timestamps(df: pd.DataFrame) -> ValidationResult:
    """Check that index is DatetimeIndex with UTC timezone."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return ValidationResult("timestamps_type", False, f"Index is {type(df.index)}, expected DatetimeIndex")
    if df.index.tz is None:
        return ValidationResult("timestamps_utc", False, "Index has no timezone, expected UTC")
    if str(df.index.tz) != "UTC":
        return ValidationResult("timestamps_utc", False, f"Index tz is {df.index.tz}, expected UTC")
    return ValidationResult("timestamps", True, "Timestamps are UTC DatetimeIndex")


def validate_4h_alignment(df: pd.DataFrame) -> ValidationResult:
    """Check that timestamps align to 4H bar boundaries (00, 04, 08, 12, 16, 20 UTC)."""
    expected_hours = {0, 4, 8, 12, 16, 20}
    actual_hours = set(df.index.hour.unique())
    invalid_hours = actual_hours - expected_hours
    if invalid_hours:
        return ValidationResult(
            "4h_alignment", False,
            f"Unexpected hours: {sorted(invalid_hours)}. Expected: {sorted(expected_hours)}"
        )
    return ValidationResult("4h_alignment", True, "All timestamps align to 4H boundaries")


def validate_duplicates(df: pd.DataFrame) -> ValidationResult:
    """Check for duplicate timestamps. Duplicates are validation failures."""
    dup_count = df.index.duplicated().sum()
    if dup_count > 0:
        return ValidationResult(
            "duplicates", False,
            f"{dup_count} duplicate timestamp(s) found. Status: NOT_VALIDATED"
        )
    return ValidationResult("duplicates", True, "No duplicate timestamps")


def validate_prices(df: pd.DataFrame) -> ValidationResult:
    """Check OHLC price constraints: H >= L, H >= O, H >= C, L <= O, L <= C, all > 0."""
    issues = []

    # Check positive prices
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            non_positive = (df[col] <= 0).sum()
            if non_positive > 0:
                issues.append(f"{col}: {non_positive} non-positive value(s)")

    # Check OHLC consistency
    if all(c in df.columns for c in ["open", "high", "low", "close"]):
        h_ge_l = (df["high"] < df["low"]).sum()
        if h_ge_l > 0:
            issues.append(f"high < low in {h_ge_l} bar(s)")

        h_ge_o = (df["high"] < df["open"]).sum()
        if h_ge_o > 0:
            issues.append(f"high < open in {h_ge_o} bar(s)")

        h_ge_c = (df["high"] < df["close"]).sum()
        if h_ge_c > 0:
            issues.append(f"high < close in {h_ge_c} bar(s)")

        l_le_o = (df["low"] > df["open"]).sum()
        if l_le_o > 0:
            issues.append(f"low > open in {l_le_o} bar(s)")

        l_le_c = (df["low"] > df["close"]).sum()
        if l_le_c > 0:
            issues.append(f"low > close in {l_le_c} bar(s)")

    if issues:
        return ValidationResult("prices", False, "; ".join(issues))
    return ValidationResult("prices", True, "All OHLC prices valid")


def validate_volume_spread(df: pd.DataFrame) -> ValidationResult:
    """Check volume >= 0 and spread >= 0 where present."""
    issues = []
    if "volume" in df.columns:
        neg_volume = (df["volume"] < 0).sum()
        if neg_volume > 0:
            issues.append(f"volume: {neg_volume} negative value(s)")
    if "spread" in df.columns:
        neg_spread = (df["spread"] < 0).sum()
        if neg_spread > 0:
            issues.append(f"spread: {neg_spread} negative value(s)")
    if issues:
        return ValidationResult("volume_spread", False, "; ".join(issues))
    return ValidationResult("volume_spread", True, "Volume and spread non-negative")


def classify_gap(hours: float) -> str:
    """Classify a gap by its duration in hours.

    Per §C4 of the specification:
    - Weekend gap (44-76 hours): Expected, informational
    - Holiday gap (76-120 hours): Expected, informational
    - Runner gap (< 44 hours): Informational
    - Data corruption gap (> 120 hours): Flagged for investigation
    """
    if hours < 44:
        return "runner_gap"
    elif hours <= 76:
        return "weekend_gap"
    elif hours <= 120:
        return "holiday_gap"
    else:
        return "corruption_gap"


def detect_gaps(df: pd.DataFrame) -> list[dict]:
    """Detect and classify gaps in the timestamp sequence.

    Returns list of dicts with: timestamp, expected_timestamp, gap_hours, gap_type, is_weekend.
    """
    if len(df) < 2:
        return []

    gaps = []
    timestamps = df.index.sort_values()

    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        gap_hours = diff.total_seconds() / 3600

        if gap_hours > 4:  # More than one bar
            # Check if this is a weekend gap
            prev = timestamps[i - 1]
            curr = timestamps[i]
            is_weekend = (
                (prev.weekday() == 4 and prev.hour == 20) and  # Friday 20:00
                (curr.weekday() == 6 and curr.hour >= 18)      # Sunday >= 18:00
            )

            # Expected next timestamp
            expected = prev + pd.Timedelta(hours=4)

            gap_type = classify_gap(gap_hours)

            gaps.append({
                "timestamp": curr,
                "previous_timestamp": prev,
                "expected_timestamp": expected,
                "gap_hours": gap_hours,
                "gap_type": gap_type,
                "is_weekend": is_weekend,
            })

    return gaps


def validate_gaps(df: pd.DataFrame) -> ValidationResult:
    """Validate gap structure: detect gaps, classify them, flag corruption."""
    gaps = detect_gaps(df)

    corruption_gaps = [g for g in gaps if g["gap_type"] == "corruption_gap"]
    if corruption_gaps:
        return ValidationResult(
            "gaps", False,
            f"{len(corruption_gaps)} corruption gap(s) detected (>120 hours)",
            severity="ERROR"
        )

    weekend_gaps = [g for g in gaps if g["gap_type"] == "weekend_gap"]
    holiday_gaps = [g for g in gaps if g["gap_type"] == "holiday_gap"]
    runner_gaps = [g for g in gaps if g["gap_type"] == "runner_gap"]

    return ValidationResult(
        "gaps", True,
        f"Gaps detected: {len(weekend_gaps)} weekend, {len(holiday_gaps)} holiday, "
        f"{len(runner_gaps)} runner"
    )


def validate_monotonic_index(df: pd.DataFrame) -> ValidationResult:
    """Check that the index is monotonically increasing."""
    if not df.index.is_monotonic_increasing:
        return ValidationResult("monotonic_index", False, "Index is not monotonically increasing")
    return ValidationResult("monotonic_index", True, "Index is monotonically increasing")


def run_all_validations(df: pd.DataFrame) -> list[ValidationResult]:
    """Run all Gate 1 validation checks.

    Returns list of ValidationResult objects.
    The dataset passes Gate 1 only if ALL checks pass.
    """
    results = [
        validate_timestamps(df),
        validate_4h_alignment(df),
        validate_monotonic_index(df),
        validate_duplicates(df),
        validate_prices(df),
        validate_volume_spread(df),
        validate_gaps(df),
    ]
    return results


def gate1_passed(df: pd.DataFrame) -> bool:
    """Check if the dataset passes Gate 1 (all validations pass)."""
    results = run_all_validations(df)
    return all(r.passed for r in results)
