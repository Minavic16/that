"""Canonical OHLCV validation.

Unified Gate-1-style checks for `OHLCVFrame`: timestamps (UTC +
monotonic), 4H alignment, schema, duplicates, prices, volume/spread,
and gap classification.

Rules follow the R2.1 data contract (§C): duplicates are validation
failures (dataset does not proceed with unresolved duplicates);
weekend/holiday/runner gaps are informational; corruption gaps
(>120h) fail validation.

Self-contained: no imports from `core/`, `production/`, or
R2.1-specific `apparatus/` code.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nestquant.research.shared.data.schema import (
    FOUR_H_BAR_HOURS,
    FOUR_H_BAR_INTERVAL_HOURS,
    OHLCV_COLUMNS,
    OHLCV_REQUIRED_COLUMNS,
)


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
    """Check UTC DatetimeIndex and monotonic increase."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return ValidationResult(
            "timestamps_type", False, f"Index is {type(df.index)}, expected DatetimeIndex"
        )
    if df.index.tz is None:
        return ValidationResult("timestamps_utc", False, "Index has no timezone, expected UTC")
    if str(df.index.tz) != "UTC":
        return ValidationResult(
            "timestamps_utc", False, f"Index tz is {df.index.tz}, expected UTC"
        )
    if not df.index.is_monotonic_increasing:
        return ValidationResult(
            "timestamps_monotonic", False, "Index is not monotonically increasing"
        )
    return ValidationResult("timestamps", True, "Timestamps are monotonic UTC DatetimeIndex")


def validate_4h_alignment(df: pd.DataFrame) -> ValidationResult:
    """Check timestamps align to 4H bar boundaries (00/04/08/12/16/20 UTC)."""
    if not isinstance(df.index, pd.DatetimeIndex) or len(df) == 0:
        return ValidationResult("4h_alignment", False, "No DatetimeIndex to check alignment on")
    invalid_hours = sorted(set(df.index.hour.unique()) - FOUR_H_BAR_HOURS)
    if invalid_hours:
        return ValidationResult(
            "4h_alignment",
            False,
            f"Unexpected hours: {invalid_hours}. Expected: {sorted(FOUR_H_BAR_HOURS)}",
        )
    return ValidationResult("4h_alignment", True, "All timestamps align to 4H boundaries")


def validate_schema(df: pd.DataFrame) -> ValidationResult:
    """Check required columns are present with numeric types."""
    missing = [c for c in OHLCV_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return ValidationResult("schema", False, f"Missing required columns: {missing}")
    non_numeric = [
        c
        for c in OHLCV_COLUMNS
        if c in df.columns and not pd.api.types.is_numeric_dtype(df[c])
    ]
    if non_numeric:
        return ValidationResult(
            "schema", False, f"Non-numeric dtype in columns: {non_numeric}"
        )
    return ValidationResult("schema", True, "Required columns present with numeric dtypes")


def validate_duplicates(df: pd.DataFrame) -> ValidationResult:
    """Check for duplicate timestamps. Duplicates are validation failures."""
    dup_count = int(df.index.duplicated().sum())
    if dup_count > 0:
        return ValidationResult(
            "duplicates",
            False,
            f"{dup_count} duplicate timestamp(s) found. Status: NOT_VALIDATED",
        )
    return ValidationResult("duplicates", True, "No duplicate timestamps")


def validate_prices(df: pd.DataFrame) -> ValidationResult:
    """Check OHLC constraints: all > 0; H>=L, H>=O, H>=C, L<=O, L<=C."""
    issues: list[str] = []
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            n_bad = int((df[col] <= 0).sum())
            if n_bad > 0:
                issues.append(f"{col}: {n_bad} non-positive value(s)")
    if all(c in df.columns for c in ("open", "high", "low", "close")):
        checks = [
            (df["high"] < df["low"], "high < low"),
            (df["high"] < df["open"], "high < open"),
            (df["high"] < df["close"], "high < close"),
            (df["low"] > df["open"], "low > open"),
            (df["low"] > df["close"], "low > close"),
        ]
        for mask, label in checks:
            n_bad = int(mask.sum())
            if n_bad > 0:
                issues.append(f"{label} in {n_bad} bar(s)")
    if issues:
        return ValidationResult("prices", False, "; ".join(issues))
    return ValidationResult("prices", True, "All OHLC prices valid")


def validate_volume_spread(df: pd.DataFrame) -> ValidationResult:
    """Check volume >= 0 and spread >= 0 where present."""
    issues: list[str] = []
    if "volume" in df.columns:
        n_bad = int((df["volume"] < 0).sum())
        if n_bad > 0:
            issues.append(f"volume: {n_bad} negative value(s)")
    if "spread" in df.columns:
        n_bad = int((df["spread"] < 0).sum())
        if n_bad > 0:
            issues.append(f"spread: {n_bad} negative value(s)")
    if issues:
        return ValidationResult("volume_spread", False, "; ".join(issues))
    return ValidationResult("volume_spread", True, "Volume and spread non-negative")


def classify_gap(hours: float) -> str:
    """Classify a gap by duration in hours.

    - runner_gap: < 44h (informational)
    - weekend_gap: 44–76h (expected, informational)
    - holiday_gap: 76–120h (expected, informational)
    - corruption_gap: > 120h (flagged for investigation)
    """
    if hours < 44:
        return "runner_gap"
    if hours <= 76:
        return "weekend_gap"
    if hours <= 120:
        return "holiday_gap"
    return "corruption_gap"


def detect_gaps(df: pd.DataFrame) -> list[dict]:
    """Detect and classify gaps in the timestamp sequence.

    Returns dicts with previous_timestamp, timestamp, gap_hours, gap_type.
    """
    if len(df) < 2 or not isinstance(df.index, pd.DatetimeIndex):
        return []
    gaps: list[dict] = []
    timestamps = df.index.sort_values()
    for i in range(1, len(timestamps)):
        gap_hours = (timestamps[i] - timestamps[i - 1]).total_seconds() / 3600
        if gap_hours > FOUR_H_BAR_INTERVAL_HOURS:
            gaps.append(
                {
                    "previous_timestamp": timestamps[i - 1],
                    "timestamp": timestamps[i],
                    "gap_hours": gap_hours,
                    "gap_type": classify_gap(gap_hours),
                }
            )
    return gaps


def validate_gaps(df: pd.DataFrame) -> ValidationResult:
    """Validate gap structure. Only corruption gaps fail validation."""
    gaps = detect_gaps(df)
    corruption = [g for g in gaps if g["gap_type"] == "corruption_gap"]
    if corruption:
        return ValidationResult(
            "gaps", False, f"{len(corruption)} corruption gap(s) detected (>120 hours)"
        )
    counts = {"weekend_gap": 0, "holiday_gap": 0, "runner_gap": 0}
    for g in gaps:
        counts[g["gap_type"]] += 1
    return ValidationResult(
        "gaps",
        True,
        f"Gaps detected: {counts['weekend_gap']} weekend, "
        f"{counts['holiday_gap']} holiday, {counts['runner_gap']} runner",
    )


def validate_ohlcv(df: pd.DataFrame) -> list[ValidationResult]:
    """Run all canonical OHLCV validation checks.

    Returns one ValidationResult per check. The frame passes only if
    ALL checks pass (see `validation_passed`).
    """
    return [
        validate_timestamps(df),
        validate_4h_alignment(df),
        validate_schema(df),
        validate_duplicates(df),
        validate_prices(df),
        validate_volume_spread(df),
        validate_gaps(df),
    ]


def validation_passed(results: list[ValidationResult]) -> bool:
    """Check that all validation results passed."""
    return all(r.passed for r in results)
