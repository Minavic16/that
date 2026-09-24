"""Canonical metric computation for execution-level evaluation.

Formula authority for the ROS evaluation layer (P&L / trade metrics).
Compatible in spirit with research.shared.backtest.metrics.calculate_metrics
for shared formulas, with explicit MetricValue edge-case statuses.

Must not import production.* or Strategy 2 modules.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from nestquant.research.shared.evaluation.contracts import (
    EquityPoint,
    EvaluationConfig,
    EvaluationMetrics,
    MetricStatus,
    MetricValue,
)
from nestquant.research.shared.execution.contracts import Trade

# ---------------------------------------------------------------------------
# METRIC_SEMANTICS — canonical definitions (see architecture doc)
# ---------------------------------------------------------------------------

METRIC_SEMANTICS: dict[str, dict[str, str]] = {
    "total_trades": {
        "definition": "Count of closed trades (exit_price is not None).",
        "unit": "count",
    },
    "winning_trades": {
        "definition": "Closed trades with pnl > 0.",
        "unit": "count",
    },
    "losing_trades": {
        "definition": "Closed trades with pnl < 0.",
        "unit": "count",
    },
    "breakeven_trades": {
        "definition": "Closed trades with pnl == 0.",
        "unit": "count",
    },
    "win_rate": {
        "definition": (
            "winning_trades / total_trades. Breakeven trades count in the "
            "denominator but not the numerator (include_breakeven_in_win_rate=False "
            "only affects numerator policy if enabled)."
        ),
        "unit": "ratio",
        "zero_trades": "UNDEFINED (None), not 0.",
    },
    "total_pnl": {
        "definition": "Sum of closed trade pnl.",
        "unit": "currency",
        "zero_trades": "DEFINED 0.0 (empty sum).",
    },
    "gross_profit": {
        "definition": "Sum of positive closed trade pnl.",
        "unit": "currency",
    },
    "gross_loss": {
        "definition": "Sum of negative closed trade pnl (reported as a negative number).",
        "unit": "currency",
    },
    "profit_factor": {
        "definition": "gross_profit / abs(gross_loss).",
        "unit": "ratio",
        "zero_gross_loss": (
            "If gross_profit > 0 and gross_loss == 0 -> +inf (JSON null + warning). "
            "If both 0 -> UNDEFINED."
        ),
    },
    "average_win": {
        "definition": "Mean of positive closed pnl.",
        "unit": "currency",
        "zero_wins": "UNDEFINED (None).",
    },
    "average_loss": {
        "definition": "Mean of negative closed pnl.",
        "unit": "currency",
        "zero_losses": "UNDEFINED (None).",
    },
    "expectancy": {
        "definition": "Mean closed trade pnl.",
        "unit": "currency",
        "zero_trades": "UNDEFINED (None).",
    },
    "max_drawdown": {
        "definition": (
            "Maximum peak-to-trough drop on the equity path. Uses provided "
            "equity_curve when present; otherwise trade-normalized cumsum path "
            "from initial_balance (warning emitted)."
        ),
        "unit": "currency",
    },
    "max_drawdown_pct": {
        "definition": "max_drawdown / running_peak * 100 (percent).",
        "unit": "percent",
    },
    "total_return": {
        "definition": (
            "(final_equity - start_equity) / start_equity when start > 0."
        ),
        "unit": "ratio",
        "zero_start": "UNDEFINED if start equity <= 0.",
    },
    "sharpe_ratio": {
        "definition": (
            "Annualized mean/std of per-trade pnl (or equity simple returns if "
            "equity_curve provided and config prefers equity returns — Phase 3 "
            "uses closed-trade pnl series for determinism with execution). "
            "scale = sqrt(periods_per_year); excess uses risk_free_rate as a "
            "per-period rate approximation matching backtest/metrics.py."
        ),
        "unit": "ratio",
        "insufficient_obs": "UNDEFINED if n < min_observations_for_sharpe.",
        "zero_variance": "UNDEFINED (None), not 0.",
    },
    "average_trade_duration": {
        "definition": "Mean (exit_time - entry_time) over closed trades with both timestamps.",
        "unit": "timedelta_seconds",
    },
    "average_winning_trade_duration": {
        "definition": "Mean duration over winning closed trades.",
        "unit": "timedelta_seconds",
    },
    "average_losing_trade_duration": {
        "definition": "Mean duration over losing closed trades.",
        "unit": "timedelta_seconds",
    },
}


def _defined(name: str, value: float | int, unit: str) -> MetricValue:
    return MetricValue(
        name=name,
        value=value,
        unit=unit or METRIC_SEMANTICS.get(name, {}).get("unit", ""),
        definition=METRIC_SEMANTICS.get(name, {}).get("definition", ""),
        status=MetricStatus.DEFINED,
    )


def _undefined(name: str) -> MetricValue:
    sem = METRIC_SEMANTICS.get(name, {})
    return MetricValue(
        name=name,
        value=None,
        unit=sem.get("unit", ""),
        definition=sem.get("definition", ""),
        status=MetricStatus.UNDEFINED,
    )


def _is_finite(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def _safe_float(x: float) -> Optional[float]:
    """Return float if finite; caller decides undefined handling for inf."""
    f = float(x)
    if math.isnan(f):
        return None
    return f


def closed_trades(trades: Sequence[Trade]) -> list[Trade]:
    return [t for t in trades if not t.is_open]


def open_trades(trades: Sequence[Trade]) -> list[Trade]:
    return [t for t in trades if t.is_open]


def _duration_seconds(trade: Trade) -> Optional[float]:
    d = trade.duration
    if d is None:
        return None
    try:
        return float(d.total_seconds())
    except Exception:
        return None


def _mean_or_none(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(np.mean(np.asarray(values, dtype=float)))


def trade_equity_path(
    trades: Sequence[Trade], initial_balance: float
) -> list[float]:
    """Trade-normalized equity path (cumsum of closed pnl + initial)."""
    path = [float(initial_balance)]
    bal = float(initial_balance)
    for t in closed_trades(trades):
        bal += float(t.pnl)
        path.append(bal)
    return path


def equity_path_from_points(
    points: Sequence[EquityPoint],
) -> list[float]:
    return [float(p.balance) for p in points]


def max_drawdown_from_path(path: Sequence[float]) -> tuple[float, float]:
    """Return (max_drawdown_currency, max_drawdown_pct)."""
    if not path:
        return 0.0, 0.0
    arr = np.asarray(path, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError("non-finite equity path")
    peak = np.maximum.accumulate(arr)
    # avoid div by zero on peak
    dd = peak - arr
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = np.where(peak != 0, dd / peak * 100.0, 0.0)
    max_dd = float(np.max(dd)) if len(dd) else 0.0
    max_dd_pct = float(np.max(dd_pct)) if len(dd) else 0.0
    if not math.isfinite(max_dd):
        raise ValueError("non-finite drawdown")
    if not math.isfinite(max_dd_pct):
        raise ValueError("non-finite drawdown pct")
    return max_dd, max_dd_pct


def compute_metrics(
    trades: Sequence[Trade],
    config: Optional[EvaluationConfig] = None,
    equity_curve: Optional[Sequence[EquityPoint]] = None,
    initial_balance: Optional[float] = None,
) -> tuple[EvaluationMetrics, list[str]]:
    """Compute canonical metrics and warnings.

    Returns (metrics, warnings).
    """
    cfg = config or EvaluationConfig()
    warnings: list[str] = []

    closed = closed_trades(trades)
    opens = open_trades(trades)
    if opens:
        warnings.append(
            f"open_trades_excluded_from_metrics:{len(opens)}"
        )

    # Non-finite / malformed PnL
    bad_pnl = 0
    pnls: list[float] = []
    for t in closed:
        if not _is_finite(float(t.pnl)):
            bad_pnl += 1
        else:
            pnls.append(float(t.pnl))
    if bad_pnl:
        warnings.append(f"non_finite_pnl_excluded:{bad_pnl}")
        # exclude trades with non-finite pnl from all pnl metrics
        closed_valid = [t for t in closed if _is_finite(float(t.pnl))]
    else:
        closed_valid = closed

    # Malformed timestamps for duration
    duration_vals: list[float] = []
    win_dur: list[float] = []
    loss_dur: list[float] = []
    for t in closed_valid:
        d = _duration_seconds(t)
        if d is None:
            warnings.append("trade_missing_duration_excluded")
            continue
        duration_vals.append(d)
        if t.pnl > 0:
            win_dur.append(d)
        elif t.pnl < 0:
            loss_dur.append(d)

    n = len(closed_valid)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    breakeven = [p for p in pnls if p == 0]

    # --- counts ---
    total_trades = _defined("total_trades", n, "count")
    if not closed and opens:
        # only open trades — total closed is 0 (defined)
        pass

    winning_trades = _defined("winning_trades", len(wins), "count")
    losing_trades = _defined("losing_trades", len(losses), "count")
    breakeven_trades = _defined("breakeven_trades", len(breakeven), "count")

    # --- win_rate ---
    if n == 0:
        win_rate = _undefined("win_rate")
        warnings.append("win_rate_undefined_zero_trades")
    else:
        num = len(wins)
        if cfg.include_breakeven_in_win_rate:
            num = len(wins) + len(breakeven)
        win_rate = _defined("win_rate", num / n, "ratio")

    # --- pnl aggregates ---
    if n == 0:
        total_pnl = _defined("total_pnl", 0.0, "currency")
        gross_profit = _defined("gross_profit", 0.0, "currency")
        gross_loss = _defined("gross_loss", 0.0, "currency")
        profit_factor = _undefined("profit_factor")
        warnings.append("profit_factor_undefined_zero_trades")
        average_win = _undefined("average_win")
        average_loss = _undefined("average_loss")
        expectancy = _undefined("expectancy")
        warnings.append("expectancy_undefined_zero_trades")
    else:
        total_pnl = _defined("total_pnl", float(np.sum(pnls)), "currency")
        gp = float(np.sum(wins)) if wins else 0.0
        gl = float(np.sum(losses)) if losses else 0.0
        gross_profit = _defined("gross_profit", gp, "currency")
        gross_loss = _defined("gross_loss", gl, "currency")
        if gl == 0.0:
            if gp > 0.0:
                # +inf — store as None with NOT_APPLICABLE? Spec wants explicit.
                # Represent +inf as status DEFINED with value None is wrong.
                # Use value=inf is invalid JSON. Use NOT_APPLICABLE + warning.
                profit_factor = MetricValue(
                    name="profit_factor",
                    value=None,
                    unit="ratio",
                    definition=METRIC_SEMANTICS["profit_factor"]["definition"],
                    status=MetricStatus.NOT_APPLICABLE,
                )
                warnings.append("profit_factor_infinite_no_losses")
            else:
                profit_factor = _undefined("profit_factor")
                warnings.append("profit_factor_undefined_zero_gross_loss")
        else:
            profit_factor = _defined("profit_factor", gp / abs(gl), "ratio")

        average_win = (
            _defined("average_win", float(np.mean(wins)), "currency")
            if wins
            else _undefined("average_win")
        )
        if not wins:
            warnings.append("average_win_undefined_zero_wins")
        average_loss = (
            _defined("average_loss", float(np.mean(losses)), "currency")
            if losses
            else _undefined("average_loss")
        )
        if not losses:
            warnings.append("average_loss_undefined_zero_losses")
        expectancy = _defined("expectancy", float(np.mean(pnls)), "currency")

    # --- equity / drawdown / return ---
    start_equity: Optional[float] = None
    path: list[float] = []
    if equity_curve is not None and len(equity_curve) > 0:
        path = equity_path_from_points(equity_curve)
        start_equity = path[0]
        if not all(_is_finite(b) for b in path):
            raise ValueError("non-finite equity curve value")
    else:
        ib = initial_balance
        if ib is None:
            ib = 0.0
            if n > 0:
                warnings.append("equity_curve_missing_and_initial_balance_unknown")
        else:
            if not _is_finite(float(ib)):
                raise ValueError("non-finite initial_balance")
            warnings.append("equity_curve_missing_trade_normalized_drawdown")
        path = trade_equity_path(closed_valid, float(ib))
        start_equity = float(ib)

    try:
        max_dd, max_dd_pct = max_drawdown_from_path(path)
        max_drawdown = _defined("max_drawdown", max_dd, "currency")
        max_drawdown_pct = _defined("max_drawdown_pct", max_dd_pct, "percent")
    except ValueError as e:
        max_drawdown = _undefined("max_drawdown")
        max_drawdown_pct = _undefined("max_drawdown_pct")
        warnings.append(f"max_drawdown_undefined:{e}")

    # total return
    if not cfg.compute_total_return:
        total_return = MetricValue(
            name="total_return",
            value=None,
            unit="ratio",
            definition=METRIC_SEMANTICS["total_return"]["definition"],
            status=MetricStatus.NOT_APPLICABLE,
        )
    elif start_equity is None or start_equity <= 0:
        total_return = _undefined("total_return")
        warnings.append("total_return_undefined_nonpositive_start")
    else:
        end_equity = path[-1] if path else start_equity
        total_return = _defined(
            "total_return", (end_equity - start_equity) / start_equity, "ratio"
        )

    # --- sharpe ---
    if len(pnls) < cfg.min_observations_for_sharpe:
        sharpe_ratio = _undefined("sharpe_ratio")
        warnings.append("sharpe_ratio_undefined_insufficient_observations")
    else:
        arr = np.asarray(pnls, dtype=float)
        std = float(np.std(arr))
        if std == 0.0 or not math.isfinite(std):
            sharpe_ratio = _undefined("sharpe_ratio")
            warnings.append("sharpe_ratio_undefined_zero_variance")
        else:
            # Match backtest/metrics.py: excess = pnl - risk_free_rate (per period)
            excess = arr - cfg.risk_free_rate
            val = float(np.mean(excess) / std * math.sqrt(cfg.periods_per_year))
            if not math.isfinite(val):
                sharpe_ratio = _undefined("sharpe_ratio")
                warnings.append("sharpe_ratio_undefined_nonfinite")
            else:
                sharpe_ratio = _defined("sharpe_ratio", val, "ratio")

    # --- durations ---
    avg_dur = _mean_or_none(duration_vals)
    avg_win_dur = _mean_or_none(win_dur)
    avg_loss_dur = _mean_or_none(loss_dur)
    if avg_dur is None and n > 0:
        warnings.append("average_trade_duration_undefined_missing_timestamps")
    average_trade_duration = (
        _defined("average_trade_duration", avg_dur, "timedelta_seconds")
        if avg_dur is not None
        else _undefined("average_trade_duration")
    )
    average_winning_trade_duration = (
        _defined("average_winning_trade_duration", avg_win_dur, "timedelta_seconds")
        if avg_win_dur is not None
        else _undefined("average_winning_trade_duration")
    )
    average_losing_trade_duration = (
        _defined("average_losing_trade_duration", avg_loss_dur, "timedelta_seconds")
        if avg_loss_dur is not None
        else _undefined("average_losing_trade_duration")
    )

    metrics = EvaluationMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        total_return=total_return,
        sharpe_ratio=sharpe_ratio,
        average_trade_duration=average_trade_duration,
        average_winning_trade_duration=average_winning_trade_duration,
        average_losing_trade_duration=average_losing_trade_duration,
    )
    # de-duplicate warnings while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return metrics, uniq


def metrics_to_jsonable(metrics: EvaluationMetrics) -> dict:
    """Convert metrics to JSON-safe dict (inf -> None already via MetricValue)."""
    out = {}
    for k, mv in metrics.as_mapping().items():
        d = mv.to_dict()
        v = d.get("value")
        if v is not None and isinstance(v, float) and not math.isfinite(v):
            d["value"] = None
            if v == float("inf"):
                d["status"] = MetricStatus.NOT_APPLICABLE.value
        out[k] = d
    return out
