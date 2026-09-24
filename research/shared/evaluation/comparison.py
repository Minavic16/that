"""Narrow evaluation comparison (describes differences; no universal winner)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from nestquant.research.shared.evaluation.contracts import (
    EvaluationResult,
    MetricStatus,
    MetricValue,
)


@dataclass(frozen=True)
class MetricDifference:
    name: str
    left: Optional[float]
    right: Optional[float]
    absolute_difference: Optional[float]
    relative_difference: Optional[float]
    left_status: str
    right_status: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "left": self.left,
            "right": self.right,
            "absolute_difference": self.absolute_difference,
            "relative_difference": self.relative_difference,
            "left_status": self.left_status,
            "right_status": self.right_status,
        }


@dataclass(frozen=True)
class EvaluationComparison:
    """Describes metric differences between two evaluations. No ranking."""

    left: EvaluationResult
    right: EvaluationResult
    differences: tuple[MetricDifference, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "differences": [d.to_dict() for d in self.differences],
            "metadata": dict(self.metadata),
        }


def _numeric(mv: MetricValue) -> Optional[float]:
    if mv.status != MetricStatus.DEFINED or mv.value is None:
        return None
    try:
        return float(mv.value)
    except (TypeError, ValueError):
        return None


def compare_evaluations(
    left: EvaluationResult,
    right: EvaluationResult,
    *,
    metadata: Optional[Mapping[str, Any]] = None,
) -> EvaluationComparison:
    """Compute absolute and relative differences for shared defined metrics."""
    left_map = left.metrics.as_mapping()
    right_map = right.metrics.as_mapping()
    diffs: list[MetricDifference] = []
    for name in left_map:
        if name not in right_map:
            continue
        lm, rm = left_map[name], right_map[name]
        lv, rv = _numeric(lm), _numeric(rm)
        if lv is None or rv is None:
            abs_diff = None
            rel_diff = None
        else:
            abs_diff = lv - rv
            if lv != 0:
                rel_diff = (rv - lv) / abs(lv)
            else:
                rel_diff = None
        diffs.append(
            MetricDifference(
                name=name,
                left=lv,
                right=rv,
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                left_status=lm.status.value,
                right_status=rm.status.value,
            )
        )
    return EvaluationComparison(
        left=left,
        right=right,
        differences=tuple(diffs),
        metadata=dict(metadata or {}),
    )
