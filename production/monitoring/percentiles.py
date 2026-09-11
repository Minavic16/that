"""
Percentile Framework with Sample-Size Discipline
=================================================

Provides statistically honest percentile calculations with:
- Minimum sample size requirements per percentile
- Confidence intervals where practical
- INSUFFICIENT SAMPLE labeling
- Configurable NORMAL/WARNING/ABNORMAL/EXTREME classifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# Minimum sample sizes for reasonable percentile estimates
# Based on standard statistical guidelines for percentile estimation
MIN_SAMPLES = {
    "P50": 10,
    "P75": 20,
    "P90": 30,
    "P95": 40,
    "P99": 100,
}


@dataclass(frozen=True)
class PercentileResult:
    """Result of a percentile computation with sample-size metadata."""

    value: float
    percentile: float
    sample_count: int
    min_required: int
    sufficient: bool
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None

    @property
    def label(self) -> str:
        if not self.sufficient:
            return "INSUFFICIENT SAMPLE"
        return f"P{int(self.percentile):02d} = {self.value:.4f}"

    def to_dict(self) -> dict:
        d = {
            "value": self.value,
            "percentile": self.percentile,
            "sample_count": self.sample_count,
            "min_required": self.min_required,
            "sufficient": self.sufficient,
            "label": self.label,
        }
        if self.ci_lower is not None:
            d["ci_lower"] = self.ci_lower
        if self.ci_upper is not None:
            d["ci_upper"] = self.ci_upper
        return d


@dataclass
class PercentileDistribution:
    """Full distribution summary with all requested percentiles."""

    p50: PercentileResult
    p75: PercentileResult
    p90: PercentileResult
    p95: PercentileResult
    p99: PercentileResult
    min_val: float
    max_val: float
    mean: float
    std: float
    count: int

    def to_dict(self) -> dict:
        return {
            "p50": self.p50.to_dict(),
            "p75": self.p75.to_dict(),
            "p90": self.p90.to_dict(),
            "p95": self.p95.to_dict(),
            "p99": self.p99.to_dict(),
            "min": self.min_val,
            "max": self.max_val,
            "mean": self.mean,
            "std": self.std,
            "count": self.count,
        }


def _percentile_ci(data: np.ndarray, pct: float, n_bootstrap: int = 1000) -> tuple[float, float]:
    """Bootstrap confidence interval for a percentile."""
    if len(data) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.RandomState(42)
    boot_pcts = []
    for _ in range(n_bootstrap):
        sample = rng.choice(data, size=len(data), replace=True)
        boot_pcts.append(np.percentile(sample, pct))
    arr = np.array(boot_pcts)
    return (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))


def compute_percentile(
    data: np.ndarray,
    pct: float,
    compute_ci: bool = True,
) -> PercentileResult:
    """
    Compute a single percentile with sample-size check.

    Args:
        data: Array of values
        pct: Percentile to compute (0-100)
        compute_ci: Whether to compute bootstrap CI

    Returns:
        PercentileResult with sufficient/insufficient label
    """
    n = len(data)
    key = f"P{int(pct):02d}"
    min_req = MIN_SAMPLES.get(key, 50)
    sufficient = n >= min_req

    if n == 0:
        return PercentileResult(
            value=float("nan"),
            percentile=pct,
            sample_count=0,
            min_required=min_req,
            sufficient=False,
        )

    value = float(np.percentile(data, pct))

    ci_lower, ci_upper = None, None
    if compute_ci and sufficient and n >= 5:
        ci_lower, ci_upper = _percentile_ci(data, pct)

    return PercentileResult(
        value=value,
        percentile=pct,
        sample_count=n,
        min_required=min_req,
        sufficient=sufficient,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def compute_percentiles(
    data: np.ndarray,
    percentiles: tuple[float, ...] = (50, 75, 90, 95, 99),
    compute_ci: bool = True,
) -> PercentileDistribution:
    """
    Compute a full percentile distribution with metadata.

    Args:
        data: Array of values
        percentiles: Tuple of percentiles to compute
        compute_ci: Whether to compute bootstrap CIs

    Returns:
        PercentileDistribution with all results
    """
    arr = np.asarray(data, dtype=float)
    arr = arr[np.isfinite(arr)]

    if len(arr) == 0:
        empty = PercentileResult(float("nan"), 0, 0, 0, False)
        return PercentileDistribution(
            p50=empty, p75=empty, p90=empty, p95=empty, p99=empty,
            min_val=float("nan"), max_val=float("nan"),
            mean=float("nan"), std=float("nan"), count=0,
        )

    results = {}
    for p in percentiles:
        results[f"p{int(p):02d}"] = compute_percentile(arr, p, compute_ci)

    return PercentileDistribution(
        p50=results.get("p50", compute_percentile(arr, 50, False)),
        p75=results.get("p75", compute_percentile(arr, 75, False)),
        p90=results.get("p90", compute_percentile(arr, 90, False)),
        p95=results.get("p95", compute_percentile(arr, 95, False)),
        p99=results.get("p99", compute_percentile(arr, 99, False)),
        min_val=float(np.min(arr)),
        max_val=float(np.max(arr)),
        mean=float(np.mean(arr)),
        std=float(np.std(arr)),
        count=len(arr),
    )


def classify_value(
    value: float,
    dist: PercentileDistribution,
    thresholds: Optional[dict[str, float]] = None,
) -> str:
    """
    Classify a value against a distribution.

    Default thresholds based on percentile tiers:
    - NORMAL: below P75
    - WARNING: P75-P90
    - ABNORMAL: P90-P99
    - EXTREME: above P99

    Args:
        value: The value to classify
        dist: The reference distribution
        thresholds: Optional custom thresholds dict with keys p75, p90, p99

    Returns:
        Classification string
    """
    if not np.isfinite(value):
        return "INSUFFICIENT DATA"

    if dist.count == 0:
        return "INSUFFICIENT DATA"

    if thresholds:
        p99_val = thresholds.get("p99", dist.p99.value if dist.p99.sufficient else float("inf"))
        p90_val = thresholds.get("p90", dist.p90.value if dist.p90.sufficient else float("inf"))
        p75_val = thresholds.get("p75", dist.p75.value if dist.p75.sufficient else float("inf"))
    else:
        p99_val = dist.p99.value if dist.p99.sufficient else float("inf")
        p90_val = dist.p90.value if dist.p90.sufficient else float("inf")
        p75_val = dist.p75.value if dist.p75.sufficient else float("inf")

    if value >= p99_val:
        return "EXTREME"
    elif value >= p90_val:
        return "ABNORMAL"
    elif value >= p75_val:
        return "WARNING"
    else:
        return "NORMAL"
