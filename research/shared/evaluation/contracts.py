"""Canonical evaluation contracts (strategy-agnostic P&L / execution evaluation).

Depends only on execution trade types and the standard library/NumPy.
Must not import production.* or Strategy 2 modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from nestquant.research.shared.execution.contracts import Trade


class EvaluationStatus(str, Enum):
    """Structural status of an evaluation (not a strategy quality score)."""

    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


class MetricStatus(str, Enum):
    """Whether a single metric is defined for this input."""

    DEFINED = "DEFINED"
    UNDEFINED = "UNDEFINED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FoldRole(str, Enum):
    """Explicit semantic role of a fold/window (never inferred from time order)."""

    TRAIN = "TRAIN"
    IS = "IS"
    OOS = "OOS"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MetricValue:
    """Canonical metric with explicit definition and edge-case status.

    value is None iff status != DEFINED. Never invents 0 for undefined metrics.
    """

    name: str
    value: Optional[float | int]
    unit: str
    definition: str
    status: MetricStatus = MetricStatus.DEFINED

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "definition": self.definition,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "MetricValue":
        return cls(
            name=d["name"],
            value=d.get("value"),
            unit=d.get("unit", ""),
            definition=d.get("definition", ""),
            status=MetricStatus(d.get("status", MetricStatus.DEFINED.value)),
        )


@dataclass(frozen=True)
class EvaluationConfig:
    """Explicit evaluation conventions (no hidden defaults beyond documented ones).

    Defaults match research.shared.backtest.metrics.calculate_metrics where
    a convention already exists in-repo:
      - risk_free_rate = 0.0
      - periods_per_year = 252 (daily-equivalent annualization used by metrics.py)
      - drawdown source: equity_curve if provided, else closed-trade PnL path
        (trade-normalized approximation; emits a warning when equity is absent)
    """

    risk_free_rate: float = 0.0
    periods_per_year: int = 252
    min_observations_for_sharpe: int = 2
    include_breakeven_in_win_rate: bool = False
    # When True, total_return uses equity end/start if equity_curve present;
    # else (initial + total_pnl) / initial when initial_balance > 0.
    compute_total_return: bool = True

    def to_dict(self) -> dict:
        return {
            "risk_free_rate": self.risk_free_rate,
            "periods_per_year": self.periods_per_year,
            "min_observations_for_sharpe": self.min_observations_for_sharpe,
            "include_breakeven_in_win_rate": self.include_breakeven_in_win_rate,
            "compute_total_return": self.compute_total_return,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "EvaluationConfig":
        return cls(
            risk_free_rate=float(d.get("risk_free_rate", 0.0)),
            periods_per_year=int(d.get("periods_per_year", 252)),
            min_observations_for_sharpe=int(d.get("min_observations_for_sharpe", 2)),
            include_breakeven_in_win_rate=bool(
                d.get("include_breakeven_in_win_rate", False)
            ),
            compute_total_return=bool(d.get("compute_total_return", True)),
        )


@dataclass(frozen=True)
class EquityPoint:
    """Single balance observation on the equity curve."""

    timestamp: Any
    balance: float


@dataclass(frozen=True)
class ExecutionMetadata:
    """Optional reference metadata about the execution that produced trades."""

    initial_balance: Optional[float] = None
    cost_model: Optional[str] = None
    spread_pips: Optional[float] = None
    commission_per_lot: Optional[float] = None
    slippage_pips: Optional[float] = None
    instrument: Optional[str] = None
    timeframe: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    n_bars: Optional[int] = None
    execution_config: Optional[Mapping[str, Any]] = None
    source_ref: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "initial_balance": self.initial_balance,
            "cost_model": self.cost_model,
            "spread_pips": self.spread_pips,
            "commission_per_lot": self.commission_per_lot,
            "slippage_pips": self.slippage_pips,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "n_bars": self.n_bars,
            "source_ref": self.source_ref,
        }
        if self.execution_config is not None:
            d["execution_config"] = dict(self.execution_config)
        else:
            d["execution_config"] = None
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ExecutionMetadata":
        return cls(
            initial_balance=d.get("initial_balance"),
            cost_model=d.get("cost_model"),
            spread_pips=d.get("spread_pips"),
            commission_per_lot=d.get("commission_per_lot"),
            slippage_pips=d.get("slippage_pips"),
            instrument=d.get("instrument"),
            timeframe=d.get("timeframe"),
            start_timestamp=d.get("start_timestamp"),
            end_timestamp=d.get("end_timestamp"),
            n_bars=d.get("n_bars"),
            execution_config=d.get("execution_config"),
            source_ref=d.get("source_ref"),
        )


@dataclass(frozen=True)
class EvaluationInput:
    """Stable input contract for the canonical evaluator.

    Consumes execution outputs (Trade[]), not strategy implementations.
    """

    trades: Sequence[Trade]
    equity_curve: Optional[Sequence[EquityPoint]] = None
    execution_metadata: Optional[ExecutionMetadata] = None
    evaluation_config: EvaluationConfig = field(default_factory=EvaluationConfig)
    fold_metadata: Optional[Mapping[str, Any]] = None
    experiment_metadata: Optional[Mapping[str, Any]] = None
    dataset_metadata: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class EvaluationMetrics:
    """Canonical single-run metric set (explicit MetricValue each field)."""

    total_trades: MetricValue
    winning_trades: MetricValue
    losing_trades: MetricValue
    breakeven_trades: MetricValue
    win_rate: MetricValue
    total_pnl: MetricValue
    gross_profit: MetricValue
    gross_loss: MetricValue
    profit_factor: MetricValue
    average_win: MetricValue
    average_loss: MetricValue
    expectancy: MetricValue
    max_drawdown: MetricValue
    max_drawdown_pct: MetricValue
    total_return: MetricValue
    sharpe_ratio: MetricValue
    average_trade_duration: MetricValue
    average_winning_trade_duration: MetricValue
    average_losing_trade_duration: MetricValue

    def as_mapping(self) -> dict[str, MetricValue]:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "average_trade_duration": self.average_trade_duration,
            "average_winning_trade_duration": self.average_winning_trade_duration,
            "average_losing_trade_duration": self.average_losing_trade_duration,
        }

    def to_dict(self) -> dict:
        return {k: v.to_dict() for k, v in self.as_mapping().items()}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "EvaluationMetrics":
        parsed = {k: MetricValue.from_dict(v) for k, v in d.items()}
        return cls(**parsed)

    @classmethod
    def empty(cls) -> "EvaluationMetrics":
        def m(name: str, unit: str, definition: str) -> MetricValue:
            return MetricValue(
                name=name,
                value=None,
                unit=unit,
                definition=definition,
                status=MetricStatus.UNDEFINED,
            )

        return cls(
            total_trades=m(
                "total_trades",
                "count",
                "closed trades with finite PnL in the evaluation population",
            ),
            winning_trades=m("winning_trades", "count", "closed trades with pnl>0"),
            losing_trades=m("losing_trades", "count", "closed trades with pnl<0"),
            breakeven_trades=m("breakeven_trades", "count", "closed trades with pnl==0"),
            win_rate=m("win_rate", "ratio", "winning/total closed"),
            total_pnl=m("total_pnl", "currency", "sum of closed trade pnl"),
            gross_profit=m("gross_profit", "currency", "sum of positive pnl"),
            gross_loss=m("gross_loss", "currency", "sum of negative pnl (negative)"),
            profit_factor=m("profit_factor", "ratio", "gross_profit/|gross_loss|"),
            average_win=m("average_win", "currency", "mean positive pnl"),
            average_loss=m("average_loss", "currency", "mean negative pnl"),
            expectancy=m("expectancy", "currency", "mean pnl per closed trade"),
            max_drawdown=m("max_drawdown", "currency", "peak-to-trough equity drop"),
            max_drawdown_pct=m("max_drawdown_pct", "percent", "max drawdown / peak * 100"),
            total_return=m("total_return", "ratio", "equity growth / start"),
            sharpe_ratio=m(
                "sharpe_ratio",
                "ratio",
                "annualized mean/std of trade pnls (or equity returns)",
            ),
            average_trade_duration=m(
                "average_trade_duration", "timedelta", "mean exit-entry duration"
            ),
            average_winning_trade_duration=m(
                "average_winning_trade_duration", "timedelta", "mean duration of wins"
            ),
            average_losing_trade_duration=m(
                "average_losing_trade_duration", "timedelta", "mean duration of losses"
            ),
        )


@dataclass(frozen=True)
class EvaluationResult:
    """Immutable single-run evaluation evidence (not a quality score).

    Duplicate-trade convention: metrics reflect the trade observations supplied
    to evaluate(); duplicate trade objects count as distinct observations.
    """

    evaluation_id: str
    metrics: EvaluationMetrics
    warnings: tuple[str, ...]
    status: EvaluationStatus
    configuration: EvaluationConfig
    execution_ref: Optional[str] = None
    fold: Optional[Mapping[str, Any]] = None
    experiment: Optional[Mapping[str, Any]] = None

    def get(self, name: str) -> MetricValue:
        return self.metrics.as_mapping()[name]

    def to_dict(self) -> dict:
        # Lazy import: metrics.py depends on contracts; avoid circular import.
        from nestquant.research.shared.evaluation.metrics import metrics_to_jsonable

        return {
            "evaluation_id": self.evaluation_id,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "configuration": self.configuration.to_dict(),
            "metrics": metrics_to_jsonable(self.metrics),
            "execution_ref": self.execution_ref,
            "fold": dict(self.fold) if self.fold is not None else None,
            "experiment": dict(self.experiment) if self.experiment is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "EvaluationResult":
        return cls(
            evaluation_id=d["evaluation_id"],
            metrics=EvaluationMetrics.from_dict(d["metrics"]),
            warnings=tuple(d.get("warnings", ())),
            status=EvaluationStatus(d["status"]),
            configuration=EvaluationConfig.from_dict(d.get("configuration", {})),
            execution_ref=d.get("execution_ref"),
            fold=d.get("fold"),
            experiment=d.get("experiment"),
        )


@dataclass(frozen=True)
class TimeWindow:
    """Explicit time window (ISO strings or any serializable bounds)."""

    start: Optional[str] = None
    end: Optional[str] = None
    n_observations: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "n_observations": self.n_observations,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "TimeWindow":
        return cls(
            start=d.get("start"),
            end=d.get("end"),
            n_observations=d.get("n_observations"),
        )


@dataclass(frozen=True)
class Fold:
    """A fold/window with explicit roles. Single-run experiments may omit folds."""

    fold_id: str
    role: FoldRole = FoldRole.UNKNOWN
    train_window: Optional[TimeWindow] = None
    validation_window: Optional[TimeWindow] = None
    test_window: Optional[TimeWindow] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fold_id": self.fold_id,
            "role": self.role.value,
            "train_window": self.train_window.to_dict() if self.train_window else None,
            "validation_window": (
                self.validation_window.to_dict() if self.validation_window else None
            ),
            "test_window": self.test_window.to_dict() if self.test_window else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Fold":
        return cls(
            fold_id=d["fold_id"],
            role=FoldRole(d.get("role", FoldRole.UNKNOWN.value)),
            train_window=(
                TimeWindow.from_dict(d["train_window"]) if d.get("train_window") else None
            ),
            validation_window=(
                TimeWindow.from_dict(d["validation_window"])
                if d.get("validation_window")
                else None
            ),
            test_window=(
                TimeWindow.from_dict(d["test_window"]) if d.get("test_window") else None
            ),
            metadata=d.get("metadata", {}),
        )


@dataclass(frozen=True)
class FoldEvaluation:
    """Evaluation bound to one fold.

    ``trades`` is optional and only used for aggregate pooling; fold-level
    metrics never require it.
    """

    fold: Fold
    evaluation: EvaluationResult
    trades: Optional[Sequence[Trade]] = None

    def to_dict(self) -> dict:
        return {
            "fold": self.fold.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "has_trades": self.trades is not None,
            "n_trades": len(self.trades) if self.trades is not None else 0,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "FoldEvaluation":
        # trades are not serialized into compact fold payloads by default;
        # callers rehydrate trades from execution references if needed.
        return cls(
            fold=Fold.from_dict(d["fold"]),
            evaluation=EvaluationResult.from_dict(d["evaluation"]),
            trades=None,
        )


@dataclass(frozen=True)
class AggregateEvaluation:
    """Aggregation across folds that never hides fold-level evidence."""

    fold_evaluations: tuple[FoldEvaluation, ...]
    aggregate_metrics: EvaluationMetrics
    aggregation_method: str
    warnings: tuple[str, ...]
    status: EvaluationStatus
    configuration: EvaluationConfig
    evaluation_id: str

    @property
    def fold_count(self) -> int:
        return len(self.fold_evaluations)

    def to_dict(self) -> dict:
        return {
            "evaluation_id": self.evaluation_id,
            "aggregation_method": self.aggregation_method,
            "fold_count": self.fold_count,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "configuration": self.configuration.to_dict(),
            "aggregate_metrics": self.aggregate_metrics.to_dict(),
            "fold_evaluations": [fe.to_dict() for fe in self.fold_evaluations],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "AggregateEvaluation":
        return cls(
            fold_evaluations=tuple(
                FoldEvaluation.from_dict(x) for x in d.get("fold_evaluations", ())
            ),
            aggregate_metrics=EvaluationMetrics.from_dict(d["aggregate_metrics"]),
            aggregation_method=d["aggregation_method"],
            warnings=tuple(d.get("warnings", ())),
            status=EvaluationStatus(d["status"]),
            configuration=EvaluationConfig.from_dict(d.get("configuration", {})),
            evaluation_id=d["evaluation_id"],
        )


# JSON-safe encoding for non-finite floats in metric payloads is handled in
# metrics/evaluator helpers; MetricValue.value for non-finite special cases
# uses status + documented sentinels where noted in METRIC_SEMANTICS.
