"""
Experiment tracking for model versions and research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Experiment:
    """Represents a single experiment."""

    name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    status: str = "running"

    @property
    def duration(self) -> Optional[float]:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class ExperimentTracker:
    """
    Track experiments for model versions and research.

    Provides simple experiment logging without external dependencies.
    """

    def __init__(self):
        self._experiments: list[Experiment] = []
        self._current: Optional[Experiment] = None

    def start_experiment(
        self,
        name: str,
        params: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> Experiment:
        """
        Start a new experiment.

        Args:
            name: Experiment name
            params: Experiment parameters
            tags: Optional tags for categorization

        Returns:
            Started Experiment
        """
        experiment = Experiment(
            name=name,
            params=params or {},
            tags=tags or [],
        )
        self._current = experiment
        self._experiments.append(experiment)
        return experiment

    def log_metric(self, name: str, value: float) -> None:
        """
        Log a metric to the current experiment.

        Args:
            name: Metric name
            value: Metric value
        """
        if self._current:
            self._current.metrics[name] = value

    def log_params(self, params: dict[str, Any]) -> None:
        """
        Log parameters to the current experiment.

        Args:
            params: Parameters to log
        """
        if self._current:
            self._current.params.update(params)

    def log_artifact(self, name: str, path: str) -> None:
        """
        Log an artifact (file) to the current experiment.

        Args:
            name: Artifact name
            path: File path
        """
        if self._current:
            self._current.artifacts[name] = path

    def end_experiment(self, status: str = "completed") -> None:
        """
        End the current experiment.

        Args:
            status: Final status (completed, failed, etc.)
        """
        if self._current:
            self._current.end_time = datetime.now()
            self._current.status = status
            self._current = None

    def get_experiments(
        self,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[Experiment]:
        """
        Get experiments with optional filters.

        Args:
            name: Filter by experiment name
            status: Filter by status

        Returns:
            List of matching experiments
        """
        experiments = self._experiments

        if name:
            experiments = [e for e in experiments if e.name == name]

        if status:
            experiments = [e for e in experiments if e.status == status]

        return experiments

    def get_best_experiment(
        self,
        metric: str = "sharpe_ratio",
        minimize: bool = False,
    ) -> Optional[Experiment]:
        """
        Get the best experiment by a metric.

        Args:
            metric: Metric to optimize
            minimize: If True, minimize metric; otherwise maximize

        Returns:
            Best experiment or None
        """
        completed = [e for e in self._experiments if e.status == "completed"]
        if not completed:
            return None

        def get_metric(exp: Experiment) -> float:
            return exp.metrics.get(metric, float("-inf") if not minimize else float("inf"))

        return min(completed, key=get_metric) if minimize else max(completed, key=get_metric)
