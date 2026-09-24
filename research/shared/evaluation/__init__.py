"""Canonical evaluation layer (strategy-agnostic execution measurement).

Dependency direction: data -> execution -> evaluation -> provenance -> reporting.
Must not import production.* or Strategy 2 modules.
"""
from nestquant.research.shared.evaluation.comparison import (
    EvaluationComparison,
    MetricDifference,
    compare_evaluations,
)
from nestquant.research.shared.evaluation.contracts import (
    AggregateEvaluation,
    EquityPoint,
    EvaluationConfig,
    EvaluationInput,
    EvaluationMetrics,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMetadata,
    Fold,
    FoldEvaluation,
    FoldRole,
    MetricStatus,
    MetricValue,
    TimeWindow,
)
from nestquant.research.shared.evaluation.evaluator import (
    aggregate_fold_evaluations,
    evaluate,
    evaluation_input_from_engine,
    evaluation_input_from_simulator,
    evaluation_input_from_trades,
    new_evaluation_id,
)
from nestquant.research.shared.evaluation.metrics import (
    METRIC_SEMANTICS,
    compute_metrics,
    metrics_to_jsonable,
)

__all__ = [
    "METRIC_SEMANTICS",
    "AggregateEvaluation",
    "EquityPoint",
    "EvaluationComparison",
    "EvaluationConfig",
    "EvaluationInput",
    "EvaluationMetrics",
    "EvaluationResult",
    "EvaluationStatus",
    "ExecutionMetadata",
    "Fold",
    "FoldEvaluation",
    "FoldRole",
    "MetricDifference",
    "MetricStatus",
    "MetricValue",
    "TimeWindow",
    "aggregate_fold_evaluations",
    "compare_evaluations",
    "compute_metrics",
    "evaluate",
    "evaluation_input_from_engine",
    "evaluation_input_from_simulator",
    "evaluation_input_from_trades",
    "metrics_to_jsonable",
    "new_evaluation_id",
]
