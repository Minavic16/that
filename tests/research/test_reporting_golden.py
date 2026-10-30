"""Golden Markdown snapshot for Phase 4 reporting (no live git required)."""
from __future__ import annotations

from pathlib import Path

from nestquant.research.shared.reporting import (
    MarkdownRenderer,
    ReportInput,
    build_report,
)
from tests.research.fixtures.reporting_fixtures import (
    fixed_generated_at,
    fixture_evaluation,
    fixture_provenance_available,
)

GOLDEN_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "golden"
    / "research_report_single_run.md"
)


def _build_fixed_report():
    return build_report(
        ReportInput(
            provenance=fixture_provenance_available(),
            evaluation=fixture_evaluation(),
        ),
        generated_at=fixed_generated_at(),
    )


def test_golden_markdown_matches_fixture():
    report = _build_fixed_report()
    actual = MarkdownRenderer().render_with_renderer_meta(report)
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert actual == expected


def test_golden_is_stable_across_renders():
    report = _build_fixed_report()
    r = MarkdownRenderer()
    assert r.render_with_renderer_meta(report) == r.render_with_renderer_meta(
        report
    )


def test_golden_does_not_require_live_git():
    # Fixture uses constructed GitIdentity; rendering works without repo state
    report = _build_fixed_report()
    assert report.provenance.git.available is True
    assert report.provenance.git.commit == "a" * 40
    md = MarkdownRenderer().render_with_renderer_meta(report)
    assert "a" * 40 in md
