"""Canonical reporting contracts (presentation boundary over Phase 3 objects).

Thin composition only: holds EvaluationResult OR AggregateEvaluation plus
Provenance. Does not own parallel metric semantics.

Must not import production.* or Strategy 2 modules.
Must not write to the research ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, Optional

from nestquant.research.shared.evaluation.contracts import (
    AggregateEvaluation,
    EvaluationResult,
)
from nestquant.research.shared.provenance.contracts import Provenance

REPORT_SCHEMA_VERSION = "1.0"
REPORT_TYPE = "research_report"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ReportMetadata:
    """Artifact-level report identity (not research provenance)."""

    report_type: str = REPORT_TYPE
    schema_version: str = REPORT_SCHEMA_VERSION
    generated_at: Optional[str] = None
    renderer: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "report_type": self.report_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "renderer": self.renderer,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ReportMetadata":
        return cls(
            report_type=d.get("report_type", REPORT_TYPE),
            schema_version=d.get("schema_version", REPORT_SCHEMA_VERSION),
            generated_at=d.get("generated_at"),
            renderer=d.get("renderer"),
        )


@dataclass(frozen=True)
class ReportInput:
    """Inputs to the report builder.

    Exactly one of evaluation / aggregate must be supplied (XOR).
    provenance is required. experiment_context is a pure pass-through mapping.
    """

    provenance: Provenance
    evaluation: Optional[EvaluationResult] = None
    aggregate: Optional[AggregateEvaluation] = None
    experiment_context: Optional[Mapping[str, Any]] = None

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        has_eval = self.evaluation is not None
        has_agg = self.aggregate is not None
        if has_eval and has_agg:
            errors.append(
                "ReportInput requires exactly one of evaluation or aggregate; both were supplied"
            )
        if not has_eval and not has_agg:
            errors.append(
                "ReportInput requires exactly one of evaluation or aggregate; neither was supplied"
            )
        if self.provenance is None:
            errors.append("ReportInput.provenance is required")
        return errors

    def is_valid(self) -> bool:
        return not self.validation_errors()


@dataclass(frozen=True)
class ResearchReport:
    """Format-independent thin composition over canonical upstream objects."""

    report_metadata: ReportMetadata
    provenance: Provenance
    evaluation: Optional[EvaluationResult] = None
    aggregate: Optional[AggregateEvaluation] = None
    experiment_context: Optional[Mapping[str, Any]] = None

    @property
    def evaluation_face(self) -> EvaluationResult | AggregateEvaluation:
        if self.evaluation is not None:
            return self.evaluation
        if self.aggregate is not None:
            return self.aggregate
        raise ResearchReportError("ResearchReport has no evaluation face")

    @property
    def is_aggregate(self) -> bool:
        return self.aggregate is not None

    @property
    def face_kind(self) -> str:
        if self.evaluation is not None:
            return "evaluation"
        if self.aggregate is not None:
            return "aggregate"
        return "none"

    @property
    def status(self):
        return self.evaluation_face.status

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self.evaluation_face.warnings)

    @property
    def evaluation_id(self) -> str:
        return self.evaluation_face.evaluation_id

    def get_metrics(self):
        """Canonical metrics for the evaluation face (never recomputed)."""
        if self.evaluation is not None:
            return self.evaluation.metrics
        if self.aggregate is not None:
            return self.aggregate.aggregate_metrics
        raise ResearchReportError("ResearchReport has no evaluation face")

    def to_dict(self) -> dict:
        """Canonical serialization path for JSON renderer.

        Nested upstream structures are preserved via their frozen to_dict().
        """
        evaluation_payload: Optional[dict]
        if self.evaluation is not None:
            evaluation_payload = self.evaluation.to_dict()
        elif self.aggregate is not None:
            evaluation_payload = self.aggregate.to_dict()
        else:
            evaluation_payload = None
        return {
            "report_metadata": self.report_metadata.to_dict(),
            "face_kind": self.face_kind,
            "evaluation": evaluation_payload,
            "provenance": self.provenance.to_dict(),
            "experiment_context": (
                dict(self.experiment_context)
                if self.experiment_context is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ResearchReport":
        from nestquant.research.shared.evaluation.contracts import (
            EvaluationResult,
        )

        face = d.get("evaluation")
        face_kind = d.get("face_kind") or (
            "aggregate" if face and "aggregation_method" in face else "evaluation"
        )
        evaluation: Optional[EvaluationResult] = None
        aggregate: Optional[AggregateEvaluation] = None
        if face is not None:
            if face_kind == "aggregate" or (
                isinstance(face, Mapping) and "aggregation_method" in face
            ):
                aggregate = AggregateEvaluation.from_dict(face)
            else:
                evaluation = EvaluationResult.from_dict(face)
        prov_d = d.get("provenance") or {}
        return cls(
            report_metadata=ReportMetadata.from_dict(d.get("report_metadata") or {}),
            provenance=Provenance.from_dict(prov_d),
            evaluation=evaluation,
            aggregate=aggregate,
            experiment_context=d.get("experiment_context"),
        )


class ResearchReportError(ValueError):
    """Invalid report construction or access (fail closed)."""


def default_report_metadata(
    *, generated_at: Optional[str] = None, renderer: Optional[str] = None
) -> ReportMetadata:
    return ReportMetadata(
        report_type=REPORT_TYPE,
        schema_version=REPORT_SCHEMA_VERSION,
        generated_at=generated_at or _now_iso(),
        renderer=renderer,
    )
