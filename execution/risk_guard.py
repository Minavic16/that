"""
NestQuant Risk Guard — Per-Trade Risk Evaluation
=================================================
Implements the RiskEvaluator protocol for live execution.

This module:
  - Checks circuit breakers before approving trades
  - Computes risk-based lot size via position_sizer
  - Enforces S7 exposure limits (max positions, max daily loss, etc.)
  - Returns RiskDecision for the orchestration layer

This module does NOT:
  - Import MT5 or broker SDKs
  - Make network calls
  - Perform strategy calculations
  - Contain logging or monitoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from nestquant.config.constitution import CONSTITUTION, ConstitutionRiskConfig
from nestquant.execution.contracts import (
    RiskDecision,
    TradeIntent,
)
from nestquant.portfolio.position_sizer import (
    SizingResult,
    compute_position_size,
    pip_size_for_pair,
    pip_value_per_lot,
)
from nestquant.risk.circuit_breakers import BreakerSuite

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk Guard Configuration — derives from constitution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskGuardConfig:
    """Configuration for the risk guard.

    Defaults are derived from the constitution. Override only for
    account-specific values (balance, leverage) that are NOT part
    of the constitution.
    """

    # Account (not part of constitution — account-specific)
    account_balance: float = 5_000_000.0
    leverage: int = 100

    # Risk per trade — FROM CONSTITUTION
    risk_pct: float = CONSTITUTION.risk_per_trade_pct

    # Position limits — FROM CONSTITUTION
    max_concurrent_positions: int = CONSTITUTION.max_concurrent_positions
    max_position_size_per_pair: float = CONSTITUTION.max_position_size_per_pair
    max_total_exposure: float = CONSTITUTION.max_total_exposure

    # Loss limits — FROM CONSTITUTION
    max_daily_loss_pct: float = CONSTITUTION.max_daily_loss_pct
    max_drawdown_pct: float = CONSTITUTION.max_drawdown_pct

    # Trade frequency — FROM CONSTITUTION
    max_trades_per_day: int = CONSTITUTION.max_trades_per_day

    # Margin safety
    margin_safety: float = 0.5  # Reject if margin > 50% of available

    # Lot sizing
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: Optional[float] = None  # None = no max (per-pair max enforced separately)


# ---------------------------------------------------------------------------
# Risk Guard
# ---------------------------------------------------------------------------


class RiskGuard:
    """Per-trade risk evaluator for live execution.

    Implements the RiskEvaluator protocol. Checks:
    1. Circuit breakers (win rate, slippage, drawdown, etc.)
    2. Position count limits
    3. Per-pair lot size limits
    4. Total exposure limits
    5. Daily loss limits
    6. Drawdown limits
    7. Margin availability
    """

    def __init__(
        self,
        config: Optional[RiskGuardConfig] = None,
        breaker_suite: Optional[BreakerSuite] = None,
        policy_version: str = "s7-1.0.0",
    ) -> None:
        """Initialize the risk guard.

        Args:
            config: Risk guard configuration. Uses defaults if None.
            breaker_suite: Circuit breaker suite. Creates new if None.
            policy_version: Policy version for version integrity checks.
        """
        self._config = config or RiskGuardConfig()
        self._breakers = breaker_suite or BreakerSuite()
        self._policy_version = policy_version
        self._open_positions: list[dict] = []
        self._daily_pnl: float = 0.0
        self._peak_equity: float = self._config.account_balance
        self._trade_count_today: int = 0

    @property
    def config(self) -> RiskGuardConfig:
        return self._config

    @property
    def breakers(self) -> BreakerSuite:
        return self._breakers

    @property
    def policy_version(self) -> str:
        return self._policy_version

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def update_positions(self, positions: list[dict]) -> None:
        """Update the current open positions state.

        Args:
            positions: List of position dicts from MT5.
        """
        self._open_positions = list(positions)

    def record_trade_result(
        self,
        pnl: float,
        equity: float,
        slippage_pips: float = 0.0,
    ) -> None:
        """Record a completed trade result for circuit breaker tracking.

        Args:
            pnl: Realized PnL in account currency.
            equity: Current account equity.
            slippage_pips: Slippage in pips for this trade.
        """
        self._daily_pnl += pnl
        self._peak_equity = max(self._peak_equity, equity)
        self._trade_count_today += 1
        self._breakers.record_trade(
            pnl=pnl,
            equity=equity,
            peak=self._peak_equity,
            slippage_pips=slippage_pips,
        )

    def reset_daily(self) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self._daily_pnl = 0.0
        self._trade_count_today = 0

    # ------------------------------------------------------------------
    # RiskEvaluator protocol
    # ------------------------------------------------------------------

    def evaluate(self, intent: TradeIntent) -> RiskDecision:
        """Evaluate a trade intent and return a risk decision.

        This is the core RiskEvaluator protocol implementation.
        Checks all risk gates before approving a trade.

        Args:
            intent: The strategy's trade signal.

        Returns:
            RiskDecision with approval status, lot_size, and reason.
        """
        # Gate 0: Max trades per day
        if self._trade_count_today >= self._config.max_trades_per_day:
            return self._reject(
                f"Max trades per day reached: "
                f"{self._trade_count_today}/{self._config.max_trades_per_day}"
            )

        # Gate 1: Circuit breakers
        can_trade, breaker_reason = self._breakers.can_trade
        if not can_trade:
            return self._reject(f"Circuit breaker: {breaker_reason}")

        # Gate 2: Max concurrent positions
        if len(self._open_positions) >= self._config.max_concurrent_positions:
            return self._reject(
                f"Max concurrent positions reached: "
                f"{len(self._open_positions)}/{self._config.max_concurrent_positions}"
            )

        # Gate 3: Daily loss limit
        daily_loss_pct = abs(self._daily_pnl) / self._config.account_balance
        if self._daily_pnl < 0 and daily_loss_pct >= self._config.max_daily_loss_pct:
            return self._reject(
                f"Daily loss limit breached: "
                f"{daily_loss_pct:.2%} >= {self._config.max_daily_loss_pct:.2%}"
            )

        # Gate 4: Max drawdown
        current_equity = self._config.account_balance + self._daily_pnl
        current_dd = (
            (self._peak_equity - current_equity) / self._peak_equity
            if self._peak_equity > 0
            else 0.0
        )
        if current_dd >= self._config.max_drawdown_pct - 1e-9:
            return self._reject(
                f"Max drawdown breached: "
                f"{current_dd:.2%} >= {self._config.max_drawdown_pct:.2%}"
            )

        # Gate 5: Compute position size
        sizing = compute_position_size(
            pair=intent.pair,
            side=intent.direction.value,
            entry_price=intent.entry_price,
            sl_price=intent.stop_loss,
            account_balance_usd=self._config.account_balance,
            risk_pct=self._config.risk_pct,
            leverage=self._config.leverage,
            margin_safety=self._config.margin_safety,
            lot_step=self._config.lot_step,
            min_lot=self._config.min_lot,
            max_lot=self._config.max_position_size_per_pair,
        )

        if not sizing.ok:
            return self._reject(f"Position sizing failed: {sizing.reject_reason}")

        lot_size = sizing.lot_size

        # Gate 6: Per-pair exposure check
        pair_exposure = sum(
            p.get("volume", 0)
            for p in self._open_positions
            if p.get("symbol", "").replace("/", "") == intent.pair.replace("/", "")
        )
        if pair_exposure + lot_size > self._config.max_position_size_per_pair:
            return self._reject(
                f"Per-pair exposure limit: "
                f"{pair_exposure + lot_size:.2f} > {self._config.max_position_size_per_pair:.2f}"
            )

        # Gate 7: Total exposure check
        total_exposure = sum(p.get("volume", 0) for p in self._open_positions)
        if total_exposure + lot_size > self._config.max_total_exposure:
            return self._reject(
                f"Total exposure limit: "
                f"{total_exposure + lot_size:.2f} > {self._config.max_total_exposure:.2f}"
            )

        # Approved
        return RiskDecision(
            approved=True,
            reason="Within risk limits",
            risk_amount=sizing.risk_dollars,
            lot_size=lot_size,
            policy_version=self._policy_version,
        )

    def _reject(self, reason: str) -> RiskDecision:
        """Create a rejection decision with logging and notification."""
        logger.warning("RISK_REJECTED: %s", reason)
        try:
            from notifications.signal_notifier import send_risk_block_alert
            send_risk_block_alert(reason=reason)
        except Exception:
            pass
        return RiskDecision(
            approved=False,
            reason=reason,
            risk_amount=0.0,
            lot_size=0.0,
            policy_version=self._policy_version,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Get the current risk guard status."""
        can_trade, blocked_by = self._breakers.can_trade
        return {
            "can_trade": can_trade,
            "blocked_by": blocked_by,
            "open_positions": len(self._open_positions),
            "max_positions": self._config.max_concurrent_positions,
            "daily_pnl": self._daily_pnl,
            "daily_loss_limit": self._config.max_daily_loss_pct,
            "peak_equity": self._peak_equity,
            "trade_count_today": self._trade_count_today,
            "max_trades_per_day": self._config.max_trades_per_day,
            "trades_remaining_today": max(0, self._config.max_trades_per_day - self._trade_count_today),
            "risk_per_trade_pct": self._config.risk_pct,
            "max_drawdown_pct": self._config.max_drawdown_pct,
            "max_total_exposure": self._config.max_total_exposure,
            "max_position_size_per_pair": self._config.max_position_size_per_pair,
            "policy_version": self._policy_version,
            "constitution_source": "config.constitution.CONSTITUTION",
            "breakers": self._breakers.status(),
        }

    def __repr__(self) -> str:
        return (
            f"<RiskGuard(policy={self._policy_version}, "
            f"positions={len(self._open_positions)}/{self._config.max_concurrent_positions})>"
        )
