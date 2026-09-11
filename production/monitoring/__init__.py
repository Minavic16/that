"""
NestQuant Monitoring — Evidence-Based Observability
===================================================

Four-layer monitoring architecture:
- Layer 1: Observation (raw facts)
- Layer 2: Statistical Engine (distributions, percentiles)
- Layer 3: Monitoring Classification (NORMAL/ELEVATED/WARNING/EXTREME)
- Layer 4: Decision Engine (hard safety + statistical → trading decisions)

Components:
- Percentile framework with sample-size discipline
- EV stability analysis
- Drawdown clustering analysis
- Circuit breaker calibration
- Passive market/infrastructure collectors
- Canonical strategy identity
- Data schema for future calibration
"""

from monitoring.percentiles import PercentileResult, compute_percentiles
from monitoring.ev_stability import EVStabilityAnalyzer
from monitoring.dd_clustering import DDClusterAnalyzer
from monitoring.architecture import (
    MetricState,
    MetricDirection,
    MetricClassification,
    MonitoringClassification,
    classify_percentile,
)
from monitoring.decision import (
    DecisionAction,
    DecisionSource,
    Decision,
    HardSafetyLimits,
    DecisionEngine,
)
from monitoring.canonical_identity import (
    CanonicalStrategyIdentity,
    PopulationMismatch,
    KNOWN_POPULATIONS,
    get_population_summary,
)

__all__ = [
    "PercentileResult",
    "compute_percentiles",
    "EVStabilityAnalyzer",
    "DDClusterAnalyzer",
    "MetricState",
    "MetricDirection",
    "MetricClassification",
    "MonitoringClassification",
    "classify_percentile",
    "DecisionAction",
    "DecisionSource",
    "Decision",
    "HardSafetyLimits",
    "DecisionEngine",
    "CanonicalStrategyIdentity",
    "PopulationMismatch",
    "KNOWN_POPULATIONS",
    "get_population_summary",
]
