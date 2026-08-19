"""
NestQuant Live Parameter Policy — Immutable Models
===================================================
Defines the research → live parameter contract.

All policy objects are frozen dataclasses. Once created, they cannot be mutated.
This ensures that the parameter set used for live trading is a faithful
transcription of the research result, not a mutable working copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class StrategyParams:
    """Strategy parameters — the statistical signal configuration."""

    z_entry_threshold: float = 2.2
    z_exit_threshold: float = 0.5
    lookback: int = 20
    atr_period: int = 14
    atr_sl_multiplier: float = 3.0
    rrr: float = 2.0
    min_divergence: float = 10.0
    breakeven_ratio: float = 1.5
    enable_macro_filter: bool = True


@dataclass(frozen=True)
class ExecutionParams:
    """Execution parameters — how orders reach the market."""

    max_lot: float = 0.20
    min_lot: float = 0.01
    max_open_trades: int = 1
    max_per_currency_block: int = 1
    max_concurrent_positions: int = 1
    commission_per_lot: float = 6.0
    slippage_pips: float = 0.1
    default_spread_pips: float = 0.5


@dataclass(frozen=True)
class RiskParams:
    """Risk parameters — position sizing and drawdown management."""

    risk_per_trade: float = 0.02
    initial_balance: float = 200.0
    max_dd_pct: float = 55.0
    dd_reduce_threshold: float = 30.0
    dd_reduced_risk: float = 0.02
    enable_recovery: bool = True
    dynamic_lot_scaling: bool = True
    max_position_risk_pct: float = 1.0


@dataclass(frozen=True)
class HardLimits:
    """Hard safety limits — non-negotiable kill switches.

    These are the absolute boundaries that trigger immediate action.
    soft_dd < hard_dd by construction (validated).
    """

    hard_dd_pct: float = 8.0
    soft_dd_pct: float = 6.0
    max_consecutive_losses: int = 5
    daily_loss_limit_pct: float = 0.03
    floating_loss_kill_threshold: float = -15.0


@dataclass(frozen=True)
class LiveParameterPolicy:
    """Immutable contract between research and live execution.

    A LiveParameterPolicy is created from a research run and passed
    unchanged to the live engine. It must never be modified after creation.

    Attributes:
        policy_version: Semver string identifying the policy schema.
        research_run_id: Unique identifier for the research run that produced
                         these parameters.
        strategy: Statistical signal parameters.
        execution: Order routing and sizing parameters.
        risk: Position sizing and drawdown management parameters.
        hard_limits: Non-negotiable safety boundaries.
    """

    policy_version: str = "1.0.0"
    research_run_id: str = ""
    strategy: StrategyParams = field(default_factory=StrategyParams)
    execution: ExecutionParams = field(default_factory=ExecutionParams)
    risk: RiskParams = field(default_factory=RiskParams)
    hard_limits: HardLimits = field(default_factory=HardLimits)
