"""Z-Score Research Engine — Experiment Configuration & Reproducibility."""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


def _get_git_commit() -> str:
    """Return current Git commit hash, or 'unknown' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def _get_git_dirty() -> bool:
    """Return True if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return len(result.stdout.strip()) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False


@dataclass
class ExperimentConfig:
    """Reproducible experiment configuration.

    All fields are serializable to JSON. No external dependencies beyond stdlib.
    """
    experiment_id: str
    git_commit: str = ""
    git_dirty: bool = False
    created_at: str = ""
    dataset_version: str = ""
    data_source: str = ""
    instruments: list[str] = field(default_factory=list)
    timeframe: str = ""
    date_range: tuple[str, str] = ("", "")
    timezone: str = "UTC"
    spread_pips: dict[str, float] = field(default_factory=dict)
    commission_per_lot: float = 0.0
    slippage_pips: float = 0.0
    execution_delay_bars: int = 0
    strategy_params: dict[str, float | int | str | bool] = field(default_factory=dict)
    random_seed: int | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.git_commit:
            self.git_commit = _get_git_commit()
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        self.git_dirty = _get_git_dirty()

    def to_dict(self) -> dict:
        """Convert to plain dict for serialization."""
        d = asdict(self)
        d["date_range"] = list(d["date_range"])
        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: str) -> None:
        """Save configuration to JSON file."""
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> ExperimentConfig:
        """Load configuration from JSON file."""
        with open(path) as f:
            data = json.load(f)
        data["date_range"] = tuple(data["date_range"])
        return cls(**data)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Experiment: {self.experiment_id}",
            f"Git: {self.git_commit[:8]}{' (dirty)' if self.git_dirty else ''}",
            f"Created: {self.created_at}",
            f"Instruments: {', '.join(self.instruments) if self.instruments else 'none'}",
            f"Timeframe: {self.timeframe}",
            f"Date range: {self.date_range[0]} to {self.date_range[1]}",
            f"Spread: {self.spread_pips}",
            f"Commission: {self.commission_per_lot}",
            f"Slippage: {self.slippage_pips} pips",
        ]
        if self.strategy_params:
            lines.append("Strategy params:")
            for k, v in self.strategy_params.items():
                lines.append(f"  {k}: {v}")
        if self.random_seed is not None:
            lines.append(f"Random seed: {self.random_seed}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)
