"""NestQuant shadow execution package (S7 SHADOW ONLY — no broker).

Public surface:
  ShadowCausalSignalGenerator, ShadowSignalRecord,
  ShadowLogger, HealthMonitor, KillSwitch, ShadowState, ShadowRunner
"""

from nestquant.execution.shadow.health import HealthMonitor, HealthSnapshot
from nestquant.execution.shadow.kill_switch import KillSwitch
from nestquant.execution.shadow.logger import ShadowLogger
from nestquant.execution.shadow.runner import ShadowRunner, ShadowRunSummary
from nestquant.execution.shadow.signal_generator import (
    BARS_PER_DAY_4H,
    BREAKEVEN_RATIO,
    LOOKBACK,
    MAX_HOLD_DAYS,
    RRR,
    ShadowCausalSignalGenerator,
    ShadowSignalRecord,
    STRATEGY_PARAMS,
)
from nestquant.execution.shadow.state import ShadowState

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
