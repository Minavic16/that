"""
NestQuant S8 — Prop Firm Risk Guard
======================================
Extends RiskGuard with prop-firm specific safety controls.

This module:
  - Provides prop-firm calibrated RiskGuardConfig
  - Tracks daily equity reset
  - Enforces max daily loss as absolute dollar amount
  - Enforces max consecutive losing days
  - Enforces max total drawdown from starting balance
  - Logs all safety state transitions

This module does NOT:
  - Import MT5 or broker SDKs
  - Make network calls
  - Perform strategy calculations
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Optional

from config.constitution import CONSTITUTION
from execution.risk_guard import RiskGuard, RiskGuardConfig
from risk.circuit_breakers import BreakerSuite


# ---------------------------------------------------------------------------
# Prop Firm Risk Guard Configuration — derives from constitution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropFirmConfig:
    """Configuration calibrated for a prop firm evaluation.

    Shared limits are derived from the constitution.
    Prop-firm-specific limits (absolute $, profit target, etc.) are
    defined here.
    """

    starting_balance: float = 200_000.0
    leverage: int = 100

    # Risk per trade — FROM CONSTITUTION (not prop firm's 1%)
    risk_pct: float = CONSTITUTION.risk_per_trade_pct

    # Daily loss limit — FROM CONSTITUTION (percentage)
    max_daily_loss_pct: float = CONSTITUTION.max_daily_loss_pct
    # Prop firm absolute dollar limit (derived from constitution pct × balance)
    max_daily_loss_absolute: float = 0.0  # computed in __post_init__

    # Total drawdown limit — FROM CONSTITUTION (percentage)
    max_total_drawdown_pct: float = CONSTITUTION.max_drawdown_pct
    # Prop firm absolute dollar limit (derived from constitution pct × balance)
    max_total_drawdown_absolute: float = 0.0  # computed in __post_init__

    # Profit target (prop-firm specific)
    profit_target_absolute: float = 20_000.0
    profit_target_pct: float = 0.10

    # Consistency rule
    max_daily_profit_pct_of_total: float = 0.50

    # Position limits — FROM CONSTITUTION
    max_concurrent_positions: int = CONSTITUTION.max_concurrent_positions
    max_position_size_per_pair: float = CONSTITUTION.max_position_size_per_pair
    max_total_exposure: float = CONSTITUTION.max_total_exposure

    # Trade frequency — FROM CONSTITUTION
    max_trades_per_day: int = CONSTITUTION.max_trades_per_day

    # Consecutive losing days (prop-firm specific)
    max_consecutive_losing_days: int = 5

    # Margin safety
    margin_safety: float = 0.5

    # Lot sizing
    lot_step: float = 0.01
    min_lot: float = 0.01


# ---------------------------------------------------------------------------
# Prop Firm Risk Guard State
# ---------------------------------------------------------------------------


@dataclass
class PropFirmState:
    """Tracks prop-firm specific risk state across sessions."""

    starting_balance: float = 200_000.0
    peak_balance: float = 200_000.0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    trade_count_today: int = 0
    daily_reset_date: Optional[date] = None
    consecutive_losing_days: int = 0
    last_day_pnl: float = 0.0
    daily_pnls: list[float] = None  # Last N days for consistency check

    def __post_init__(self) -> None:
        if self.daily_pnls is None:
            self.daily_pnls = []

    @property
    def current_equity(self) -> float:
        return self.starting_balance + self.total_pnl

    @property
    def drawdown_from_peak(self) -> float:
        return self.peak_balance - self.current_equity

    @property
    def drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return self.drawdown_from_peak / self.peak_balance

    @property
    def daily_loss_remaining(self) -> float:
        """How much more can be lost today before hitting limit."""
        if self.daily_pnl >= 0:
            return 0.0
        return max(0.0, abs(self.daily_pnl))

    @property
    def total_loss_remaining(self) -> float:
        """How much more can be lost total before hitting limit."""
        return max(0.0, self.drawdown_from_peak)

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade."""
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.peak_balance = max(self.peak_balance, self.current_equity)
        self.trade_count_today += 1

    def new_day(self) -> None:
        """Reset for a new trading day."""
        today = date.today()

        if self.daily_reset_date == today:
            return  # Already reset today

        # Record yesterday's PnL
        if self.daily_pnl != 0.0:
            self.daily_pnls.append(self.daily_pnl)
            if self.daily_pnl < 0:
                self.consecutive_losing_days += 1
            else:
                self.consecutive_losing_days = 0

        # Reset daily counters
        self.daily_pnl = 0.0
        self.trade_count_today = 0
        self.daily_reset_date = today

        # Keep only last 30 days for consistency check
        if len(self.daily_pnls) > 30:
            self.daily_pnls = self.daily_pnls[-30:]


# ---------------------------------------------------------------------------
# Prop Firm Risk Guard
# ---------------------------------------------------------------------------


class PropFirmGuard(RiskGuard):
    """Risk guard with prop-firm safety controls.

    Extends the base RiskGuard with:
      - Absolute dollar limits (not just percentages)
      - Consecutive losing day tracking
      - Consistency rule enforcement
      - Profit target awareness
      - Session-aware daily reset
    """

    def __init__(
        self,
        prop_config: Optional[PropFirmConfig] = None,
        breaker_suite: Optional[BreakerSuite] = None,
        policy_version: str = "s8-prop-1.0.0",
    ) -> None:
        """Initialize prop firm risk guard.

        Args:
            prop_config: Prop firm configuration. Uses defaults if None.
            breaker_suite: Circuit breaker suite. Creates new if None.
            policy_version: Policy version for version integrity.
        """
        self._prop_config = prop_config or PropFirmConfig()

        # Compute absolute dollar limits from constitution percentages
        balance = self._prop_config.starting_balance
        if self._prop_config.max_daily_loss_absolute == 0.0:
            object.__setattr__(
                self._prop_config, '_max_daily_loss_absolute_computed',
                balance * CONSTITUTION.max_daily_loss_pct,
            )
        if self._prop_config.max_total_drawdown_absolute == 0.0:
            object.__setattr__(
                self._prop_config, '_max_total_drawdown_absolute_computed',
                balance * CONSTITUTION.max_drawdown_pct,
            )

        # Map constitution-derived config to base RiskGuardConfig
        base_config = RiskGuardConfig(
            account_balance=balance,
            leverage=self._prop_config.leverage,
            risk_pct=self._prop_config.risk_pct,
            max_concurrent_positions=self._prop_config.max_concurrent_positions,
            max_position_size_per_pair=self._prop_config.max_position_size_per_pair,
            max_total_exposure=self._prop_config.max_total_exposure,
            max_daily_loss_pct=self._prop_config.max_daily_loss_pct,
            max_drawdown_pct=self._prop_config.max_total_drawdown_pct,
            max_trades_per_day=self._prop_config.max_trades_per_day,
            margin_safety=self._prop_config.margin_safety,
            lot_step=self._prop_config.lot_step,
            min_lot=self._prop_config.min_lot,
        )

        super().__init__(
            config=base_config,
            breaker_suite=breaker_suite,
            policy_version=policy_version,
        )

        # Prop-firm specific state
        self._prop_state = PropFirmState(
            starting_balance=balance,
            peak_balance=balance,
        )

    @property
    def prop_config(self) -> PropFirmConfig:
        return self._prop_config

    @property
    def prop_state(self) -> PropFirmState:
        return self._prop_state

    def check_daily_reset(self) -> None:
        """Check if we need to reset for a new trading day."""
        self._prop_state.new_day()

    def record_trade_result(
        self,
        pnl: float,
        equity: float,
        slippage_pips: float = 0.0,
    ) -> None:
        """Record a completed trade with prop-firm tracking."""
        # Check daily reset first
        self.check_daily_reset()

        # Record in base class
        super().record_trade_result(pnl, equity, slippage_pips)

        # Record in prop-firm state
        self._prop_state.record_trade(pnl)

    def evaluate(self, intent) -> "RiskDecision":
        """Evaluate with prop-firm safety checks added.

        Runs base RiskGuard checks first, then adds prop-firm specific checks.
        """
        # Check daily reset
        self.check_daily_reset()

        # Run base checks
        base_decision = super().evaluate(intent)
        if not base_decision.approved:
            return base_decision

        # --- Prop-firm specific checks ---

        # Check 8: Absolute daily loss limit (constitution-derived)
        daily_loss_abs_limit = self._prop_config.starting_balance * CONSTITUTION.max_daily_loss_pct
        if self._prop_state.daily_pnl < 0:
            daily_loss_abs = abs(self._prop_state.daily_pnl)
            if daily_loss_abs > daily_loss_abs_limit:
                return self._reject(
                    f"Daily loss limit: "
                    f"${daily_loss_abs:,.0f} > ${daily_loss_abs_limit:,.0f} "
                    f"({CONSTITUTION.max_daily_loss_pct:.0%} of ${self._prop_config.starting_balance:,.0f})"
                )

        # Check 9: Total drawdown from starting balance (constitution-derived)
        total_dd_abs_limit = self._prop_config.starting_balance * CONSTITUTION.max_drawdown_pct
        total_dd_abs = self._prop_state.drawdown_from_peak
        if total_dd_abs > total_dd_abs_limit:
            return self._reject(
                f"Total drawdown limit: "
                f"${total_dd_abs:,.0f} > ${total_dd_abs_limit:,.0f} "
                f"({CONSTITUTION.max_drawdown_pct:.0%} of ${self._prop_config.starting_balance:,.0f})"
            )

        # Check 10: Consecutive losing days
        if self._prop_state.consecutive_losing_days >= self._prop_config.max_consecutive_losing_days:
            return self._reject(
                f"Prop firm consecutive losing days: "
                f"{self._prop_state.consecutive_losing_days} >= {self._prop_config.max_consecutive_losing_days}"
            )

        # Check 11: Profit target reached (no more trading needed)
        if self._prop_state.total_pnl >= self._prop_config.profit_target_absolute:
            return self._reject(
                f"Prop firm profit target reached: "
                f"${self._prop_state.total_pnl:,.0f} >= ${self._prop_config.profit_target_absolute:,.0f}"
            )

        # Approved
        return base_decision

    def status(self) -> dict:
        """Get comprehensive prop-firm risk status."""
        base_status = super().status()
        daily_loss_limit = self._prop_config.starting_balance * CONSTITUTION.max_daily_loss_pct
        total_dd_limit = self._prop_config.starting_balance * CONSTITUTION.max_drawdown_pct
        base_status.update({
            "prop_firm": {
                "starting_balance": self._prop_config.starting_balance,
                "current_equity": self._prop_state.current_equity,
                "peak_balance": self._prop_state.peak_balance,
                "total_pnl": self._prop_state.total_pnl,
                "daily_pnl": self._prop_state.daily_pnl,
                "daily_loss_limit": daily_loss_limit,
                "daily_loss_remaining": max(0, daily_loss_limit - abs(self._prop_state.daily_pnl)) if self._prop_state.daily_pnl < 0 else daily_loss_limit,
                "total_drawdown": self._prop_state.drawdown_from_peak,
                "total_drawdown_limit": total_dd_limit,
                "total_drawdown_remaining": max(0, total_dd_limit - self._prop_state.drawdown_from_peak),
                "profit_target": self._prop_config.profit_target_absolute,
                "profit_progress": self._prop_state.total_pnl / self._prop_config.profit_target_absolute if self._prop_config.profit_target_absolute > 0 else 0.0,
                "consecutive_losing_days": self._prop_state.consecutive_losing_days,
                "max_consecutive_losing_days": self._prop_config.max_consecutive_losing_days,
                "trade_count_today": self._prop_state.trade_count_today,
                "max_trades_per_day": self._prop_config.max_trades_per_day,
                "daily_reset_date": str(self._prop_state.daily_reset_date) if self._prop_state.daily_reset_date else None,
                "constitution_source": "config.constitution.CONSTITUTION",
            },
        })
        return base_status

    def __repr__(self) -> str:
        return (
            f"<PropFirmGuard(equity=${self._prop_state.current_equity:,.0f}, "
            f"daily_pnl=${self._prop_state.daily_pnl:,.0f}, "
            f"total_pnl=${self._prop_state.total_pnl:,.0f})>"
        )
