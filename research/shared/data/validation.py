"""Z-Score Research Engine — Extended Data Validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    passed: bool
    details: str = ""
    count: int = 0


@dataclass
class DataValidationReport:
    """Comprehensive data validation report."""
    source: str
    filename: str
    total_bars: int
    checks: list[ValidationResult] = field(default_factory=list)
    is_valid: bool = True

    def add_check(self, check: ValidationResult) -> None:
        self.checks.append(check)
        if not check.passed:
            self.is_valid = False

    def summary(self) -> str:
        lines = [
            f"Validation Report: {self.source} / {self.filename}",
            f"Total bars: {self.total_bars}",
            f"Valid: {self.is_valid}",
            "",
            "Checks:",
        ]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{status}] {c.check_name}: {c.details}")
        return "\n".join(lines)


def validate_timestamps(df: pd.DataFrame) -> ValidationResult:
    """Check that timestamps are strictly monotonically increasing."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return ValidationResult("timestamp_type", False, "Index is not DatetimeIndex")

    is_ordered = pd.Series(df.index).is_monotonic_increasing
    return ValidationResult(
        "timestamp_order",
        is_ordered,
        "Timestamps are monotonically increasing" if is_ordered else "Timestamps are NOT ordered",
    )


def validate_duplicates(df: pd.DataFrame) -> ValidationResult:
    """Check for duplicate timestamps."""
    n_dupes = int(pd.Index(df.index).duplicated().sum())
    return ValidationResult(
        "duplicate_timestamps",
        n_dupes == 0,
        f"{n_dupes} duplicate timestamps found" if n_dupes > 0 else "No duplicates",
        n_dupes,
    )


def validate_gaps(df: pd.DataFrame, max_gap_multiplier: float = 2.0) -> ValidationResult:
    """Check for gaps in timestamp sequence."""
    if len(df) < 2:
        return ValidationResult("gap_check", True, "Too few bars to check gaps")

    diffs = np.diff(df.index.view(np.int64))
    median_gap = np.median(diffs)
    gap_threshold = median_gap * max_gap_multiplier
    n_gaps = int(np.sum(diffs > gap_threshold))

    return ValidationResult(
        "gap_check",
        n_gaps == 0,
        f"{n_gaps} gaps detected (threshold: {gap_threshold/1e9:.1f}s)" if n_gaps > 0 else "No gaps",
        n_gaps,
    )


def validate_ohlc_integrity(df: pd.DataFrame) -> ValidationResult:
    """Check OHLC relationships."""
    violations = 0
    if "high" in df.columns and "low" in df.columns:
        violations += int(np.sum(df["high"] < df["low"]))
    if "high" in df.columns and "open" in df.columns:
        violations += int(np.sum(df["high"] < df["open"]))
    if "high" in df.columns and "close" in df.columns:
        violations += int(np.sum(df["high"] < df["close"]))
    if "low" in df.columns and "open" in df.columns:
        violations += int(np.sum(df["low"] > df["open"]))
    if "low" in df.columns and "close" in df.columns:
        violations += int(np.sum(df["low"] > df["close"]))

    return ValidationResult(
        "ohlc_integrity",
        violations == 0,
        f"{violations} OHLC violations" if violations > 0 else "All OHLC relationships valid",
        violations,
    )


def validate_missing_values(df: pd.DataFrame) -> ValidationResult:
    """Check for NaN/missing values in OHLC columns."""
    ohlc_cols = ["open", "high", "low", "close"]
    existing_cols = [c for c in ohlc_cols if c in df.columns]
    nan_counts = {c: int(df[c].isna().sum()) for c in existing_cols}
    total_nans = sum(nan_counts.values())

    details = ", ".join(f"{c}:{n}" for c, n in nan_counts.items() if n > 0)
    return ValidationResult(
        "missing_values",
        total_nans == 0,
        f"NaN counts: {details}" if total_nans > 0 else "No missing values",
        total_nans,
    )


def validate_price_values(df: pd.DataFrame) -> ValidationResult:
    """Check for non-positive or suspicious price values."""
    ohlc_cols = ["open", "high", "low", "close"]
    existing_cols = [c for c in ohlc_cols if c in df.columns]
    issues = 0
    for c in existing_cols:
        issues += int(np.sum(df[c] <= 0))

    return ValidationResult(
        "price_values",
        issues == 0,
        f"{issues} non-positive price values" if issues > 0 else "All prices positive",
        issues,
    )


def validate_bid_ask(df: pd.DataFrame) -> ValidationResult:
    """Check bid/ask integrity if both exist."""
    has_bid = any("bid" in c.lower() for c in df.columns)
    has_ask = any("ask" in c.lower() for c in df.columns)

    if not (has_bid and has_ask):
        return ValidationResult("bid_ask_check", True, "No bid/ask columns to check")

    bid_close = df.get("close_bid") or df.get("bid_close")
    ask_close = df.get("close_ask") or df.get("ask_close")

    if bid_close is not None and ask_close is not None:
        violations = int(np.sum(bid_close > ask_close))
        return ValidationResult(
            "bid_ask_integrity",
            violations == 0,
            f"{violations} bid > ask violations" if violations > 0 else "Bid <= Ask always holds",
            violations,
        )

    return ValidationResult("bid_ask_check", True, "Bid/ask columns present but could not validate")


def validate_timezone(df: pd.DataFrame) -> ValidationResult:
    """Check that timestamps are timezone-aware and in UTC."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return ValidationResult("timezone_check", False, "Index is not DatetimeIndex")

    if df.index.tz is None:
        return ValidationResult("timezone_check", False, "Timestamps are timezone-naive (no TZ info)")

    tz_str = str(df.index.tz)
    is_utc = "UTC" in tz_str.upper() or tz_str == "UTC"
    return ValidationResult(
        "timezone_utc",
        is_utc,
        f"Timezone: {tz_str}" + (" (UTC)" if is_utc else " (NOT UTC)"),
    )


def validate_data_quality(df: pd.DataFrame, source: str = "unknown", filename: str = "unknown") -> DataValidationReport:
    """Run all validation checks on a DataFrame."""
    report = DataValidationReport(source=source, filename=filename, total_bars=len(df))

    report.add_check(validate_timestamps(df))
    report.add_check(validate_duplicates(df))
    report.add_check(validate_gaps(df))
    report.add_check(validate_ohlc_integrity(df))
    report.add_check(validate_missing_values(df))
    report.add_check(validate_price_values(df))
    report.add_check(validate_bid_ask(df))
    report.add_check(validate_timezone(df))

    return report


def validate_parquet_file(filepath: str | Path) -> DataValidationReport:
    """Load and validate a parquet file."""
    filepath = Path(filepath)
    df = pd.read_parquet(filepath)
    return validate_data_quality(df, source="parquet", filename=filepath.name)


def validate_pickle_pair(filepath: str | Path, pair: str | None = None) -> DataValidationReport:
    """Load and validate a pickle pair file."""
    import pickle

    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        data = pickle.load(f)

    if isinstance(data, dict):
        if pair is None:
            pair = list(data.keys())[0]
        df = data[pair]
    else:
        df = data

    return validate_data_quality(df, source="pickle", filename=filepath.name)
