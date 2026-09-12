"""NestQuant shadow execution package (S7 SHADOW ONLY — no broker).

Public surface:
  ShadowCausalSignalGenerator, ShadowSignalRecord,
  ShadowLogger, HealthMonitor, KillSwitch, ShadowState, ShadowRunner
"""

from nestquant.production.execution.shadow.health import HealthMonitor, HealthSnapshot
from nestquant.production.execution.shadow.kill_switch import KillSwitch
from nestquant.production.execution.shadow.logger import ShadowLogger
from nestquant.production.execution.shadow.runner import ShadowRunner, ShadowRunSummary
from nestquant.production.execution.shadow.signal_generator import (
    BARS_PER_DAY_4H,
    BREAKEVEN_RATIO,
    LOOKBACK,
    MAX_HOLD_DAYS,
    RRR,
    ShadowCausalSignalGenerator,
    ShadowSignalRecord,
    STRATEGY_PARAMS,
)
from nestquant.production.execution.shadow.state import ShadowState

__all__ = [
    "ShadowCausalSignalGenerator",
    "ShadowSignalRecord",
    "ShadowLogger",
    "HealthMonitor",
    "HealthSnapshot",
    "KillSwitch",
    "ShadowState",
    "ShadowRunner",
    "ShadowRunSummary",
    "LOOKBACK",
    "RRR",
    "STRATEGY_PARAMS",
    "BARS_PER_DAY_4H",
    "MAX_HOLD_DAYS",
    "BREAKEVEN_RATIO",
]
