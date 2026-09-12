"""
NestQuant S8 — Experiment Identity and Configuration
=====================================================
Provides reproducible experiment tracking for live validation.

Every S8 experiment run gets a unique ID, records its configuration,
and produces a deterministic config hash. This ensures that six months
from now, we can answer: "Which exact strategy configuration produced
this trade?"

This module does NOT:
  - Import MT5 or broker SDKs
  - Make network calls
  - Perform strategy calculations
  - Perform risk calculations
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Experiment phases
# ---------------------------------------------------------------------------


class ExperimentPhase:
    """Experiment lifecycle phases."""

    INITIALIZING = "INITIALIZING"
    HEALTH_CHECK = "HEALTH_CHECK"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


# ---------------------------------------------------------------------------
# Strategy identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyIdentity:
    """Identifies a specific strategy version and its frozen parameters.

    Variant A — Historically Validated (S0, S5.5, S6A).
    Includes breakeven, max hold, and trailing stop as validated components.
    """

    name: str = "breakout"
    version: str = "1.0.0"
    parameters: dict[str, Any] = field(default_factory=lambda: {
        # Signal parameters (from RESEARCH_DEFAULTS)
        "lookback": 5,
        "atr_period": 14,
        "atr_sl_multiplier": 2.0,
        "rrr": 3.5,
        # Trade management (validated in S0/S5.5/S6A)
        "breakeven_ratio": 0.8,
        "breakeven_enabled": True,
        "max_hold_days": 7,
        "max_hold_bars": 42,  # 7 days * 6 bars/day (4h)
        "trailing_enabled": True,
        "trailing_type": "swing_based",
    })
    timeframe: str = "4h"

    def config_hash(self) -> str:
        """Deterministic SHA256 of strategy name + version + parameters.

        Two experiments with identical StrategyIdentity produce identical hashes.
        """
        canonical = json.dumps({
            "name": self.name,
            "version": self.version,
            "parameters": self.parameters,
            "timeframe": self.timeframe,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Risk identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskIdentity:
    """Risk configuration for the experiment. Separate from strategy."""

    risk_per_trade_pct: float = 0.0015  # 0.15% of $200K = $300 per 1R
    max_concurrent_positions: int = 3
    max_position_size_per_pair: float = 0.10  # lots
    max_total_exposure: float = 3.0  # lots
    max_daily_loss_pct: float = 0.03  # 3% of equity
    max_drawdown_pct: float = 0.08  # 8% of equity (hard safety)
    max_trades_per_day: int = 4

    def config_hash(self) -> str:
        """Deterministic SHA256 of risk parameters."""
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Universe identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseIdentity:
    """Which instruments are tradeable."""

    pairs: tuple[str, ...] = (
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
        "NZD/USD", "EUR/JPY", "GBP/JPY",
    )

    def config_hash(self) -> str:
        canonical = json.dumps({"pairs": sorted(self.pairs)}, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentConfig:
    """Complete experiment identity. Immutable once created.

    Every field is frozen. The config_hash is deterministic and
    reproducible. This is the scientific fingerprint of the experiment.
    """

    experiment_id: str = field(default_factory=lambda: f"S8-{uuid.uuid4().hex[:12]}")
    strategy: StrategyIdentity = field(default_factory=StrategyIdentity)
    risk: RiskIdentity = field(default_factory=RiskIdentity)
    universe: UniverseIdentity = field(default_factory=UniverseIdentity)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    operator: str = "nestquant-s8"
    environment: str = "prop-firm-challenge"
    notes: str = ""

    def full_config_hash(self) -> str:
        """Hash of all component hashes combined. The master fingerprint."""
        combined = (
            self.strategy.config_hash()
            + self.risk.config_hash()
            + self.universe.config_hash()
        )
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging and storage."""
        return {
            "experiment_id": self.experiment_id,
            "strategy": asdict(self.strategy),
            "strategy_config_hash": self.strategy.config_hash(),
            "risk": asdict(self.risk),
            "risk_config_hash": self.risk.config_hash(),
            "universe": asdict(self.universe),
            "universe_config_hash": self.universe.config_hash(),
            "full_config_hash": self.full_config_hash(),
            "created_at": self.created_at,
            "operator": self.operator,
            "environment": self.environment,
            "notes": self.notes,
        }

    def summary(self) -> str:
        """Human-readable summary for logging."""
        return (
            f"Experiment {self.experiment_id} | "
            f"Strategy: {self.strategy.name} v{self.strategy.version} | "
            f"Risk: {self.risk.risk_per_trade_pct:.2%}/trade | "
            f"Universe: {len(self.universe.pairs)} pairs | "
            f"Hash: {self.full_config_hash()}"
        )

    def __repr__(self) -> str:
        return f"<ExperimentConfig({self.experiment_id}, hash={self.full_config_hash()})>"
