"""JSON renderer — serializes ResearchReport via to_dict().

JSON is never produced by parsing Markdown. ResearchReport is the shared object.
"""
from __future__ import annotations

import json
from dataclasses import replace

from nestquant.research.shared.reporting.contracts import ResearchReport

JSON_RENDERER_NAME = "json"
JSON_RENDERER_VERSION = "1.0"


class JsonRenderer:
    """Machine-readable renderer over ResearchReport.to_dict()."""

    name = JSON_RENDERER_NAME
    version = JSON_RENDERER_VERSION

    def to_payload(self, report: ResearchReport) -> dict:
        return report.to_dict()

    def render(self, report: ResearchReport, *, indent: int | None = 2) -> str:
        meta = replace(
            report.report_metadata,
            renderer=f"{self.name}:{self.version}",
        )
        stamped = replace(report, report_metadata=meta)
        return json.dumps(
            stamped.to_dict(),
            indent=indent,
            sort_keys=True,
            allow_nan=False,
            default=str,
        )


__all__ = ["JsonRenderer"]
