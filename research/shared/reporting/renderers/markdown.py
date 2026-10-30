"""Markdown renderer — deterministic projection of ResearchReport.

No metric recalculation. No quality language. No strategy-specific logic.
"""
from __future__ import annotations

from typing import Optional

from nestquant.research.shared.evaluation.contracts import (
    AggregateEvaluation,
    EvaluationMetrics,
    EvaluationResult,
    MetricStatus,
    MetricValue,
)
from nestquant.research.shared.provenance.contracts import Provenance
from nestquant.research.shared.reporting.contracts import ResearchReport

# Presentation-only explanations for known Phase 3 warning codes.
# Not severity; not inference. Unknown codes render as-is.
KNOWN_WARNING_TEXT: dict[str, str] = {
    "aggregate_zero_folds": "Zero folds were supplied to aggregate evaluation.",
    "aggregate_without_trades_unavailable_use_fold_results": (
        "Aggregate metrics unavailable without carried trades; use fold-level results."
    ),
    "equity_curve_missing_trade_normalized_drawdown": (
        "Drawdown uses trade-normalized path (equity curve missing)."
    ),
    "equity_curve_missing_and_initial_balance_unknown": (
        "Drawdown uses trade-normalized path from base 0 (equity and initial balance unknown)."
    ),
    "non_finite_pnl_excluded": "Closed trades with non-finite PnL were excluded.",
    "open_trades_excluded_from_metrics": "Open trades were excluded from closed-trade metrics.",
    "profit_factor_infinite_no_losses": "Profit factor infinite (no losing trades).",
    "win_rate_undefined_zero_trades": "Win rate undefined (zero trades).",
    "sharpe_ratio_undefined_insufficient_observations": (
        "Sharpe ratio undefined (insufficient observations)."
    ),
    "sharpe_ratio_undefined_zero_variance": "Sharpe ratio undefined (zero variance).",
    "duplicate_trades_counted_as_supplied": (
        "Duplicate trade objects count as distinct observations."
    ),
}

UNAVAILABLE = "unavailable"


def _fmt_value(mv: MetricValue) -> str:
    if mv.status != MetricStatus.DEFINED or mv.value is None:
        if mv.status == MetricStatus.NOT_APPLICABLE:
            return "n/a (not applicable)"
        return UNAVAILABLE
    v = mv.value
    if isinstance(v, float):
        if mv.unit == "ratio" and abs(v) <= 1.0 and mv.name == "win_rate":
            return f"{v * 100:.1f}%"
        if mv.unit == "percent":
            return f"{v:.2f}%"
        if float(v).is_integer() and mv.unit == "count":
            return str(int(v))
        return f"{v:.6g}"
    return str(v)


def _metric_row(mv: MetricValue) -> str:
    return (
        f"| `{mv.name}` | {_fmt_value(mv)} | {mv.unit} | {mv.status.value} |"
    )


def _metrics_table(metrics: EvaluationMetrics) -> list[str]:
    lines = [
        "| Metric | Value | Unit | Status |",
        "|---|---:|---|---|",
    ]
    for name, mv in metrics.as_mapping().items():
        lines.append(_metric_row(mv))
    return lines


def _identity_or_unavailable(value: Optional[object]) -> str:
    if value is None or value == "" or value == ():
        return UNAVAILABLE
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        if not value:
            return UNAVAILABLE
        return ", ".join(str(x) for x in value)
    return str(value)


def _warning_lines(warnings: tuple[str, ...]) -> list[str]:
    if not warnings:
        return ["- none"]
    out: list[str] = []
    for w in warnings:
        base = w.split(":", 1)[0]
        # strip fold[id]: prefix for catalog lookup of trailing code
        catalog_key = base
        if base.startswith("fold[") and "]:" in base:
            catalog_key = base.split("]:", 1)[-1]
        explanation = KNOWN_WARNING_TEXT.get(catalog_key)
        if explanation:
            out.append(f"- `{w}` — {explanation}")
        else:
            out.append(f"- `{w}`")
    return out


def _summary_lines(report: ResearchReport) -> list[str]:
    face = report.evaluation_face
    metrics = report.get_metrics()
    total = metrics.total_trades
    win_rate = metrics.win_rate
    pf = metrics.profit_factor
    lines: list[str] = [
        f"- Evaluation ID: `{report.evaluation_id}`",
        f"- Status: `{face.status.value}`",
        f"- Face: `{report.face_kind}`",
    ]
    if report.face_kind == "aggregate":
        assert report.aggregate is not None
        lines.append(
            f"- Aggregation method: `{report.aggregate.aggregation_method}`"
        )
        lines.append(f"- Fold count: {report.aggregate.fold_count}")
    if total.status == MetricStatus.DEFINED and total.value is not None:
        lines.append(f"- Closed trades (finite PnL): {total.value}")
    if win_rate.status == MetricStatus.DEFINED and win_rate.value is not None:
        lines.append(f"- Win rate: {_fmt_value(win_rate)}")
    if pf.status == MetricStatus.DEFINED and pf.value is not None:
        lines.append(f"- Profit factor: {_fmt_value(pf)}")
    elif pf.status == MetricStatus.NOT_APPLICABLE:
        lines.append("- Profit factor: n/a (not applicable)")
    else:
        lines.append(f"- Profit factor: {UNAVAILABLE}")
    if report.warnings:
        lines.append(f"- Warnings: {len(report.warnings)}")
    else:
        lines.append("- Warnings: 0")
    return lines


def _experiment_lines(report: ResearchReport) -> list[str]:
    prov = report.provenance
    lines = [
        f"- Experiment ID: {_identity_or_unavailable(prov.experiment_id)}",
        f"- Strategy / workload: {_identity_or_unavailable(prov.strategy_identity)}",
        f"- Run ID: `{prov.run_id}`",
    ]
    eval_exp = None
    if report.evaluation is not None:
        eval_exp = report.evaluation.experiment
    if eval_exp:
        lines.append("- Evaluation experiment payload:")
        for k in sorted(eval_exp.keys()):
            lines.append(f"  - {k}: {eval_exp[k]}")
    if report.experiment_context:
        lines.append("- Experiment context (pass-through):")
        for k in sorted(report.experiment_context.keys()):
            lines.append(f"  - {k}: {report.experiment_context[k]}")
    else:
        lines.append(f"- Experiment context: {UNAVAILABLE}")
    if report.evaluation is not None and report.evaluation.fold:
        lines.append(f"- Fold payload: `{dict(report.evaluation.fold)}`")
    return lines


def _evaluation_lines(report: ResearchReport) -> list[str]:
    lines: list[str] = []
    if report.face_kind == "aggregate":
        assert report.aggregate is not None
        lines.append(
            "**Aggregate metrics** "
            f"(method=`{report.aggregate.aggregation_method}`) — "
            "not fold-level averages:"
        )
        lines.append("")
        lines.extend(_metrics_table(report.aggregate.aggregate_metrics))
        lines.append("")
        lines.append(
            "Path-dependent aggregate metrics depend on supplied fold order; "
            "they are not a stitched multi-fold portfolio equity curve."
        )
    else:
        assert report.evaluation is not None
        lines.append("**Evaluation metrics** (canonical, not recalculated):")
        lines.append("")
        lines.extend(_metrics_table(report.evaluation.metrics))
        lines.append("")
        if report.evaluation.configuration is not None:
            cfg = report.evaluation.configuration.to_dict()
            lines.append(
                f"- Evaluation config: rf={cfg.get('risk_free_rate')}, "
                f"periods_per_year={cfg.get('periods_per_year')}, "
                f"min_obs={cfg.get('min_observations_for_sharpe')}"
            )
        if report.evaluation.execution_ref:
            lines.append(f"- Execution ref: `{report.evaluation.execution_ref}`")
    return lines


def _folds_lines(report: ResearchReport) -> list[str]:
    if report.aggregate is None:
        if report.evaluation is not None and report.evaluation.fold:
            return [
                "- Single-run fold metadata present "
                f"(not a multi-fold series): `{dict(report.evaluation.fold)}`",
            ]
        return ["- Not applicable (single-run evaluation without fold payload)."]
    agg = report.aggregate
    lines = [
        f"- Fold count: {agg.fold_count}",
        f"- Aggregation method: `{agg.aggregation_method}`",
        "",
        "### Fold-level evaluations",
        "",
    ]
    if not agg.fold_evaluations:
        lines.append("- none")
        return lines
    for fe in agg.fold_evaluations:
        fold = fe.fold
        ev = fe.evaluation
        lines.append(f"#### Fold `{fold.fold_id}` (role=`{fold.role.value}`)")
        lines.append(f"- Status: `{ev.status.value}`")
        if fold.train_window and fold.train_window.start:
            lines.append(
                f"- Train window: {fold.train_window.start} → {fold.train_window.end}"
            )
        if fold.test_window and fold.test_window.start:
            lines.append(
                f"- Test window: {fold.test_window.start} → {fold.test_window.end}"
            )
        if ev.warnings:
            lines.append(f"- Warnings: {', '.join(f'`{w}`' for w in ev.warnings)}")
        total = ev.metrics.total_trades
        wr = ev.metrics.win_rate
        if total.status == MetricStatus.DEFINED and total.value is not None:
            lines.append(f"- Total trades: {total.value}")
        if wr.status == MetricStatus.DEFINED and wr.value is not None:
            lines.append(f"- Win rate: {_fmt_value(wr)}")
        lines.append(
            "- Fold metrics are fold-level; they are not averaged into the aggregate."
        )
        lines.append("")
    lines.append(
        "### Aggregate (pooled) metrics — distinct from fold-level metrics"
    )
    lines.append("")
    lines.extend(_metrics_table(agg.aggregate_metrics))
    return lines


def _provenance_lines(report: ResearchReport) -> list[str]:
    p = report.provenance
    git = p.git
    data = p.data
    lines = [
        f"- Run ID: `{p.run_id}`",
        f"- Experiment ID: {_identity_or_unavailable(p.experiment_id)}",
        f"- Strategy identity: {_identity_or_unavailable(p.strategy_identity)}",
        f"- Git available: `{'true' if git.available else 'false'}`",
        f"- Git commit: `{_identity_or_unavailable(git.commit)}`",
        f"- Git dirty: {_identity_or_unavailable(git.dirty)}",
        f"- Code version: `{_identity_or_unavailable(p.code_version)}`",
        f"- Data instruments: {_identity_or_unavailable(data.instruments)}",
        f"- Data timeframe: {_identity_or_unavailable(data.timeframe)}",
        f"- Data source: {_identity_or_unavailable(data.source)}",
        f"- Data checksum: `{_identity_or_unavailable(data.checksum)}`",
        f"- Data dataset_id: `{_identity_or_unavailable(data.dataset_id)}`",
        f"- Data dataset_version: `{_identity_or_unavailable(data.dataset_version)}`",
        f"- Data n_bars: {_identity_or_unavailable(data.n_bars)}",
        f"- Execution config hash: `{_identity_or_unavailable(p.execution_config_hash)}`",
        f"- Evaluation config hash: `{_identity_or_unavailable(p.evaluation_config_hash)}`",
        f"- Evaluation ID: `{_identity_or_unavailable(p.evaluation_id)}`",
        f"- Evaluation status (provenance): "
        f"`{_identity_or_unavailable(p.evaluation_status)}`",
        f"- Evaluation status (face): `{report.status.value}`",
        f"- Created at: `{_identity_or_unavailable(p.created_at)}`",
        f"- Parent run ID: `{_identity_or_unavailable(p.parent_run_id)}`",
    ]
    if p.notes:
        lines.append("- Notes:")
        for n in p.notes:
            lines.append(f"  - {n}")
    return lines


class MarkdownRenderer:
    """Deterministic Markdown projection of ResearchReport."""

    name = "markdown"
    version = "1.0"

    def render(self, report: ResearchReport) -> str:
        md = report.report_metadata
        sections: list[str] = []
        sections.append("# Research Report")
        sections.append("")
        sections.append(
            f"- Report type: `{md.report_type}`  \n"
            f"- Schema version: `{md.schema_version}`  \n"
            f"- Generated at: `{md.generated_at or UNAVAILABLE}`  \n"
            f"- Renderer: `{md.renderer or UNAVAILABLE}`"
        )
        sections.append("")
        sections.append("## Summary")
        sections.append("")
        sections.extend(_summary_lines(report))
        sections.append("")
        sections.append("## Experiment")
        sections.append("")
        sections.extend(_experiment_lines(report))
        sections.append("")
        sections.append("## Evaluation")
        sections.append("")
        sections.extend(_evaluation_lines(report))
        sections.append("")
        sections.append("## Folds")
        sections.append("")
        sections.extend(_folds_lines(report))
        sections.append("")
        sections.append("## Provenance")
        sections.append("")
        sections.extend(_provenance_lines(report))
        sections.append("")
        sections.append("## Warnings & Limitations")
        sections.append("")
        sections.extend(_warning_lines(report.warnings))
        sections.append("")
        sections.append("### Limitations applicable to this report")
        sections.append("")
        sections.extend(_limitation_lines(report))
        sections.append("")
        return "\n".join(sections)

    def render_with_renderer_meta(self, report: ResearchReport) -> str:
        """Render after stamping renderer identity onto metadata (non-mutating copy)."""
        from dataclasses import replace

        meta = replace(
            report.report_metadata,
            renderer=f"{self.name}:{self.version}",
        )
        stamped = replace(report, report_metadata=meta)
        return self.render(stamped)


def _limitation_lines(report: ResearchReport) -> list[str]:
    """Only limitations actually applicable to the supplied result."""
    out: list[str] = []
    metrics = report.get_metrics()
    warning_bases = {w.split(":", 1)[0] for w in report.warnings}
    for w in list(report.warnings):
        if w.startswith("fold[") and "]:" in w:
            warning_bases.add(w.split("]:", 1)[-1])

    if (
        metrics.sharpe_ratio.status == MetricStatus.DEFINED
        and "sharpe" not in "".join(out).lower()
    ):
        out.append(
            "- Sharpe uses trade-PnL series annualized with √252 "
            "(not portfolio time-series Sharpe)."
        )
    if report.is_aggregate:
        out.append(
            "- Aggregate path-dependent metrics depend on fold order "
            "(pooled_closed_trades; no equity stitch; no overlap detection)."
        )
    if not report.provenance.data.checksum:
        out.append("- Dataset checksum unavailable in provenance (optional DataIdentity).")
    if "non_finite_pnl_excluded" in warning_bases:
        out.append("- Non-finite PnL trades excluded from the evaluation population.")
    if "duplicate" in " ".join(report.warnings):
        out.append("- Duplicate trades counted as supplied (upstream convention).")
    if (
        "equity_curve_missing_trade_normalized_drawdown" in warning_bases
        or "equity_curve_missing_and_initial_balance_unknown" in warning_bases
    ):
        out.append(
            "- Drawdown source is warning-distinguished (trade-normalized, not equity-path)."
        )
    if not report.provenance.git.available:
        out.append("- Git identity unavailable (fail-closed; not fabricated).")
    if not out:
        out.append("- none beyond canonical metric definitions and warnings above.")
    return out


__all__ = ["MarkdownRenderer", "KNOWN_WARNING_TEXT", "UNAVAILABLE"]
