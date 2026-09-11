"""
NestQuant S8.6.2 — Monitoring Architecture
============================================

Four-layer monitoring architecture:

Layer 1 — Observation
    Collect raw facts. No decisions.

Layer 2 — Statistical Engine
    Calculate distributions, percentiles, rolling stats.
    Still no trading decisions.

Layer 3 — Monitoring Classification
    Classify observations into states:
        NORMAL / ELEVATED / WARNING / EXTREME
    Direction depends on metric (high=bad for slippage, low=bad for EV).

Layer 4 — Decision Engine
    Combine classifications into trading decisions.
    Hard safety limits bypass statistical classification.
    Statistical anomalies alone should NOT trigger hard halts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# Layer 3: Monitoring Classification
# ─────────────────────────────────────────────────────────────────────

class MetricState(Enum):
    """Classification state for a monitored metric."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    WARNING = "WARNING"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class MetricDirection(Enum):
    """Whether high values are bad (HIGH_IS_BAD) or low values are bad (LOW_IS_BAD)."""
    HIGH_IS_BAD = "HIGH_IS_BAD"
    LOW_IS_BAD = "LOW_IS_BAD"
    BIDIRECTIONAL = "BIDIRECTIONAL"


@dataclass
class MetricClassification:
    """Result of classifying a single metric."""
    metric_name: str
    value: float
    state: MetricState
    direction: MetricDirection
    percentile: Optional[float] = None
    z_score: Optional[float] = None
    sample_size: int = 0
    is_provisional: bool = True
    notes: str = ""


@dataclass
class MonitoringClassification:
    """Complete classification of all monitored metrics."""
    timestamp: str = ""
    metrics: list[MetricClassification] = field(default_factory=list)

    def add(self, mc: MetricClassification) -> None:
        self.metrics.append(mc)

    def get(self, name: str) -> Optional[MetricClassification]:
        for m in self.metrics:
            if m.metric_name == name:
                return m
        return None

    @property
    def any_warning(self) -> bool:
        return any(m.state in (MetricState.WARNING, MetricState.EXTREME) for m in self.metrics)

    @property
    def any_extreme(self) -> bool:
        return any(m.state == MetricState.EXTREME for m in self.metrics)

    @property
    def warning_count(self) -> int:
        return sum(1 for m in self.metrics if m.state == MetricState.WARNING)

    @property
    def extreme_count(self) -> int:
        return sum(1 for m in self.metrics if m.state == MetricState.EXTREME)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "any_warning": self.any_warning,
            "any_extreme": self.any_extreme,
            "warning_count": self.warning_count,
            "extreme_count": self.extreme_count,
            "metrics": [
                {
                    "name": m.metric_name,
                    "value": m.value,
                    "state": m.state.value,
                    "direction": m.direction.value,
                    "percentile": m.percentile,
                    "z_score": m.z_score,
                    "sample_size": m.sample_size,
                    "is_provisional": m.is_provisional,
                    "notes": m.notes,
                }
                for m in self.metrics
            ],
        }


# ─────────────────────────────────────────────────────────────────────
# Layer 3: Percentile-Based Classifier
# ─────────────────────────────────────────────────────────────────────

def classify_percentile(
    value: float,
    percentiles: dict[str, float],
    direction: MetricDirection,
    metric_name: str = "",
    sample_size: int = 0,
    is_provisional: bool = True,
) -> MetricClassification:
    """
    Classify a metric value using percentile thresholds.

    percentiles should contain keys like:
        "p25", "p50", "p75", "p90", "p95", "p99"

    For HIGH_IS_BAD (e.g., slippage, spread):
        < p75  = NORMAL
        p75-p90 = ELEVATED
        p90-p95 = WARNING
        > p95   = EXTREME

    For LOW_IS_BAD (e.g., EV, win rate):
        > p25  = NORMAL
        p10-p25 = ELEVATED
        p5-p10  = WARNING
        < p5    = EXTREME
    """
    if direction == MetricDirection.HIGH_IS_BAD:
        p75 = percentiles.get("p75", 0)
        p90 = percentiles.get("p90", 0)
        p95 = percentiles.get("p95", 0)

        if value > p95:
            state = MetricState.EXTREME
        elif value > p90:
            state = MetricState.WARNING
        elif value > p75:
            state = MetricState.ELEVATED
        else:
            state = MetricState.NORMAL

    elif direction == MetricDirection.LOW_IS_BAD:
        p25 = percentiles.get("p25", 0)
        p10 = percentiles.get("p10", 0)
        p5 = percentiles.get("p5", 0)

        if value < p5:
            state = MetricState.EXTREME
        elif value < p10:
            state = MetricState.WARNING
        elif value < p25:
            state = MetricState.ELEVATED
        else:
            state = MetricState.NORMAL

    else:
        state = MetricState.UNKNOWN

    # Calculate percentile if we have enough data
    pctile = None
    if sample_size > 0:
        vals = sorted(percentiles.values())
        above = sum(1 for v in vals if v <= value)
        pctile = above / len(vals) * 100 if vals else None

    return MetricClassification(
        metric_name=metric_name,
        value=value,
        state=state,
        direction=direction,
        percentile=pctile,
        sample_size=sample_size,
        is_provisional=is_provisional,
    )
