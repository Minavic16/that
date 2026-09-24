"""Fold helpers for canonical evaluation (representation + aggregation only).

Does not generate folds, execute strategies, or select parameters.
"""
from __future__ import annotations

from nestquant.research.shared.evaluation.contracts import (
    AggregateEvaluation,
    Fold,
    FoldEvaluation,
    FoldRole,
    TimeWindow,
)
from nestquant.research.shared.evaluation.evaluator import aggregate_fold_evaluations

__all__ = [
    "AggregateEvaluation",
    "Fold",
    "FoldEvaluation",
    "FoldRole",
    "TimeWindow",
    "aggregate_fold_evaluations",
]
