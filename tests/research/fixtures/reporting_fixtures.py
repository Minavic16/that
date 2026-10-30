"""Shared deterministic fixtures for Phase 4 reporting tests.

Constructed Provenance/GitIdentity — no live git repository required.
"""
from __future__ import annotations

from nestquant.research.shared.evaluation import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationStatus,
    Fold,
    FoldEvaluation,
    FoldRole,
    MetricStatus,
    MetricValue,
    EvaluationMetrics,
    AggregateEvaluation,
    evaluate,
)
from nestquant.research.shared.evaluation.contracts import ExecutionMetadata
from nestquant.research.shared.execution.contracts import Trade
from nestquant.research.shared.provenance import (
    DataIdentity,
    GitIdentity,
    Provenance,
)
import pandas as pd


def make_trade(pnl: float, *, entry: str = "2024-01-02 10:00", exit_: str = "2024-01-02 14:00") -> Trade:
    return Trade(
        pair="EUR/USD",
        direction="BUY",
        entry_price=1.10,
        entry_time=pd.Timestamp(entry, tz="UTC"),
        sl_price=1.099,
        tp_price=1.102,
        lot_size=0.1,
        exit_price=1.11,
        exit_time=pd.Timestamp(exit_, tz="UTC"),
        pnl=pnl,
        exit_reason="tp" if pnl > 0 else "sl",
    )


def fixture_evaluation() -> EvaluationResult:
    trades = [
        make_trade(10.0, entry="2024-01-02 10:00", exit_="2024-01-02 11:00"),
        make_trade(-5.0, entry="2024-01-02 12:00", exit_="2024-01-02 13:00"),
        make_trade(3.0, entry="2024-01-03 10:00", exit_="2024-01-03 14:00"),
    ]
    result = evaluate(
        trades,
        EvaluationConfig(),
        execution_metadata=ExecutionMetadata(initial_balance=10000.0),
        evaluation_id="eval-fixture00000001",
    )
    # Pin evaluation_id for golden stability (builder does not alter metrics)
    return EvaluationResult(
        evaluation_id="eval-fixture00000001",
        metrics=result.metrics,
        warnings=result.warnings,
        status=result.status,
        configuration=result.configuration,
        execution_ref=result.execution_ref,
        fold=result.fold,
        experiment=result.experiment,
    )


def fixture_provenance_available() -> Provenance:
    return Provenance(
        run_id="run-fixture00000001",
        experiment_id="exp-fixture",
        git=GitIdentity(commit="a" * 40, dirty=False, available=True),
        code_version="a" * 40,
        data=DataIdentity(
            instruments=("EUR/USD",),
            timeframe="1h",
            start="2024-01-01",
            end="2024-01-05",
            source="fixture://data",
            dataset_id="ds-fixture",
            dataset_version="1",
            checksum="deadbeef",
            n_bars=100,
        ),
        strategy_identity="fixture-strategy",
        execution_config={"risk_per_trade": 0.01},
        evaluation_config={"risk_free_rate": 0.0},
        execution_config_hash="1111111111111111",
        evaluation_config_hash="2222222222222222",
        created_at="2024-06-01T00:00:00+00:00",
        evaluation_id="eval-fixture00000001",
        evaluation_status="VALID_WITH_WARNINGS",
        parent_run_id=None,
        notes=("fixture note",),
    )


def fixture_provenance_unavailable() -> Provenance:
    return Provenance(
        run_id="run-fixture00000002",
        experiment_id=None,
        git=GitIdentity(commit=None, dirty=None, available=False),
        code_version=None,
        data=DataIdentity(),
        strategy_identity=None,
        execution_config=None,
        evaluation_config=None,
        execution_config_hash=None,
        evaluation_config_hash=None,
        created_at="2024-06-01T00:00:00+00:00",
        evaluation_id="eval-fixture00000001",
        evaluation_status=None,
        parent_run_id=None,
        notes=(),
    )


def fixture_aggregate() -> AggregateEvaluation:
    t1 = [make_trade(100.0, entry="2024-01-02 10:00", exit_="2024-01-02 11:00"),
          make_trade(100.0, entry="2024-01-02 12:00", exit_="2024-01-02 13:00")]
    t2 = [make_trade(-10.0, entry="2024-01-03 10:00", exit_="2024-01-03 11:00")]
    e1 = evaluate(t1, evaluation_id="eval-fold00000000001")
    e2 = evaluate(t2, evaluation_id="eval-fold00000000002")
    # pin ids
    e1 = EvaluationResult(
        evaluation_id="eval-fold00000000001",
        metrics=e1.metrics,
        warnings=e1.warnings,
        status=e1.status,
        configuration=e1.configuration,
        execution_ref=e1.execution_ref,
        fold=e1.fold,
        experiment=e1.experiment,
    )
    e2 = EvaluationResult(
        evaluation_id="eval-fold00000000002",
        metrics=e2.metrics,
        warnings=e2.warnings,
        status=e2.status,
        configuration=e2.configuration,
        execution_ref=e2.execution_ref,
        fold=e2.fold,
        experiment=e2.experiment,
    )
    f1 = Fold(
        fold_id="fold-a",
        role=FoldRole.IS,
        train_window=None,
        test_window=None,
    )
    f2 = Fold(
        fold_id="fold-b",
        role=FoldRole.OOS,
        train_window=None,
        test_window=None,
    )
    fe1 = FoldEvaluation(fold=f1, evaluation=e1, trades=t1)
    fe2 = FoldEvaluation(fold=f2, evaluation=e2, trades=t2)
    # Build aggregate via public API for canonical aggregation_method
    from nestquant.research.shared.evaluation import aggregate_fold_evaluations

    agg = aggregate_fold_evaluations(
        [fe1, fe2],
        evaluation_id="eval-agg000000000001",
    )
    return AggregateEvaluation(
        fold_evaluations=agg.fold_evaluations,
        aggregate_metrics=agg.aggregate_metrics,
        aggregation_method=agg.aggregation_method,
        warnings=agg.warnings,
        status=agg.status,
        configuration=agg.configuration,
        evaluation_id="eval-agg000000000001",
    )


def fixed_generated_at() -> str:
    return "2024-06-01T00:00:00+00:00"
