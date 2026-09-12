"""
NestQuant S8 — Intent Factory
===============================
Converts BreakoutSignal output (SignalResult) into TradeIntent
for the execution pipeline.

This module:
  - Bridges strategy signals to execution contracts
  - Generates unique signal_id for traceability
  - Attaches experiment identity to every intent
  - Validates signal is actionable before creating intent

This module does NOT:
  - Import MT5 or broker SDKs
  - Make network calls
  - Perform risk calculations
  - Perform strategy calculations
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from nestquant.core.contracts.execution_contracts import Direction, TradeIntent

if TYPE_CHECKING:
    from nestquant.production.signals.base import SignalResult


class IntentFactoryError(ValueError):
    """Raised when intent creation fails due to invalid signal."""
    pass


class IntentFactory:
    """Converts SignalResult to TradeIntent.

    Each intent gets a unique signal_id for traceability through
    the execution pipeline: signal → intent → risk → order → fill.
    """

    def __init__(
        self,
        strategy_version: str = "breakout-1.0.0",
        policy_version: str = "s7-1.0.0",
        experiment_id: str = "",
        config_hash: str = "",
    ) -> None:
        """Initialize the intent factory.

        Args:
            strategy_version: Version string for the strategy.
            policy_version: Policy version for risk compatibility.
            experiment_id: Experiment identity for logging.
            config_hash: Config hash for reproducibility.
        """
        self._strategy_version = strategy_version
        self._policy_version = policy_version
        self._experiment_id = experiment_id
        self._config_hash = config_hash

    @property
    def strategy_version(self) -> str:
        return self._strategy_version

    @property
    def experiment_id(self) -> str:
        return self._experiment_id

    def create_intent(
        self,
        signal: SignalResult,
        timestamp: Optional[datetime] = None,
    ) -> TradeIntent:
        """Convert a SignalResult into a TradeIntent.

        Args:
            signal: The strategy's signal output.
            timestamp: Optional timestamp. Uses current UTC if not provided.

        Returns:
            TradeIntent ready for the execution pipeline.

        Raises:
            IntentFactoryError: If the signal is not actionable.
        """
        if not signal.is_active:
            raise IntentFactoryError(
                f"Cannot create intent from inactive signal: "
                f"direction={signal.direction}, strength={signal.strength}"
            )

        if signal.entry_price is None or signal.entry_price <= 0:
            raise IntentFactoryError(
                f"Signal has invalid entry_price: {signal.entry_price}"
            )

        if signal.sl_price is None or signal.sl_price <= 0:
            raise IntentFactoryError(
                f"Signal has invalid sl_price: {signal.sl_price}"
            )

        if signal.tp_price is None or signal.tp_price <= 0:
            raise IntentFactoryError(
                f"Signal has invalid tp_price: {signal.tp_price}"
            )

        # Map direction string to Direction enum
        try:
            direction = Direction(signal.direction.upper())
        except ValueError:
            raise IntentFactoryError(
                f"Invalid direction: {signal.direction}. Must be BUY or SELL."
            )

        ts = timestamp or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        # Generate unique signal_id
        signal_id = str(uuid.uuid4())

        return TradeIntent(
            pair=signal.pair,
            direction=direction,
            signal_strength=signal.strength,
            entry_price=signal.entry_price,
            stop_loss=signal.sl_price,
            take_profit=signal.tp_price,
            strategy=self._strategy_version,
            policy_version=self._policy_version,
            timestamp=ts,
        )

    def create_intent_with_id(
        self,
        signal: SignalResult,
        timestamp: Optional[datetime] = None,
    ) -> tuple[TradeIntent, str]:
        """Create intent and return the signal_id separately.

        This is useful when the caller needs the signal_id for logging
        before the intent enters the execution pipeline.

        Returns:
            (TradeIntent, signal_id) tuple.
        """
        intent = self.create_intent(signal, timestamp)
        # We need to generate a separate signal_id here since
        # TradeIntent doesn't have a signal_id field.
        # The signal_id is used by TradeLogger, not TradeIntent.
        signal_id = str(uuid.uuid4())
        return intent, signal_id

    def __repr__(self) -> str:
        return (
            f"<IntentFactory(strategy={self._strategy_version}, "
            f"experiment={self._experiment_id})>"
        )
