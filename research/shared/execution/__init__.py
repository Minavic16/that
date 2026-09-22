"""Strategy-agnostic execution core for research backtesting.

This package owns signal-intent execution, portfolio state, fills, and
result metrics. It must not import production strategy or risk modules.
"""

from nestquant.research.shared.execution.contracts import (
    BacktestConfig,
    SignalIntent,
    Trade,
    to_signal_intent,
)
from nestquant.research.shared.execution.portfolio import Portfolio
from nestquant.research.shared.execution.simulator import ExecutionSimulator

__all__ = [
    "BacktestConfig",
    "ExecutionSimulator",
    "Portfolio",
    "SignalIntent",
    "Trade",
    "to_signal_intent",
]
