"""Single-run canonical evaluator.

API: evaluate(execution_result, evaluation_config) -> EvaluationResult

Consumes execution outputs only. No strategy, production, or broker coupling.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping, Optional, Sequence, Union

from nestquant.research.shared.evaluation.contracts import (
    EquityPoint,
    EvaluationConfig,
    EvaluationInput,
    EvaluationMetrics,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMetadata,
    Fold,
    FoldEvaluation,
    AggregateEvaluation,
)
from nestquant.research.shared.evaluation.metrics import compute_metrics
from nestquant.research.shared.execution.contracts import Trade


def new_evaluation_id() -> str:
    return f"eval-{uuid.uuid4().hex[:16]}"


def _status_from_warnings(warnings: Sequence[str], metrics: EvaluationMetrics) -> EvaluationStatus:
    """INVALID only for structural impossibilities we cannot describe.

    Zero trades is VALID with warnings (no observations), not INVALID.
    Metric-level UNDEFINED values produce VALID_WITH_WARNINGS.
    """
    if not warnings:
        return EvaluationStatus.VALID
    return EvaluationStatus.VALID_WITH_WARNINGS


def evaluate(
    execution_result: Union[EvaluationInput, Sequence[Trade], Mapping[str, Any]],
    evaluation_config: Optional[EvaluationConfig] = None,
    *,
    equity_curve: Optional[Sequence[EquityPoint]] = None,
    execution_metadata: Optional[ExecutionMetadata] = None,
    fold: Optional[Fold] = None,
    experiment_metadata: Optional[Mapping[str, Any]] = None,
    evaluation_id: Optional[str] = None,
) -> EvaluationResult:
    """Evaluate an execution result.

    Accepts:
      - EvaluationInput (preferred)
      - Sequence[Trade]
      - mapping with key "trades" (and optional equity_curve, etc.)
    """
    if isinstance(execution_result, EvaluationInput):
        inp = execution_result
        if evaluation_config is not None:
            inp = EvaluationInput(
                trades=inp.trades,
                equity_curve=inp.equity_curve,
                execution_metadata=inp.execution_metadata,
                evaluation_config=evaluation_config,
                fold_metadata=inp.fold_metadata,
                experiment_metadata=inp.experiment_metadata,
                dataset_metadata=inp.dataset_metadata,
            )
    elif isinstance(execution_result, Mapping):
        trades = execution_result.get("trades", ())
        eq = execution_result.get("equity_curve", equity_curve)
        em = execution_result.get("execution_metadata", execution_metadata)
        cfg = evaluation_config or EvaluationConfig.from_dict(
            execution_result.get("evaluation_config", {}) or {}
        )
        exp = execution_result.get("experiment_metadata", experiment_metadata)
        inp = EvaluationInput(
            trades=list(trades),
            equity_curve=eq,
            execution_metadata=em,
            evaluation_config=cfg,
            fold_metadata=execution_result.get("fold_metadata"),
            experiment_metadata=exp,
            dataset_metadata=execution_result.get("dataset_metadata"),
        )
    else:
        inp = EvaluationInput(
            trades=list(execution_result),
            equity_curve=equity_curve,
            execution_metadata=execution_metadata,
            evaluation_config=evaluation_config or EvaluationConfig(),
            experiment_metadata=experiment_metadata,
        )

    initial_balance = None
    if inp.execution_metadata is not None:
        initial_balance = inp.execution_metadata.initial_balance

    try:
        metrics, warnings = compute_metrics(
            inp.trades,
            config=inp.evaluation_config,
            equity_curve=inp.equity_curve,
            initial_balance=initial_balance,
        )
    except ValueError as e:
        # Non-finite equity/PnL path — fail safe with INVALID
        empty = EvaluationMetrics.empty()
        return EvaluationResult(
            evaluation_id=evaluation_id or new_evaluation_id(),
            metrics=empty,
            warnings=(f"invalid_execution_data:{e}",),
            status=EvaluationStatus.INVALID,
            configuration=inp.evaluation_config,
            execution_ref=(
                inp.execution_metadata.source_ref if inp.execution_metadata else None
            ),
            fold=fold.to_dict() if fold is not None else (dict(inp.fold_metadata) if inp.fold_metadata else None),
            experiment=dict(inp.experiment_metadata) if inp.experiment_metadata else None,
        )

    status = _status_from_warnings(warnings, metrics)

    fold_payload: Optional[dict] = None
    if fold is not None:
        fold_payload = fold.to_dict()
    elif inp.fold_metadata is not None:
        fold_payload = dict(inp.fold_metadata)

    return EvaluationResult(
        evaluation_id=evaluation_id or new_evaluation_id(),
        metrics=metrics,
        warnings=tuple(warnings),
        status=status,
        configuration=inp.evaluation_config,
        execution_ref=(
            inp.execution_metadata.source_ref if inp.execution_metadata else None
        ),
        fold=fold_payload,
        experiment=dict(inp.experiment_metadata) if inp.experiment_metadata else None,
    )


def evaluation_input_from_trades(
    trades: Sequence[Trade],
    *,
    initial_balance: Optional[float] = None,
    equity_curve: Optional[Sequence[EquityPoint]] = None,
    config: Optional[EvaluationConfig] = None,
    execution_metadata: Optional[ExecutionMetadata] = None,
    **meta: Any,
) -> EvaluationInput:
    """Convenience builder from Trade[] (Phase 2 execution output)."""
    em = execution_metadata
    if em is None and initial_balance is not None:
        em = ExecutionMetadata(initial_balance=initial_balance, **meta)
    elif em is not None and initial_balance is not None and em.initial_balance is None:
        em = ExecutionMetadata(
            initial_balance=initial_balance,
            cost_model=em.cost_model,
            spread_pips=em.spread_pips,
            commission_per_lot=em.commission_per_lot,
            slippage_pips=em.slippage_pips,
            instrument=em.instrument,
            timeframe=em.timeframe,
            start_timestamp=em.start_timestamp,
            end_timestamp=em.end_timestamp,
            n_bars=em.n_bars,
            execution_config=em.execution_config,
            source_ref=em.source_ref,
        )
    return EvaluationInput(
        trades=list(trades),
        equity_curve=equity_curve,
        execution_metadata=em,
        evaluation_config=config or EvaluationConfig(),
    )


def evaluation_input_from_simulator(simulator: Any) -> EvaluationInput:
    """Adapt ExecutionSimulator (Phase 2) to EvaluationInput without importing strategy."""
    portfolio = simulator.portfolio
    cfg = simulator.config
    em = ExecutionMetadata(
        initial_balance=cfg.initial_balance,
        commission_per_lot=cfg.commission_per_lot,
        spread_pips=cfg.spread_pips,
        slippage_pips=cfg.slippage_pips,
        execution_config={
            "risk_per_trade": cfg.risk_per_trade,
            "max_open_trades": cfg.max_open_trades,
        },
        source_ref="execution.ExecutionSimulator",
    )
    return EvaluationInput(
        trades=list(portfolio.trades),
        equity_curve=None,
        execution_metadata=em,
        evaluation_config=EvaluationConfig(),
    )


def evaluation_input_from_engine(engine: Any) -> EvaluationInput:
    """Adapt BacktestEngine (Phase 2) to EvaluationInput."""
    cfg = engine.config
    em = ExecutionMetadata(
        initial_balance=cfg.initial_balance,
        commission_per_lot=cfg.commission_per_lot,
        spread_pips=cfg.spread_pips,
        slippage_pips=cfg.slippage_pips,
        execution_config={
            "risk_per_trade": cfg.risk_per_trade,
            "max_open_trades": cfg.max_open_trades,
        },
        source_ref="engines.BacktestEngine",
    )
    return EvaluationInput(
        trades=list(engine._trades),
        equity_curve=None,
        execution_metadata=em,
        evaluation_config=EvaluationConfig(),
    )


def aggregate_fold_evaluations(
    fold_evaluations: Sequence[FoldEvaluation],
    *,
    configuration: Optional[EvaluationConfig] = None,
    aggregation_method: str = "pooled_closed_trades",
    evaluation_id: Optional[str] = None,
) -> AggregateEvaluation:
    """Aggregate fold evaluations by pooling closed-trade PnL metrics.

    Explicitly does NOT stitch equity curves or invent capital continuity.
    Fold-level results are always retained.
    """
    cfg = configuration or EvaluationConfig()
    warnings: list[str] = []
    if aggregation_method != "pooled_closed_trades":
        warnings.append(f"unknown_aggregation_method:{aggregation_method}")

    if not fold_evaluations:
        empty = EvaluationMetrics.empty()
        warnings.append("aggregate_zero_folds")
        return AggregateEvaluation(
            fold_evaluations=(),
            aggregate_metrics=empty,
            aggregation_method=aggregation_method,
            warnings=tuple(warnings),
            status=EvaluationStatus.VALID_WITH_WARNINGS,
            configuration=cfg,
            evaluation_id=evaluation_id or new_evaluation_id(),
        )

    # Pool trades reconstructed from fold evaluations is not available without
    # storing trades on EvaluationResult. Aggregate by combining fold metric
    # sufficient statistics where possible, else re-evaluate from union of trades
    # passed through fold evaluations if present.
    # Phase 3: require FoldEvaluation inputs that carry evaluation only.
    # Pooling strategy: recompute from concatenated metrics counts is incomplete.
    # Instead, aggregate folds that include trades via private field _trades if set.
    # Cleaner approach: accept optional trades per fold via fold metadata.
    # For justified minimalism: if all folds have total_trades defined, pool PnL
    # via weighted averages only for additive metrics; warn otherwise.

    # Pool closed trades provided on each FoldEvaluation for aggregate metrics.
    all_trades: list[Trade] = []
    for fe in fold_evaluations:
        if fe.trades:
            all_trades.extend(fe.trades)

    if all_trades:
        metrics, warns = compute_metrics(all_trades, config=cfg, initial_balance=None)
        warnings.extend(warns)
    else:
        metrics = EvaluationMetrics.empty()
        warnings.append(
            "aggregate_without_trades_unavailable_use_fold_results"
        )

    # Combine fold-level warnings
    for fe in fold_evaluations:
        for w in fe.evaluation.warnings:
            warnings.append(f"fold[{fe.fold.fold_id}]:{w}")

    status = (
        EvaluationStatus.VALID_WITH_WARNINGS
        if warnings
        else EvaluationStatus.VALID
    )
    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            uniq.append(w)

    return AggregateEvaluation(
        fold_evaluations=tuple(fold_evaluations),
        aggregate_metrics=metrics,
        aggregation_method=aggregation_method,
        warnings=tuple(uniq),
        status=status,
        configuration=cfg,
        evaluation_id=evaluation_id or new_evaluation_id(),
    )
