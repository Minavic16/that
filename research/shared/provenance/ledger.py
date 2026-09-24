"""Append-only research ledger (JSONL).

Answers: «What did we run, with what inputs, and what did it produce?»

Persistence rules:
  - append-only (no overwrite of prior lines)
  - one LedgerEntry per line
  - no database
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

from nestquant.research.shared.provenance.contracts import Provenance
from nestquant.research.shared.provenance.identity import now_iso

DEFAULT_LEDGER_PATH = Path("research/ledger/research_ledger.jsonl")


@dataclass(frozen=True)
class LedgerEntry:
    """Historical research event record (immutable once written)."""

    run_id: str
    experiment_id: Optional[str]
    timestamp: str
    workload_identity: Optional[str]
    data_identity: Mapping[str, Any]
    execution_identity: Mapping[str, Any]
    evaluation_identity: Mapping[str, Any]
    result_ref: Optional[str]
    git_commit: Optional[str]
    git_dirty: Optional[bool]
    status: str
    notes: tuple[str, ...] = ()
    evaluation_status: Optional[str] = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "timestamp": self.timestamp,
            "workload_identity": self.workload_identity,
            "data_identity": dict(self.data_identity),
            "execution_identity": dict(self.execution_identity),
            "evaluation_identity": dict(self.evaluation_identity),
            "result_ref": self.result_ref,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "status": self.status,
            "notes": list(self.notes),
            "evaluation_status": self.evaluation_status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "LedgerEntry":
        return cls(
            run_id=d["run_id"],
            experiment_id=d.get("experiment_id"),
            timestamp=d["timestamp"],
            workload_identity=d.get("workload_identity"),
            data_identity=d.get("data_identity", {}),
            execution_identity=d.get("execution_identity", {}),
            evaluation_identity=d.get("evaluation_identity", {}),
            result_ref=d.get("result_ref"),
            git_commit=d.get("git_commit"),
            git_dirty=d.get("git_dirty"),
            status=d["status"],
            notes=tuple(d.get("notes", ()) or ()),
            evaluation_status=d.get("evaluation_status"),
            warnings=tuple(d.get("warnings", ()) or ()),
        )

    @classmethod
    def from_provenance(
        cls,
        provenance: Provenance,
        *,
        status: str = "RECORDED",
        result_ref: Optional[str] = None,
        workload_identity: Optional[str] = None,
        evaluation_status: Optional[str] = None,
        warnings: Sequence[str] = (),
        notes: Sequence[str] = (),
        timestamp: Optional[str] = None,
    ) -> "LedgerEntry":
        return cls(
            run_id=provenance.run_id,
            experiment_id=provenance.experiment_id,
            timestamp=timestamp or provenance.created_at or now_iso(),
            workload_identity=workload_identity or provenance.strategy_identity,
            data_identity=provenance.data.to_dict(),
            execution_identity={
                "config": dict(provenance.execution_config or {}),
                "config_hash": provenance.execution_config_hash,
            },
            evaluation_identity={
                "evaluation_id": provenance.evaluation_id,
                "config": dict(provenance.evaluation_config or {}),
                "config_hash": provenance.evaluation_config_hash,
            },
            result_ref=result_ref,
            git_commit=provenance.git.commit,
            git_dirty=provenance.git.dirty,
            status=status,
            notes=tuple(notes) + tuple(provenance.notes),
            evaluation_status=evaluation_status
            if evaluation_status is not None
            else provenance.evaluation_status,
            warnings=tuple(warnings),
        )


class ResearchLedger:
    """Append-only JSONL ledger. No silent overwrite of existing run_ids."""

    def __init__(self, path: Optional[Path | str] = None):
        self.path = Path(path) if path is not None else DEFAULT_LEDGER_PATH

    def _read_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        return [ln for ln in text.splitlines() if ln.strip()]

    def entries(self) -> list[LedgerEntry]:
        out: list[LedgerEntry] = []
        for ln in self._read_lines():
            out.append(LedgerEntry.from_dict(json.loads(ln)))
        return out

    def __iter__(self) -> Iterator[LedgerEntry]:
        return iter(self.entries())

    def run_ids(self) -> set[str]:
        return {e.run_id for e in self.entries()}

    def get(self, run_id: str) -> Optional[LedgerEntry]:
        for e in self.entries():
            if e.run_id == run_id:
                return e
        return None

    def append(self, entry: LedgerEntry) -> None:
        """Append entry. Fails if run_id already exists (no silent overwrite)."""
        if entry.run_id in self.run_ids():
            raise ValueError(f"ledger run_id already exists: {entry.run_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def append_provenance(
        self,
        provenance: Provenance,
        **kwargs: Any,
    ) -> LedgerEntry:
        entry = LedgerEntry.from_provenance(provenance, **kwargs)
        self.append(entry)
        return entry

    def to_jsonl(self) -> str:
        return "\n".join(
            json.dumps(e.to_dict(), sort_keys=True, default=str) for e in self.entries()
        )
