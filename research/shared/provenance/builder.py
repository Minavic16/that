"""build_provenance — construct Provenance from layered ROS objects."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from nestquant.research.shared.provenance.contracts import (
    DataIdentity,
    GitIdentity,
    Provenance,
)
from nestquant.research.shared.provenance.identity import (
    config_hash,
    get_git_commit,
    get_git_dirty,
    new_run_id,
    now_iso,
)


def _as_mapping(obj: Any) -> Optional[Mapping[str, Any]]:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    return None


def _execution_fields(execution: Any) -> tuple[Optional[Mapping[str, Any]], Optional[str]]:
    if execution is None:
        return None, None
    # BacktestConfig / ExecutionSimulator / engine
    cfg = getattr(execution, "config", None)
    if cfg is not None and hasattr(cfg, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(cfg), getattr(execution, "__class__", type(execution)).__name__
    if hasattr(execution, "to_dict"):
        return execution.to_dict(), type(execution).__name__
    m = _as_mapping(execution)
    if m is not None:
        return dict(m), None
    return None, None


def _evaluation_fields(evaluation: Any) -> tuple[Optional[Mapping[str, Any]], Optional[str], Optional[str]]:
    """Return (config_dict, evaluation_id, evaluation_status)."""
    if evaluation is None:
        return None, None, None
    if hasattr(evaluation, "configuration") and hasattr(evaluation, "evaluation_id"):
        # EvaluationResult
        return (
            evaluation.configuration.to_dict(),
            evaluation.evaluation_id,
            getattr(evaluation.status, "value", str(evaluation.status)),
        )
    if hasattr(evaluation, "to_dict") and not hasattr(evaluation, "configuration"):
        # EvaluationConfig
        return evaluation.to_dict(), None, None
    m = _as_mapping(evaluation)
    if m is None:
        return None, None, None
    if "configuration" in m and "evaluation_id" in m:
        return (
            m.get("configuration") or {},
            m.get("evaluation_id"),
            m.get("status"),
        )
    if "evaluation_id" in m:
        return m.get("configuration") or {}, m.get("evaluation_id"), m.get("status")
    return dict(m), None, None


def _experiment_id(experiment: Any) -> Optional[str]:
    if experiment is None:
        return None
    if isinstance(experiment, Mapping):
        return experiment.get("experiment_id") or experiment.get("id")
    return getattr(experiment, "experiment_id", None)


def _data_identity(data: Any) -> DataIdentity:
    if data is None:
        return DataIdentity()
    if isinstance(data, DataIdentity):
        return data
    m = _as_mapping(data)
    if m is None:
        return DataIdentity()
    # mapping-shaped data identity (DataIdentity dict or record-like fields)
    instruments = m.get("instruments") or ()
    if isinstance(instruments, str):
        instruments = (instruments,)
    date_range = m.get("date_range") or m.get("window")
    start = m.get("start") or m.get("start_timestamp")
    end = m.get("end") or m.get("end_timestamp")
    if date_range and isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start = start or date_range[0]
        end = end or date_range[1]
    return DataIdentity(
        instruments=tuple(instruments),
        timeframe=m.get("timeframe"),
        start=str(start) if start else None,
        end=str(end) if end else None,
        source=m.get("source") or m.get("data_source") or m.get("path"),
        dataset_id=m.get("dataset_id"),
        dataset_version=m.get("dataset_version") or m.get("version"),
        checksum=m.get("checksum") or m.get("raw_checksum") or m.get("checksum_sha256"),
        n_bars=m.get("n_bars"),
    )


def build_provenance(
    *,
    execution: Any = None,
    evaluation: Any = None,
    experiment: Any = None,
    data: Any = None,
    run_id: Optional[str] = None,
    strategy_identity: Optional[str] = None,
    cwd: Optional[str] = None,
    created_at: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    notes: tuple[str, ...] = (),
) -> Provenance:
    """Construct experiment-agnostic Provenance.

    Does not require Strategy 2. Unavailable values remain None (fail closed).
    """
    exec_cfg, exec_src = _execution_fields(execution)
    eval_cfg, eval_id, eval_status = _evaluation_fields(evaluation)
    exp_id = _experiment_id(experiment)

    commit = get_git_commit(cwd=cwd)
    dirty = get_git_dirty(cwd=cwd)

    return Provenance(
        run_id=run_id or new_run_id(),
        experiment_id=exp_id,
        git=GitIdentity(
            commit=commit,
            dirty=dirty,
            available=commit is not None,
        ),
        code_version=commit,
        data=_data_identity(data),
        strategy_identity=strategy_identity or exec_src,
        execution_config=exec_cfg,
        evaluation_config=eval_cfg,
        execution_config_hash=config_hash(exec_cfg),
        evaluation_config_hash=config_hash(eval_cfg),
        created_at=created_at or now_iso(),
        evaluation_id=eval_id,
        evaluation_status=eval_status,
        parent_run_id=parent_run_id,
        notes=tuple(notes),
    )
