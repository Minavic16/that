"""
NestQuant S8.6.2 — Canonical Strategy Identity
===============================================

Defines the SINGLE source of truth for the deployed NestQuant strategy.

The strategy has two distinct parameter sets:

A. SIGNAL GENERATION (entry decision)
   Defined in: signals/breakout.py RESEARCH_DEFAULTS
   Parameters: lookback, atr_period, atr_sl_multiplier, rrr
   These determine WHEN a trade signal is generated.

B. POSITION LIFECYCLE (exit management)
   Defined in: execution/shadow/signal_generator.py STRATEGY_PARAMS
              execution/shadow/runner.py ShadowPosition
              execution/shadow/live_executor.py
              execution/s8_runtime.py LifecycleRegistry
              strategy/trade_management/breakeven.py
              strategy/trade_management/max_hold.py
              strategy/trade_management/trailing_stop.py
   Parameters: breakeven_ratio, max_hold_days, trailing_enabled
   These determine HOW a position is managed after entry.

C. RISK CONTRACT
   Defined in: config/experiment.py RiskIdentity
   Parameters: risk_per_trade, max_concurrent, max_daily_loss, etc.

DESIGN PRINCIPLE:
    The canonical identity describes what the CODE does,
    not what we wish it did.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────
# A. SIGNAL GENERATION PARAMETERS (entry decision)
# ─────────────────────────────────────────────────────────────────────

# These are the EXACT parameters in signals/breakout.py RESEARCH_DEFAULTS
# Any future changes to breakout.py must update this simultaneously.
CANONICAL_STRATEGY_PARAMS: dict[str, Any] = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
}

# Features ABSENT FROM SIGNAL GENERATION (breakout.py does not implement these).
# Note: breakeven, max_hold, and trailing ARE implemented in the position lifecycle
# layer (execution/shadow/ and strategy/trade_management/). They are listed here
# only to clarify they are NOT part of the signal entry decision.
CANONICAL_ABSENT_FEATURES: list[str] = [
    "session_filter",
    "macro_ema_filter",
    "news_filter",
    "regime_filter",
    "correlation_filter",
    "currency_strength_filter",
    "adx_filter",
]

# ─────────────────────────────────────────────────────────────────────
# B. POSITION LIFECYCLE PARAMETERS (exit management)
# ─────────────────────────────────────────────────────────────────────

# These parameters govern position management AFTER entry.
# They are implemented across the execution layer, NOT in signals/breakout.py.
# Source: execution/shadow/signal_generator.py STRATEGY_PARAMS (frozen Variant B)
#         execution/shadow/runner.py ShadowPosition
#         execution/shadow/live_executor.py
#         strategy/trade_management/breakeven.py, max_hold.py, trailing_stop.py
CANONICAL_LIFECYCLE_PARAMS: dict[str, Any] = {
    "breakeven_ratio": 0.8,        # Move SL to entry when profit >= 0.8R
    "breakeven_enabled": True,
    "max_hold_days": 7,            # Exit after 7 days
    "max_hold_bars": 42,           # 7 days × 6 bars/day (4H timeframe)
    "trailing_enabled": True,      # Swing-based trailing stop
    "trailing_type": "swing_based",
}

# ─────────────────────────────────────────────────────────────────────
# C. RISK CONTRACT PARAMETERS
# ─────────────────────────────────────────────────────────────────────

# Source: config/experiment.py RiskIdentity
CANONICAL_RISK_PARAMS: dict[str, Any] = {
    "risk_per_trade_pct": 0.0015,     # 0.15% of equity
    "max_concurrent_positions": 3,
    "max_position_size_per_pair": 0.10,  # lots
    "max_total_exposure": 3.0,           # lots
    "max_daily_loss_pct": 0.03,          # 3%
    "max_drawdown_pct": 0.08,            # 8%
    "max_trades_per_day": 4,
}


@dataclass(frozen=True)
class CanonicalStrategyIdentity:
    """
    The SINGLE source of truth for what the deployed strategy is.

    This describes signals/breakout.py as it actually exists.
    Not what ExperimentConfig declares. Not what settings.py says.

    The strategy has two parameter sets:
    - Signal parameters (what the signal generator uses)
    - Lifecycle parameters (what the execution layer uses for position management)
    """
    name: str = "breakout"
    version: str = "1.0.0"
    code_path: str = "signals/breakout.py"
    parameters: dict[str, Any] = field(
        default_factory=lambda: dict(CANONICAL_STRATEGY_PARAMS)
    )
    lifecycle_parameters: dict[str, Any] = field(
        default_factory=lambda: dict(CANONICAL_LIFECYCLE_PARAMS)
    )
    risk_parameters: dict[str, Any] = field(
        default_factory=lambda: dict(CANONICAL_RISK_PARAMS)
    )
    absent_features: list[str] = field(
        default_factory=lambda: list(CANONICAL_ABSENT_FEATURES)
    )
    timeframe: str = "4h"
    instruments: tuple[str, ...] = (
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
        "NZD/USD", "EUR/JPY", "GBP/JPY",
    )

    def config_hash(self) -> str:
        """Deterministic hash of the canonical signal configuration."""
        canonical = json.dumps({
            "name": self.name,
            "version": self.version,
            "parameters": self.parameters,
            "timeframe": self.timeframe,
            "instruments": sorted(self.instruments),
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def full_config_hash(self) -> str:
        """Deterministic hash of all canonical parameters (signal + lifecycle + risk)."""
        canonical = json.dumps({
            "signal": self.parameters,
            "lifecycle": self.lifecycle_parameters,
            "risk": self.risk_parameters,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "code_path": self.code_path,
            "signal_parameters": self.parameters,
            "lifecycle_parameters": self.lifecycle_parameters,
            "risk_parameters": self.risk_parameters,
            "absent_features": self.absent_features,
            "timeframe": self.timeframe,
            "instruments": list(self.instruments),
            "config_hash": self.config_hash(),
            "full_config_hash": self.full_config_hash(),
        }

    def summary(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        lifecycle = ", ".join(f"{k}={v}" for k, v in self.lifecycle_parameters.items())
        absent = ", ".join(self.absent_features)
        return (
            f"Canonical: {self.name} v{self.version} | "
            f"Signal: {params} | "
            f"Lifecycle: {lifecycle} | "
            f"Absent from signal: {absent} | "
            f"Hash: {self.config_hash()}"
        )


# ─────────────────────────────────────────────────────────────────────
# Population Mismatch Documentation
# ─────────────────────────────────────────────────────────────────────

# NOTE: PopulationMismatch documents whether research backtest populations
# match the DEPLOYED SIGNAL GENERATION (breakout.py parameters).
# The presence of breakeven/max_hold in a research population does NOT mean
# those features are absent from the deployed system — they are implemented
# in the position lifecycle layer (execution/shadow/ + strategy/trade_management/).
# The mismatch is about whether the research used the SAME signal parameters
# as the deployed breakout.py.

@dataclass(frozen=True)
class PopulationMismatch:
    """Documents a mismatch between deployed signal generation and research population."""
    population_name: str
    source_file: str
    trade_count: int
    has_breakeven: bool
    has_max_hold: bool
    has_trailing: bool
    has_session_filter: bool
    has_macro_filter: bool
    win_rate: float
    profit_factor: float
    max_dd_r: float
    matches_deployed: bool
    mismatch_notes: str


# Known research populations and their match status
KNOWN_POPULATIONS: list[PopulationMismatch] = [
    PopulationMismatch(
        population_name="S0",
        source_file="research_data/simple_strategies/S0_breakout_results.json",
        trade_count=1002,
        has_breakeven=True,
        has_max_hold=True,
        has_trailing=False,
        has_session_filter=False,
        has_macro_filter=False,
        win_rate=0.730,
        profit_factor=5.32,
        max_dd_r=5.68,  # Approximate
        matches_deployed=False,
        mismatch_notes="Uses breakeven=0.8 and max_hold=7d — NOT in deployed code",
    ),
    PopulationMismatch(
        population_name="S6A",
        source_file="research_data/simple_strategies/S6_adaptive_risk_challenge.json",
        trade_count=15321,
        has_breakeven=True,
        has_max_hold=True,
        has_trailing=False,
        has_session_filter=False,
        has_macro_filter=False,
        win_rate=0.357,
        profit_factor=2.01,
        max_dd_r=19.61,
        matches_deployed=False,
        mismatch_notes=(
            "S6 script also hardcodes MAX_HOLD_DAYS=7 and BREAKEVEN_RATIO=0.8. "
            "Despite having more trades, still uses BE/MH that are NOT in deployed code. "
            "Closest available but NOT an exact match."
        ),
    ),
    PopulationMismatch(
        population_name="S5.5",
        source_file="research_data/simple_strategies/S5_5_failure_analysis.json",
        trade_count=15321,
        has_breakeven=True,
        has_max_hold=True,
        has_trailing=False,
        has_session_filter=False,
        has_macro_filter=False,
        win_rate=0.359,
        profit_factor=2.14,
        max_dd_r=19.61,
        matches_deployed=False,
        mismatch_notes="Same trade population as S6A, same BE/MH issue",
    ),
]


def get_population_summary() -> str:
    """Human-readable summary of population mismatch status."""
    lines = ["Population Match Assessment:"]
    for p in KNOWN_POPULATIONS:
        status = "MATCH" if p.matches_deployed else "MISMATCH"
        lines.append(
            f"  {p.population_name}: {status} | "
            f"n={p.trade_count}, WR={p.win_rate:.1%}, PF={p.profit_factor:.2f} | "
            f"BE={p.has_breakeven}, MH={p.has_max_hold} | "
            f"{p.mismatch_notes}"
        )
    lines.append("")
    lines.append("CONCLUSION: NO historical population exactly matches the deployed signal generation.")
    lines.append("S6A/S5.5 is the CLOSEST available but uses different signal parameters.")
    lines.append("Note: breakeven/max_hold ARE part of the deployed position lifecycle (not signal generation).")
    return "\n".join(lines)
