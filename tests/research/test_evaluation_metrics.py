"""Unit tests for canonical evaluation metrics and edge cases."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from nestquant.research.shared.evaluation import (
    EvaluationConfig,
    EvaluationStatus,
    MetricStatus,
    MetricValue,
    aggregate_fold_evaluations,
    compare_evaluations,
    evaluate,
    evaluation_input_from_trades,
    compute_metrics,
)
from nestquant.research.shared.evaluation.contracts import (
    EquityPoint,
    ExecutionMetadata,
    Fold,
    FoldEvaluation,
    FoldRole,
    TimeWindow,
)
from nestquant.research.shared.execution.contracts import Trade


def make_trade(
    pnl: float,
    *,
    pair: str = "EUR/USD",
    direction: str = "BUY",
    entry: str = "2024-01-02 10:00",
    exit_: str | None = "2024-01-02 14:00",
    entry_price: float = 1.10,
    exit_price: float | None = None,
    lot: float = 0.1,
) -> Trade:
    et = pd.Timestamp(entry, tz="UTC")
    xt = pd.Timestamp(exit_, tz="UTC") if exit_ else None
    if exit_price is None:
        # fabricate exit price so trade is closed; pnl is authoritative for metrics
        exit_price = entry_price + (pnl / (lot * 100000) if direction == "BUY" else -pnl / (lot * 100000))
    return Trade(
        pair=pair,
        direction=direction,
        entry_price=entry_price,
        entry_time=et,
        sl_price=entry_price - 0.001,
        tp_price=entry_price + 0.002,
        lot_size=lot,
        exit_price=exit_price,
        exit_time=xt,
        pnl=pnl,
        exit_reason="tp" if pnl > 0 else "sl",
    )


class TestMetricSemantics:
    def test_zero_trades_counts_defined(self):
        metrics, warnings = compute_metrics([])
        assert metrics.total_trades.value == 0
        assert metrics.total_trades.status == MetricStatus.DEFINED
        assert metrics.total_pnl.value == 0.0
        assert metrics.total_pnl.status == MetricStatus.DEFINED

    def test_zero_trades_win_rate_undefined(self):
        metrics, warnings = compute_metrics([])
        assert metrics.win_rate.value is None
        assert metrics.win_rate.status == MetricStatus.UNDEFINED
        assert any("win_rate_undefined" in w for w in warnings)

    def test_zero_trades_expectancy_undefined(self):
        metrics, _ = compute_metrics([])
        assert metrics.expectancy.value is None
        assert metrics.expectancy.status == MetricStatus.UNDEFINED

    def test_all_wins_pf_infinite_not_applicable(self):
        trades = [make_trade(10.0), make_trade(20.0)]
        metrics, warnings = compute_metrics(trades)
        assert metrics.winning_trades.value == 2
        assert metrics.losing_trades.value == 0
        assert metrics.profit_factor.value is None
        assert metrics.profit_factor.status == MetricStatus.NOT_APPLICABLE
        assert any("profit_factor_infinite" in w for w in warnings)
        assert metrics.win_rate.value == 1.0

    def test_all_losses(self):
        trades = [make_trade(-10.0), make_trade(-20.0)]
        metrics, _ = compute_metrics(trades)
        assert metrics.win_rate.value == 0.0
        assert metrics.profit_factor.value == 0.0  # gp=0, gl<0 -> 0/abs = 0
        assert metrics.gross_profit.value == 0.0
        assert metrics.gross_loss.value == -30.0

    def test_mixed_breakeven(self):
        trades = [make_trade(10.0), make_trade(-5.0), make_trade(0.0)]
        metrics, _ = compute_metrics(trades)
        assert metrics.total_trades.value == 3
        assert metrics.breakeven_trades.value == 1
        assert metrics.winning_trades.value == 1
        assert metrics.losing_trades.value == 1
        assert metrics.win_rate.value == pytest.approx(1.0 / 3.0)

    def test_profit_factor_mixed(self):
        trades = [make_trade(30.0), make_trade(-15.0)]
        metrics, _ = compute_metrics(trades)
        assert metrics.profit_factor.value == pytest.approx(2.0)
        assert metrics.expectancy.value == pytest.approx(7.5)

    def test_sharpe_insufficient_obs(self):
        trades = [make_trade(10.0)]
        metrics, warnings = compute_metrics(trades)
        assert metrics.sharpe_ratio.value is None
        assert metrics.sharpe_ratio.status == MetricStatus.UNDEFINED
        assert any("sharpe_ratio_undefined_insufficient" in w for w in warnings)

    def test_sharpe_zero_variance(self):
        trades = [make_trade(10.0), make_trade(10.0), make_trade(10.0)]
        metrics, warnings = compute_metrics(trades)
        assert metrics.sharpe_ratio.value is None
        assert any("zero_variance" in w for w in warnings)

    def test_sharpe_defined_mixed(self):
        trades = [make_trade(10.0), make_trade(-5.0), make_trade(15.0), make_trade(2.0)]
        metrics, _ = compute_metrics(trades)
        assert metrics.sharpe_ratio.status == MetricStatus.DEFINED
        assert metrics.sharpe_ratio.value is not None
        assert math.isfinite(metrics.sharpe_ratio.value)

    def test_non_finite_pnl_excluded(self):
        trades = [make_trade(10.0), make_trade(float("nan")), make_trade(-5.0)]
        metrics, warnings = compute_metrics(trades)
        assert metrics.total_trades.value == 2
        assert any("non_finite_pnl" in w for w in warnings)
        assert metrics.total_pnl.value == pytest.approx(5.0)

    def test_open_trades_excluded(self):
        closed = make_trade(10.0)
        open_t = Trade(
            pair="EUR/USD",
            direction="BUY",
            entry_price=1.1,
            entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
            sl_price=1.09,
            tp_price=1.12,
            lot_size=0.1,
        )
        metrics, warnings = compute_metrics([closed, open_t])
        assert metrics.total_trades.value == 1
        assert any("open_trades_excluded" in w for w in warnings)

    def test_equity_curve_used_for_drawdown(self):
        trades = [make_trade(100.0), make_trade(-200.0)]
        eq = [
            EquityPoint(timestamp="t0", balance=10000.0),
            EquityPoint(timestamp="t1", balance=10100.0),
            EquityPoint(timestamp="t2", balance=9900.0),
        ]
        metrics, warnings = compute_metrics(
            trades, equity_curve=eq, initial_balance=10000.0
        )
        # peak 10100, trough 9900 -> dd 200
        assert metrics.max_drawdown.value == pytest.approx(200.0)
        assert not any("equity_curve_missing" in w for w in warnings)

    def test_missing_equity_uses_trade_path_with_warning(self):
        trades = [make_trade(100.0), make_trade(-50.0)]
        metrics, warnings = compute_metrics(trades, initial_balance=10000.0)
        assert any("trade_normalized" in w or "equity_curve_missing" in w for w in warnings)
        assert metrics.max_drawdown.status == MetricStatus.DEFINED

    def test_zero_initial_balance_total_return_undefined(self):
        trades = [make_trade(10.0)]
        metrics, warnings = compute_metrics(trades, initial_balance=0.0)
        assert metrics.total_return.value is None
        assert metrics.total_return.status == MetricStatus.UNDEFINED
        assert any("total_return_undefined" in w for w in warnings)

    def test_non_finite_equity_raises(self):
        eq = [EquityPoint(timestamp="t0", balance=float("nan"))]
        with pytest.raises(ValueError):
            compute_metrics([make_trade(1.0)], equity_curve=eq, initial_balance=10000)

    def test_duration_metrics(self):
        trades = [
            make_trade(10.0, entry="2024-01-02 10:00", exit_="2024-01-02 14:00"),
            make_trade(-5.0, entry="2024-01-03 10:00", exit_="2024-01-03 16:00"),
        ]
        metrics, _ = compute_metrics(trades)
        # 4h = 14400s, 6h = 21600s
        assert metrics.average_trade_duration.value == pytest.approx((14400 + 21600) / 2)
        assert metrics.average_winning_trade_duration.value == pytest.approx(14400)
        assert metrics.average_losing_trade_duration.value == pytest.approx(21600)


class TestEvaluateAPI:
    def test_evaluate_from_trades(self):
        trades = [make_trade(10.0), make_trade(-5.0)]
        result = evaluate(trades, EvaluationConfig(), execution_metadata=ExecutionMetadata(initial_balance=10000.0))
        assert result.status in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_WARNINGS)
        assert result.metrics.total_trades.value == 2
        assert result.evaluation_id.startswith("eval-")

    def test_evaluate_deterministic_metrics(self):
        trades = [make_trade(10.0), make_trade(-5.0), make_trade(3.0)]
        r1 = evaluate(trades)
        r2 = evaluate(trades)
        # evaluation_id differs but metrics identical
        d1 = r1.metrics.to_dict()
        d2 = r2.metrics.to_dict()
        assert d1 == d2
        assert r1.evaluation_id != r2.evaluation_id

    def test_evaluate_empty_is_valid_with_warnings(self):
        result = evaluate([])
        assert result.status == EvaluationStatus.VALID_WITH_WARNINGS
        assert result.metrics.total_trades.value == 0

    def test_evaluation_input_from_trades_builder(self):
        trades = [make_trade(1.0)]
        inp = evaluation_input_from_trades(trades, initial_balance=5000.0)
        result = evaluate(inp)
        assert result.metrics.total_trades.value == 1

    def test_result_roundtrip_dict(self):
        result = evaluate([make_trade(10.0), make_trade(-2.0)])
        d = result.to_dict()
        from nestquant.research.shared.evaluation import EvaluationResult

        back = EvaluationResult.from_dict(d)
        assert back.metrics.to_dict() == result.metrics.to_dict()
        assert back.status == result.status


class TestFoldsAndAggregation:
    def test_fold_roles_explicit(self):
        fold = Fold(
            fold_id="f1",
            role=FoldRole.OOS,
            train_window=TimeWindow(start="2020-01-01", end="2021-01-01", n_observations=100),
            test_window=TimeWindow(start="2021-01-01", end="2022-01-01", n_observations=50),
        )
        assert fold.role == FoldRole.OOS
        d = fold.to_dict()
        assert Fold.from_dict(d).role == FoldRole.OOS

    def test_aggregate_with_trades(self):
        t1 = [make_trade(10.0)]
        t2 = [make_trade(-5.0)]
        e1 = evaluate(t1)
        e2 = evaluate(t2)
        f1 = Fold(fold_id="1", role=FoldRole.IS)
        f2 = Fold(fold_id="2", role=FoldRole.OOS)
        agg = aggregate_fold_evaluations(
            [
                FoldEvaluation(fold=f1, evaluation=e1, trades=t1),
                FoldEvaluation(fold=f2, evaluation=e2, trades=t2),
            ]
        )
        assert agg.fold_count == 2
        assert agg.aggregate_metrics.total_trades.value == 2
        assert agg.aggregation_method == "pooled_closed_trades"
        # fold-level preserved
        assert len(agg.fold_evaluations) == 2
        assert agg.to_dict()["fold_count"] == 2

    def test_aggregate_zero_folds_warns(self):
        agg = aggregate_fold_evaluations([])
        assert agg.fold_count == 0
        assert agg.status == EvaluationStatus.VALID_WITH_WARNINGS
        assert any("zero_folds" in w for w in agg.warnings)

    def test_aggregate_without_trades_warns(self):
        e = evaluate([make_trade(1.0)])
        agg = aggregate_fold_evaluations(
            [FoldEvaluation(fold=Fold(fold_id="1"), evaluation=e, trades=None)]
        )
        assert any("aggregate_without_trades" in w for w in agg.warnings)


class TestComparison:
    def test_compare_evaluations_no_winner(self):
        a = evaluate([make_trade(10.0), make_trade(-5.0)])
        b = evaluate([make_trade(20.0), make_trade(-5.0)])
        cmp = compare_evaluations(a, b)
        assert len(cmp.differences) > 0
        names = {d.name for d in cmp.differences}
        assert "total_pnl" in names
        # no rank/winner field
        assert not hasattr(cmp, "winner")
        assert not hasattr(cmp, "rank")

    def test_relative_difference(self):
        a = evaluate([make_trade(100.0)])
        b = evaluate([make_trade(50.0)])
        cmp = compare_evaluations(a, b)
        tp = next(d for d in cmp.differences if d.name == "total_pnl")
        assert tp.absolute_difference == pytest.approx(50.0)
        assert tp.relative_difference == pytest.approx(-0.5)  # (50-100)/|100|


class TestNoUniversalScore:
    def test_evaluation_result_has_no_score(self):
        r = evaluate([make_trade(1.0)])
        assert not hasattr(r, "score")
        assert "score" not in r.to_dict()
