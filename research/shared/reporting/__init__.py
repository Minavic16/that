"""Canonical reporting layer (presentation boundary over evaluation + provenance).

Dependency direction: data -> execution -> evaluation -> provenance -> reporting.
Must not import production.* or Strategy 2 modules.
Must not write to the research ledger.
"""
from nestquant.research.shared.reporting.builder import build_report
from nestquant.research.shared.reporting.contracts import (
    REPORT_SCHEMA_VERSION,
    REPORT_TYPE,
    ReportInput,
    ReportMetadata,
    ResearchReport,
    ResearchReportError,
    default_report_metadata,
)
from nestquant.research.shared.reporting.renderers import (
    JsonRenderer,
    MarkdownRenderer,
)

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "REPORT_TYPE",
    "JsonRenderer",
    "MarkdownRenderer",
    "ReportInput",
    "ReportMetadata",
    "ResearchReport",
    "ResearchReportError",
    "build_report",
    "default_report_metadata",
]
