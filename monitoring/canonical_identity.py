"""
NestQuant S8.6.2 — Canonical Strategy Identity
================================================

Resolves the three-configuration ambiguity:
1. signals/breakout.py — actual code (no BE/MH)
2. config/experiment.py — intended config (with BE/MH)
3. config/settings.py — legacy config (different ATR/RRR)

This module defines the SINGLE source of truth for what the
deployed strategy actually is.

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
# Canonical Strategy Parameters
# ─────────────────────────────────────────────────────────────────────

# These are the EXACT parameters in signals/breakout.py RESEARCH_DEFAULTS
# Any future changes to breakout.py must update this simultaneously.
CANONICAL_STRATEGY_PARAMS: dict[str, Any] = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
    # EXPLICITLY ABSENT (not implemented in breakout.py):
    # "breakeven_ratio": None,
    # "max_hold_days": None,
    # "trailing_stop": None,
    # "session_filter": None,
    # "macro_filter": None,
}

# Features that are DEFINITELY NOT in the deployed strategy
# These are documented here to prevent accidental inclusion
CANONICAL_ABSENT_FEATURES: list[str] = [
    "breakeven_ratio",
    "max_hold_days",
    "trailing_stop",
    "session_filter",
    "macro_ema_filter",
    "news_filter",
    "regime_filter",
]


@dataclass(frozen=True)
class CanonicalStrategyIdentity:
    """
    The SINGLE source of truth for what the deployed strategy is.

    This describes signals/breakout.py as it actually exists.
    Not what ExperimentConfig declares. Not what settings.py says.
    """
    name: str = "breakout"
    version: str = "1.0.0"
    code_path: str = "signals/breakout.py"
    parameters: dict[str, Any] = field(
        default_factory=lambda: dict(CANONICAL_STRATEGY_PARAMS)
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
        """Deterministic hash of the canonical configuration."""
        canonical = json.dumps({
            "name": self.name,
            "version": self.version,
            "parameters": self.parameters,
            "timeframe": self.timeframe,
            "instruments": sorted(self.instruments),
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "code_path": self.code_path,
            "parameters": self.parameters,
            "absent_features": self.absent_features,
            "timeframe": self.timeframe,
            "instruments": list(self.instruments),
            "config_hash": self.config_hash(),
        }

    def summary(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        absent = ", ".join(self.absent_features)
        return (
            f"Canonical: {self.name} v{self.version} | "
            f"Params: {params} | "
            f"Absent: {absent} | "
            f"Hash: {self.config_hash()}"
        )


# ─────────────────────────────────────────────────────────────────────
# Population Mismatch Documentation
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PopulationMismatch:
    """Documents a mismatch between deployed strategy and research population."""
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
    lines.append("CONCLUSION: NO historical population exactly matches the deployed strategy.")
    lines.append("S6A/S5.5 is the CLOSEST available but uses breakeven/max_hold.")
    lines.append("A re-run without BE/MH is needed for exact calibration.")
    return "\n".join(lines)
