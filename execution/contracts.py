"""
NestQuant Execution Contracts — Immutable Data Flow Objects
===========================================================
Defines the data contracts between strategy, risk, and execution layers.

These are pure data containers with validation. They contain:
  - No strategy logic
  - No risk calculations
  - No broker-specific API coupling
  - No network calls
  - No logging
  - No monitoring

Each contract represents a single handoff in the execution pipeline:
  Strategy → TradeIntent → Risk → RiskDecision → OrderRequest → ExecutionResult
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"


class ExecutionStatus(str, Enum):
    """Outcome classification for an execution result."""

    FILLED = "FILLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class ContractValidationError(ValueError):
    """Raised when a contract fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Contract validation failed: {'; '.join(errors)}")


# ---------------------------------------------------------------------------
# TradeIntent — Strategy → Risk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeIntent:
    """Immutable signal from the strategy layer to the risk layer.

    Represents the strategy's desire to enter a trade. Contains all
    information the strategy had at decision time. No future data.
    """

    pair: str
    direction: Direction
    signal_strength: float
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy: str
    policy_version: str
    timestamp: datetime

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty if valid."""
        errors: list[str] = []

        if not self.pair or not self.pair.strip():
            errors.append("pair must be non-empty")

        if not isinstance(self.direction, Direction):
            errors.append(f"direction must be BUY or SELL, got {self.direction}")

        if self.entry_price <= 0:
            errors.append(f"entry_price must be positive, got {self.entry_price}")

        if self.stop_loss <= 0:
            errors.append(f"stop_loss must be positive, got {self.stop_loss}")

        if self.take_profit <= 0:
            errors.append(f"take_profit must be positive, got {self.take_profit}")

        if self.signal_strength < 0 or self.signal_strength > 1:
            errors.append(
                f"signal_strength must be in [0, 1], got {self.signal_strength}"
            )

        if not self.policy_version or not self.policy_version.strip():
            errors.append("policy_version must be non-empty")

        if self.timestamp.tzinfo is None:
            errors.append("timestamp must be timezone-aware")
        elif self.timestamp.tzinfo != timezone.utc:
            errors.append("timestamp must be UTC")

        # Directional validity: SL and TP must make sense for the direction
        if self.direction == Direction.BUY:
            if self.stop_loss >= self.entry_price:
                errors.append(
                    f"BUY stop_loss ({self.stop_loss}) must be < entry_price ({self.entry_price})"
                )
            if self.take_profit <= self.entry_price:
                errors.append(
                    f"BUY take_profit ({self.take_profit}) must be > entry_price ({self.entry_price})"
                )
        elif self.direction == Direction.SELL:
            if self.stop_loss <= self.entry_price:
                errors.append(
                    f"SELL stop_loss ({self.stop_loss}) must be > entry_price ({self.entry_price})"
                )
            if self.take_profit >= self.entry_price:
                errors.append(
                    f"SELL take_profit ({self.take_profit}) must be < entry_price ({self.entry_price})"
                )

        return errors

    def assert_valid(self) -> None:
        """Raise ContractValidationError if invalid."""
        errors = self.validate()
        if errors:
            raise ContractValidationError(errors)


# ---------------------------------------------------------------------------
# RiskDecision — Risk → Execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskDecision:
    """Immutable decision from the risk layer to the execution layer.

    Approved decisions include the computed lot_size and risk_amount.
    Rejected decisions include a human-readable reason.
    """

    approved: bool
    reason: str
    risk_amount: float
    lot_size: float
    policy_version: str

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty if valid."""
        errors: list[str] = []

        if not self.policy_version or not self.policy_version.strip():
            errors.append("policy_version must be non-empty")

        if self.risk_amount < 0:
            errors.append(f"risk_amount cannot be negative, got {self.risk_amount}")

        if self.lot_size < 0:
            errors.append(f"lot_size cannot be negative, got {self.lot_size}")

        if self.approved:
            if self.lot_size <= 0:
                errors.append(
                    f"approved decision must have lot_size > 0, got {self.lot_size}"
                )
            # Approved decisions must not contain contradictory rejection state
            if self.reason and self.reason.strip():
                lower = self.reason.strip().lower()
                rejection_keywords = (
                    "reject", "deny", "denied", "exceed", "exceeded",
                    "breach", "violation", "fail", "failed",
                    "insufficient", "invalid", "block", "blocked",
                )
                if any(kw in lower for kw in rejection_keywords):
                    errors.append(
                        f"approved decision must not contain rejection language in reason: '{self.reason}'"
                    )
        else:
            # Rejected decisions must have a meaningful reason
            if not self.reason or not self.reason.strip():
                errors.append("rejected decision must have a non-empty reason")

        return errors

    def assert_valid(self) -> None:
        """Raise ContractValidationError if invalid."""
        errors = self.validate()
        if errors:
            raise ContractValidationError(errors)


# ---------------------------------------------------------------------------
# OrderRequest — Execution → Broker Adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderRequest:
    """Immutable execution request sent to a broker adapter.

    This is broker-agnostic. It represents what to execute, not how.
    The broker adapter (e.g., MT5, cTrader) translates this into
    a broker-specific API call.
    """

    pair: str
    direction: Direction
    lot_size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    policy_version: str

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty if valid."""
        errors: list[str] = []

        if not self.pair or not self.pair.strip():
            errors.append("pair must be non-empty")

        if not isinstance(self.direction, Direction):
            errors.append(f"direction must be BUY or SELL, got {self.direction}")

        if self.lot_size <= 0:
            errors.append(f"lot_size must be positive, got {self.lot_size}")

        if self.entry_price <= 0:
            errors.append(f"entry_price must be positive, got {self.entry_price}")

        if self.stop_loss <= 0:
            errors.append(f"stop_loss must be positive, got {self.stop_loss}")

        if self.take_profit <= 0:
            errors.append(f"take_profit must be positive, got {self.take_profit}")

        if not self.policy_version or not self.policy_version.strip():
            errors.append("policy_version must be non-empty")

        return errors

    def assert_valid(self) -> None:
        """Raise ContractValidationError if invalid."""
        errors = self.validate()
        if errors:
            raise ContractValidationError(errors)


# ---------------------------------------------------------------------------
# ExecutionResult — Broker Adapter → System
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result returned by a broker adapter after execution.

    Distinguishes between:
      - FILLED: order was successfully filled
      - REJECTED: broker rejected the order (e.g., margin, instrument)
      - ERROR: execution failed (e.g., network, timeout)
    """

    status: ExecutionStatus
    order_id: Optional[str]
    requested_price: float
    fill_price: Optional[float]
    slippage_pips: float
    rejection_reason: Optional[str]

    @property
    def is_filled(self) -> bool:
        """True if the order was successfully filled."""
        return self.status == ExecutionStatus.FILLED and self.fill_price is not None

    @property
    def is_rejected(self) -> bool:
        """True if the broker rejected the order."""
        return self.status == ExecutionStatus.REJECTED

    @property
    def is_error(self) -> bool:
        """True if execution failed with an error."""
        return self.status == ExecutionStatus.ERROR

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty if valid."""
        errors: list[str] = []

        if not isinstance(self.status, ExecutionStatus):
            errors.append(f"status must be FILLED, REJECTED, or ERROR, got {self.status}")

        if self.requested_price <= 0:
            errors.append(f"requested_price must be positive, got {self.requested_price}")

        if self.slippage_pips < 0:
            errors.append(f"slippage_pips cannot be negative, got {self.slippage_pips}")

        if self.status == ExecutionStatus.FILLED:
            if self.fill_price is None:
                errors.append("FILLED result must have a fill_price")
            elif self.fill_price <= 0:
                errors.append(f"fill_price must be positive, got {self.fill_price}")
            if self.rejection_reason is not None:
                errors.append("FILLED result should not have a rejection_reason")

        if self.status == ExecutionStatus.REJECTED:
            if not self.rejection_reason or not self.rejection_reason.strip():
                errors.append("REJECTED result must have a non-empty rejection_reason")
            if self.fill_price is not None:
                errors.append("REJECTED result should not have a fill_price")

        if self.status == ExecutionStatus.ERROR:
            if not self.rejection_reason or not self.rejection_reason.strip():
                errors.append("ERROR result must have a non-empty rejection_reason (error message)")

        return errors

    def assert_valid(self) -> None:
        """Raise ContractValidationError if invalid."""
        errors = self.validate()
        if errors:
            raise ContractValidationError(errors)
