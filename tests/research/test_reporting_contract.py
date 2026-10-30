"""Phase 4 reporting contract and builder tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nestquant.research.shared.reporting import (
    JsonRenderer,
    MarkdownRenderer,
    ReportInput,
    ReportMetadata,
    ResearchReport,
    ResearchReportError,
    build_report,
    default_report_metadata,
)
from tests.research.fixtures.reporting_fixtures import (
    fixed_generated_at,
    fixture_aggregate,
    fixture_evaluation,
    fixture_provenance_available,
    fixture_provenance_unavailable,
)


class TestReportInputContract:
    def test_evaluation_only_valid(self):
        ri = ReportInput(
            provenance=fixture_provenance_available(),
            evaluation=fixture_evaluation(),
        )
        assert ri.is_valid()
        assert ri.validation_errors() == []

    def test_aggregate_only_valid(self):
        ri = ReportInput(
            provenance=fixture_provenance_available(),
            aggregate=fixture_aggregate(),
        )
        assert ri.is_valid()

    def test_both_rejected(self):
        ri = ReportInput(
            provenance=fixture_provenance_available(),
            evaluation=fixture_evaluation(),
            aggregate=fixture_aggregate(),
        )
        assert not ri.is_valid()
        with pytest.raises(ResearchReportError, match="exactly one"):
            build_report(ri)

    def test_neither_rejected(self):
        ri = ReportInput(provenance=fixture_provenance_available())
        assert not ri.is_valid()
        with pytest.raises(ResearchReportError):
            build_report(ri)

    def test_provenance_required(self):
        # Provenance is a required positional field; None must fail validation
        ri = ReportInput(
            provenance=None,  # type: ignore[arg-type]
            evaluation=fixture_evaluation(),
        )
        assert not ri.is_valid()
        with pytest.raises(ResearchReportError, match="provenance"):
            build_report(ri)

    def test_experiment_context_passthrough(self):
        ctx = {"hypothesis": "researcher text", "label": "w1"}
        ri = ReportInput(
            provenance=fixture_provenance_available(),
            evaluation=fixture_evaluation(),
            experiment_context=ctx,
        )
        report = build_report(ri, generated_at=fixed_generated_at())
        assert report.experiment_context == ctx
        # not mutated into a semantic model
        assert report.experiment_context is not None
        assert "hypothesis" in report.experiment_context


class TestResearchReportBuilder:
    def test_preserves_evaluation_result(self):
        ev = fixture_evaluation()
        prov = fixture_provenance_available()
        report = build_report(
            ReportInput(provenance=prov, evaluation=ev),
            generated_at=fixed_generated_at(),
        )
        assert report.evaluation is not None
        assert report.evaluation is ev
        assert report.aggregate is None
        assert report.provenance is prov
        assert report.face_kind == "evaluation"
        assert report.status == ev.status
        assert report.warnings == ev.warnings
        assert report.evaluation_id == ev.evaluation_id
        assert report.get_metrics() is ev.metrics
        # metric values unchanged
        assert (
            report.get_metrics().total_trades.value == ev.metrics.total_trades.value
        )
        assert (
            report.get_metrics().win_rate.value == ev.metrics.win_rate.value
        )

    def test_preserves_aggregate(self):
        agg = fixture_aggregate()
        prov = fixture_provenance_available()
        report = build_report(
            ReportInput(provenance=prov, aggregate=agg),
            generated_at=fixed_generated_at(),
        )
        assert report.aggregate is agg
        assert report.evaluation is None
        assert report.is_aggregate
        assert report.face_kind == "aggregate"
        assert report.get_metrics() is agg.aggregate_metrics
        assert report.warnings == agg.warnings
        assert len(report.evaluation_face.fold_evaluations) == agg.fold_count

    def test_preserves_provenance_unavailable(self):
        prov = fixture_provenance_unavailable()
        report = build_report(
            ReportInput(provenance=prov, evaluation=fixture_evaluation()),
            generated_at=fixed_generated_at(),
        )
        assert report.provenance.git.available is False
        assert report.provenance.git.commit is None
        assert report.provenance.data.checksum is None
        assert report.provenance.strategy_identity is None

    def test_evaluation_status_preserved(self):
        ev = fixture_evaluation()
        prov = fixture_provenance_available()
        report = build_report(
            ReportInput(provenance=prov, evaluation=ev),
            generated_at=fixed_generated_at(),
        )
        assert report.status is ev.status
        assert report.provenance.evaluation_status == "VALID_WITH_WARNINGS"

    def test_no_metric_recalculation(self):
        ev = fixture_evaluation()
        before = ev.metrics.to_dict()
        report = build_report(
            ReportInput(provenance=fixture_provenance_available(), evaluation=ev),
            generated_at=fixed_generated_at(),
        )
        _ = report.to_dict()
        assert ev.metrics.to_dict() == before

    def test_report_metadata_fields(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        assert report.report_metadata.report_type == "research_report"
        assert report.report_metadata.schema_version == "1.0"
        assert report.report_metadata.generated_at == fixed_generated_at()

    def test_metadata_roundtrip(self):
        md = default_report_metadata(
            generated_at=fixed_generated_at(), renderer="markdown:1.0"
        )
        assert ReportMetadata.from_dict(md.to_dict()) == md


class TestSerialization:
    def test_to_dict_nested_canonical(self):
        ev = fixture_evaluation()
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=ev,
            ),
            generated_at=fixed_generated_at(),
        )
        d = report.to_dict()
        assert d["face_kind"] == "evaluation"
        assert d["evaluation"]["evaluation_id"] == ev.evaluation_id
        assert d["evaluation"]["status"] == ev.status.value
        assert "metrics" in d["evaluation"]
        assert d["provenance"]["run_id"] == report.provenance.run_id
        assert d["report_metadata"]["schema_version"] == "1.0"

    def test_to_dict_aggregate_nested(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                aggregate=fixture_aggregate(),
            ),
            generated_at=fixed_generated_at(),
        )
        d = report.to_dict()
        assert d["face_kind"] == "aggregate"
        assert "aggregation_method" in d["evaluation"]
        assert "fold_evaluations" in d["evaluation"]
        assert "aggregate_metrics" in d["evaluation"]

    def test_from_dict_roundtrip_evaluation(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
                experiment_context={"k": "v"},
            ),
            generated_at=fixed_generated_at(),
        )
        back = ResearchReport.from_dict(report.to_dict())
        assert back.face_kind == "evaluation"
        assert back.evaluation_id == report.evaluation_id
        assert back.provenance.run_id == report.provenance.run_id
        assert back.experiment_context == {"k": "v"}
        assert (
            back.get_metrics().to_dict() == report.get_metrics().to_dict()
        )

    def test_from_dict_roundtrip_aggregate(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                aggregate=fixture_aggregate(),
            ),
            generated_at=fixed_generated_at(),
        )
        back = ResearchReport.from_dict(report.to_dict())
        assert back.face_kind == "aggregate"
        assert back.aggregate is not None
        assert (
            back.aggregate.aggregation_method
            == report.aggregate.aggregation_method
        )
        assert back.aggregate.fold_count == report.aggregate.fold_count


class TestRenderers:
    def test_markdown_sections_and_values(self):
        ev = fixture_evaluation()
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=ev,
            ),
            generated_at=fixed_generated_at(),
        )
        md = MarkdownRenderer().render_with_renderer_meta(report)
        for heading in [
            "# Research Report",
            "## Summary",
            "## Experiment",
            "## Evaluation",
            "## Folds",
            "## Provenance",
            "## Warnings & Limitations",
        ]:
            assert heading in md
        # canonical metric present with status
        assert "`total_trades`" in md
        assert ev.metrics.total_trades.status.value in md
        # no quality adjectives auto-injected
        for bad in [" strategy performed well", "Research Score", "excellent"]:
            assert bad not in md

    def test_markdown_deterministic(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        r = MarkdownRenderer()
        a = r.render_with_renderer_meta(report)
        b = r.render_with_renderer_meta(report)
        assert a == b

    def test_markdown_unavailable_provenance(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_unavailable(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        md = MarkdownRenderer().render_with_renderer_meta(report)
        assert "unavailable" in md
        assert "Git available: `false`" in md
        # no fabricated sha
        assert "a" * 40 not in md

    def test_markdown_aggregate_fold_distinction(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                aggregate=fixture_aggregate(),
            ),
            generated_at=fixed_generated_at(),
        )
        md = MarkdownRenderer().render_with_renderer_meta(report)
        assert "Aggregate metrics" in md
        assert "pooled_closed_trades" in md
        assert "Fold-level evaluations" in md
        assert "not averaged" in md or "not fold-level averages" in md
        assert "fold-a" in md and "fold-b" in md

    def test_markdown_preserves_warnings(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        md = MarkdownRenderer().render_with_renderer_meta(report)
        for w in report.warnings:
            assert f"`{w}`" in md

    def test_json_renderer_not_from_markdown(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        text = JsonRenderer().render(report)
        payload = json.loads(text)
        assert payload["face_kind"] == "evaluation"
        assert payload["report_metadata"]["renderer"] == "json:1.0"
        # nested structure preserved
        assert payload["evaluation"]["metrics"]["total_trades"]["status"] in (
            "DEFINED",
            "UNDEFINED",
            "NOT_APPLICABLE",
        )
        assert payload["provenance"]["run_id"] == report.provenance.run_id

    def test_json_strict_no_nan(self):
        report = build_report(
            ReportInput(
                provenance=fixture_provenance_available(),
                evaluation=fixture_evaluation(),
            ),
            generated_at=fixed_generated_at(),
        )
        text = JsonRenderer().render(report)
        assert "NaN" not in text
        assert "Infinity" not in text
        json.loads(text)


class TestImportBoundaries:
    def test_reporting_package_no_production_or_strategy2(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "reporting"
        for py in pkg.rglob("*.py"):
            src = py.read_text()
            assert "nestquant.production" not in src, py
            assert "strategy2" not in src, py
            assert "apparatus" not in src, py

    def test_reporting_does_not_import_ledger_write_path(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "reporting"
        for py in pkg.rglob("*.py"):
            src = py.read_text()
            assert "ResearchLedger" not in src, py
            assert "append_provenance" not in src, py

    def test_no_experiment_config_import(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "reporting"
        for py in pkg.rglob("*.py"):
            src = py.read_text()
            assert "research.experiment" not in src, py
            assert "ExperimentConfig" not in src, py
