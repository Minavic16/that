"""Provenance contracts for research runs (experiment-agnostic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class GitIdentity:
    """Repository git state at provenance build time."""

    commit: Optional[str] = None
    dirty: Optional[bool] = None
    available: bool = False

    def to_dict(self) -> dict:
        return {
            "commit": self.commit,
            "dirty": self.dirty,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "GitIdentity":
        return cls(
            commit=d.get("commit"),
            dirty=d.get("dirty"),
            available=bool(d.get("available", False)),
        )


@dataclass(frozen=True)
class DataIdentity:
    """Identity of the dataset/window used by a run."""

    instruments: tuple[str, ...] = ()
    timeframe: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    source: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_version: Optional[str] = None
    checksum: Optional[str] = None
    n_bars: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "instruments": list(self.instruments),
            "timeframe": self.timeframe,
            "start": self.start,
            "end": self.end,
            "source": self.source,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "checksum": self.checksum,
            "n_bars": self.n_bars,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "DataIdentity":
        return cls(
            instruments=tuple(d.get("instruments", ()) or ()),
            timeframe=d.get("timeframe"),
            start=d.get("start"),
            end=d.get("end"),
            source=d.get("source"),
            dataset_id=d.get("dataset_id"),
            dataset_version=d.get("dataset_version"),
            checksum=d.get("checksum"),
            n_bars=d.get("n_bars"),
        )


@dataclass(frozen=True)
class Provenance:
    """What exactly produced a result (code, data, config, experiment, evaluation)."""

    run_id: str
    experiment_id: Optional[str] = None
    git: GitIdentity = field(default_factory=GitIdentity)
    code_version: Optional[str] = None
    data: DataIdentity = field(default_factory=DataIdentity)
    strategy_identity: Optional[str] = None
    execution_config: Optional[Mapping[str, Any]] = None
    evaluation_config: Optional[Mapping[str, Any]] = None
    execution_config_hash: Optional[str] = None
    evaluation_config_hash: Optional[str] = None
    created_at: Optional[str] = None
    evaluation_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "git": self.git.to_dict(),
            "code_version": self.code_version,
            "data": self.data.to_dict(),
            "strategy_identity": self.strategy_identity,
            "execution_config": dict(self.execution_config)
            if self.execution_config is not None
            else None,
            "evaluation_config": dict(self.evaluation_config)
            if self.evaluation_config is not None
            else None,
            "execution_config_hash": self.execution_config_hash,
            "evaluation_config_hash": self.evaluation_config_hash,
            "created_at": self.created_at,
            "evaluation_id": self.evaluation_id,
            "parent_run_id": self.parent_run_id,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Provenance":
        return cls(
            run_id=d["run_id"],
            experiment_id=d.get("experiment_id"),
            git=GitIdentity.from_dict(d.get("git") or {}),
            code_version=d.get("code_version"),
            data=DataIdentity.from_dict(d.get("data") or {}),
            strategy_identity=d.get("strategy_identity"),
            execution_config=d.get("execution_config"),
            evaluation_config=d.get("evaluation_config"),
            execution_config_hash=d.get("execution_config_hash"),
            evaluation_config_hash=d.get("evaluation_config_hash"),
            created_at=d.get("created_at"),
            evaluation_id=d.get("evaluation_id"),
            parent_run_id=d.get("parent_run_id"),
            notes=tuple(d.get("notes", ()) or ()),
        )
