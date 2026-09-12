"""
NestQuant Constitution Risk Configuration — Single Source of Truth
==================================================================
The canonical risk parameters for the NestQuant trading system.

THIS IS THE AUTHORITATIVE SOURCE for all risk limits.
All risk components MUST consume these values.

These values are FROZEN. Do not modify without explicit authorization.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstitutionRiskConfig:
    """Frozen constitution risk parameters.

    These values define the mandatory risk boundaries for the
    NestQuant trading system. Every risk guard, circuit breaker,
    and execution path must respect these limits.

    Source: AGENTS.md constitution §2, §9, §12
    """

    # --- Per-trade risk ---
    risk_per_trade_pct: float = 0.0015  # 0.15% of equity per trade

    # --- Position limits ---
    max_concurrent_positions: int = 3
    max_position_size_per_pair: float = 0.10  # lots
    max_total_exposure: float = 3.0  # lots total

    # --- Loss limits ---
    max_daily_loss_pct: float = 0.03  # 3% of equity
    max_drawdown_pct: float = 0.08  # 8% of equity (hard safety)

    # --- Trade frequency ---
    max_trades_per_day: int = 4


# The single authoritative instance
CONSTITUTION = ConstitutionRiskConfig()
