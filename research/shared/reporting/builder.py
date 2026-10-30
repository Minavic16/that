"""ReportBuilder — validated ReportInput → ResearchReport (thin composition).

Does not recalculate metrics, invent provenance, average folds, or write ledger.
"""
from __future__ import annotations

from typing import Optional

from nestquant.research.shared.reporting.contracts import (
    ReportInput,
    ReportMetadata,
    ResearchReport,
    ResearchReportError,
    default_report_metadata,
)


def build_report(
    report_input: ReportInput,
    *,
    metadata: Optional[ReportMetadata] = None,
    generated_at: Optional[str] = None,
) -> ResearchReport:
    """Validate ReportInput and assemble a ResearchReport.

    Raises ResearchReportError on XOR / required-field violations (fail closed).
    """
    if not isinstance(report_input, ReportInput):
        raise ResearchReportError("build_report requires a ReportInput")
    errors = report_input.validation_errors()
    if errors:
        raise ResearchReportError("; ".join(errors))

    if metadata is None:
        metadata = default_report_metadata(generated_at=generated_at)

    return ResearchReport(
        report_metadata=metadata,
        provenance=report_input.provenance,
        evaluation=report_input.evaluation,
        aggregate=report_input.aggregate,
        experiment_context=report_input.experiment_context,
    )
