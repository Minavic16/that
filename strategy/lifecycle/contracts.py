"""
NestQuant Strategy — Lifecycle Data Contracts
==============================================

Immutable data objects representing the state of an active position
and the market context required for lifecycle evaluation.

Design principles:
- risk_pips is IMMUTABLE after entry (matches research)
- All fields are set at entry and updated only by lifecycle evaluation
- No broker-specific API coupling
- TradeGeometry is built from ACTUAL fill price, not signal level
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Direction(int, Enum):
    """Trade direction."""
    LONG = 1
    SHORT = -1


class ExitReason(str, Enum):
    """Reason for position exit."""
    STOP_LOSS = "SL"
    TAKE_PROFIT = "TP"
    MAX_HOLD = "MH"
    MANUAL = "MANUAL"
    RISK_GUARD = "RG"
    RECONCILIATION_GHOST = "RG_HOST"


class LifecycleAction(str, Enum):
    """Action returned by lifecycle evaluation."""
    HOLD = "HOLD"
    MOVE_STOP = "MOVE_STOP"
    EXIT = "EXIT"


@dataclass(frozen=True)
class TradeGeometry:
    """Fill-aware trade geometry.

    Built from ACTUAL broker fill price, not signal level.
    This matches the research engine's behavior where SL/TP/risk
    are anchored to the actual execution price.

    The signal provides:
        signal_level, stop_distance, rrr, direction

    The execution provides:
        fill_price

    TradeGeometry combines them:
        entry = fill_price
        sl = fill_price ± stop_distance
        tp = fill_price ± stop_distance * rrr
        risk_pips = stop_distance / pip
    """

    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pips: float
    pip_size: float
    direction: int  # 1 = LONG, -1 = SHORT
    stop_distance: float  # ATR * multiplier (in price units)

    @classmethod
    def from_fill(
        cls,
        fill_price: float,
        stop_distance: float,
        rrr: float,
        pip_size: float,
        direction: int,
    ) -> TradeGeometry:
        """Build geometry from actual broker fill.

        This is the ONLY way to create TradeGeometry.
        Signal-level prices must NOT be used directly.
        """
        risk_pips = stop_distance / pip_size

        if direction == 1:  # LONG
            sl = fill_price - stop_distance
            tp = fill_price + stop_distance * rrr
        else:  # SHORT
            sl = fill_price + stop_distance
            tp = fill_price - stop_distance * rrr

        return cls(
            entry_price=fill_price,
            stop_loss=sl,
            take_profit=tp,
            risk_pips=risk_pips,
            pip_size=pip_size,
            direction=direction,
            stop_distance=stop_distance,
        )

    def unrealized_r(self, current_price: float) -> float:
        """Current unrealized P&L in R-multiples."""
        if self.risk_pips <= 0:
            return 0.0
        if self.direction == 1:
            return (current_price - self.entry_price) / self.pip_size / self.risk_pips
        else:
            return (self.entry_price - current_price) / self.pip_size / self.risk_pips


@dataclass(frozen=True)
class RiskReconciliation:
    """Compares expected vs actual risk after fill."""

    expected_entry: float
    actual_entry: float
    expected_risk_pips: float
    actual_risk_pips: float
    entry_deviation_pips: float
    risk_deviation_pips: float
    within_tolerance: bool
    severity: str  # "OK" or "CRITICAL"

    @property
    def is_ok(self) -> bool:
        return self.within_tolerance

    @classmethod
    def from_reconciliation(
        cls,
        expected_entry: float,
        actual_entry: float,
        stop_distance: float,
        pip_size: float,
        tolerance_pips: float = 5.0,
    ) -> RiskReconciliation:
        """Build reconciliation from expected vs actual entry."""
        entry_deviation = abs(actual_entry - expected_entry) / pip_size
        risk_pips = stop_distance / pip_size
        # Risk is the same if SL moves with fill (fixed stop distance)
        risk_deviation = 0.0  # Fixed distance means no risk deviation

        within = entry_deviation <= tolerance_pips

        return cls(
            expected_entry=expected_entry,
            actual_entry=actual_entry,
            expected_risk_pips=risk_pips,
            actual_risk_pips=risk_pips,
            entry_deviation_pips=entry_deviation,
            risk_deviation_pips=risk_deviation,
            within_tolerance=within,
            severity="OK" if within else "CRITICAL",
        )


@dataclass(frozen=True)
class PositionLifecycleState:
    """Canonical state of an active strategy trade.

    Immutable after creation except for:
    - current_sl (updated by trailing/breakeven)
    - bars_held (incremented each bar)
    - breakeven_triggered (set once)

    risk_pips NEVER changes. This matches the research engine.
    """

    # Identity
    trade_id: str
    symbol: str
    direction: Direction
    strategy_identity: str  # config_hash

    # Entry (immutable)
    entry_price: float
    initial_sl: float
    take_profit: float
    risk_pips: float  # abs(entry - initial_sl) / pip — NEVER changes
    pip_size: float
    entry_time: datetime
    entry_bar_index: int

    # Mutable state
    current_sl: float = 0.0
    bars_held: int = 0
    breakeven_triggered: bool = False

    def __post_init__(self):
        if self.current_sl == 0.0:
            object.__setattr__(self, 'current_sl', self.initial_sl)

    @property
    def risk_reward_at_tp(self) -> float:
        """RRR from entry to TP."""
        if self.direction == Direction.LONG:
            return (self.take_profit - self.entry_price) / self.risk_pips / self.pip_size
        else:
            return (self.entry_price - self.take_profit) / self.risk_pips / self.pip_size

    def unrealized_r(self, current_price: float) -> float:
        """Current unrealized P&L in R-multiples."""
        if self.risk_pips <= 0:
            return 0.0
        if self.direction == Direction.LONG:
            return (current_price - self.entry_price) / self.pip_size / self.risk_pips
        else:
            return (self.entry_price - current_price) / self.pip_size / self.risk_pips


@dataclass(frozen=True)
class MarketContext:
    """Market data required for lifecycle evaluation.

    swing_low and swing_high are from the PREVIOUS bar (i-1).
    This matches the research engine's lookahead-free design.
    """

    symbol: str
    timeframe: str
    timestamp: datetime
    bar_index: int

    open: float
    high: float
    low: float
    close: float

    # Previous bar's confirmed swing levels
    previous_swing_low: float
    previous_swing_high: float

    def to_trade_management_market(self) -> "MarketUpdate":
        """Convert to TradeLifecycleManager's MarketUpdate format."""
        from strategy.trade_management.manager import MarketUpdate
        return MarketUpdate(
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            prev_swing_low=self.previous_swing_low,
            prev_swing_high=self.previous_swing_high,
        )


@dataclass(frozen=True)
class LifecycleDecision:
    """Decision returned by lifecycle evaluation."""

    action: LifecycleAction
    trade_id: str
    new_sl: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None

    @property
    def is_exit(self) -> bool:
        return self.action == LifecycleAction.EXIT

    @property
    def is_sl_move(self) -> bool:
        return self.action == LifecycleAction.MOVE_STOP

    @property
    def is_hold(self) -> bool:
        return self.action == LifecycleAction.HOLD


@dataclass(frozen=True)
class PositionModificationRequest:
    """Request to modify an existing position's SL."""

    trade_id: str
    symbol: str
    new_sl: float
    reason: str


@dataclass(frozen=True)
class ModificationResult:
    """Result of a broker SL modification request.

    This is the confirmation contract. The runtime MUST verify
    that the broker actually applied the requested SL.
    """

    success: bool
    trade_id: str
    requested_sl: float
    broker_sl: Optional[float]  # Actual SL after modification
    timestamp: datetime
    error: Optional[str] = None

    @property
    def sl_matches(self) -> bool:
        """True if broker SL matches requested SL."""
        if not self.success or self.broker_sl is None:
            return False
        return abs(self.broker_sl - self.requested_sl) < 1e-10


@dataclass(frozen=True)
class ReconciliationResult:
    """Result of internal vs broker state comparison."""

    trade_id: str
    internal_sl: float
    broker_sl: float
    mismatch: bool
    severity: str  # "OK" or "CRITICAL"

    @property
    def is_ok(self) -> bool:
        return not self.mismatch


class OrphanPositionPolicy(str, Enum):
    """Policy for handling broker orphan positions at startup."""
    HALT = "HALT"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class StartupReconciliationResult:
    """Result of startup reconciliation between broker and registry.

    Classifies every position into:
    - MATCHED: position exists in both broker and registry with matching state
    - BROKER_ORPHAN: position at broker but not in registry (CRITICAL)
    - INTERNAL_GHOST: position in registry but not at broker
    - STATE_MISMATCH: position in both but critical state differs
    """

    success: bool
    matched_count: int
    broker_orphans: list  # list of dicts with broker position info
    internal_ghosts: list  # list of str trade_ids
    state_mismatches: list  # list of dicts with mismatch details
    actions_taken: list  # list of str describing actions
    runtime_safe: bool
    orphan_policy: str

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "matched_count": self.matched_count,
            "broker_orphan_count": len(self.broker_orphans),
            "internal_ghost_count": len(self.internal_ghosts),
            "state_mismatch_count": len(self.state_mismatches),
            "actions_taken": self.actions_taken,
            "runtime_safe": self.runtime_safe,
            "orphan_policy": self.orphan_policy,
        }
