"""
NestQuant Strategy — Lifecycle Registry
========================================

Manages the set of active positions and coordinates lifecycle evaluation
on each bar close.

This is the integration layer between:
- Market data (MarketContext)
- Trade lifecycle rules (TradeLifecycleManager)
- Execution (broker adapter)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from strategy.lifecycle.contracts import (
    Direction,
    ExitReason,
    LifecycleAction,
    LifecycleDecision,
    MarketContext,
    ModificationResult,
    PositionLifecycleState,
    ReconciliationResult,
)
from strategy.lifecycle.contracts import PositionModificationRequest
from strategy.trade_management.manager import TradeAction, TradeLifecycleManager, TradeState
from strategy.trade_management.breakeven import BreakevenConfig
from strategy.trade_management.max_hold import MaxHoldConfig
from strategy.trade_management.trailing_stop import TrailingStopConfig

logger = logging.getLogger(__name__)


@dataclass
class LifecycleEvent:
    """Record of a lifecycle evaluation event."""
    trade_id: str
    timestamp: datetime
    bar_index: int
    decision: LifecycleDecision
    modification_result: Optional[ModificationResult] = None
    reconciliation: Optional[ReconciliationResult] = None


class LifecycleRegistry:
    """Manages active positions and coordinates lifecycle evaluation.

    Usage:
        registry = LifecycleRegistry(strategy_identity="abc123")

        # On new trade entry
        registry.register_entry(...)

        # On each bar close
        decisions = registry.evaluate_bar(market_context)

        # For reconciliation
        results = registry.reconcile(broker_positions)
    """

    def __init__(
        self,
        strategy_identity: str,
        breakeven_config: BreakevenConfig | None = None,
        max_hold_config: MaxHoldConfig | None = None,
        trailing_config: TrailingStopConfig | None = None,
    ):
        self.strategy_identity = strategy_identity
        self._lifecycle_manager = TradeLifecycleManager(
            breakeven_config=breakeven_config,
            max_hold_config=max_hold_config,
            trailing_config=trailing_config,
        )
        self._active: dict[str, PositionLifecycleState] = {}
        self._events: list[LifecycleEvent] = []
        self._pending_sl: dict[str, float] = {}  # trade_id → proposed SL (not yet confirmed)
        self._confirmed_sl: dict[str, float] = {}  # trade_id → last broker-confirmed SL

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def events(self) -> list[LifecycleEvent]:
        return list(self._events)

    def get_position(self, trade_id: str) -> Optional[PositionLifecycleState]:
        return self._active.get(trade_id)

    def get_all_active(self) -> list[PositionLifecycleState]:
        return list(self._active.values())

    def register_entry(
        self,
        trade_id: str,
        symbol: str,
        direction: Direction,
        entry_price: float,
        initial_sl: float,
        take_profit: float,
        pip_size: float,
        entry_time: datetime,
        entry_bar_index: int,
    ) -> PositionLifecycleState:
        """Register a new trade entry."""
        risk_pips = abs(entry_price - initial_sl) / pip_size

        position = PositionLifecycleState(
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            strategy_identity=self.strategy_identity,
            entry_price=entry_price,
            initial_sl=initial_sl,
            take_profit=take_profit,
            risk_pips=risk_pips,
            pip_size=pip_size,
            entry_time=entry_time,
            entry_bar_index=entry_bar_index,
            current_sl=initial_sl,
            bars_held=0,
            breakeven_triggered=False,
        )

        self._active[trade_id] = position
        self._confirmed_sl[trade_id] = initial_sl
        logger.info(
            "Registered entry: %s %s %s @ %.5f SL=%.5f TP=%.5f risk=%.1f pips",
            trade_id, symbol, direction.name, entry_price,
            initial_sl, take_profit, risk_pips,
        )
        return position

    def evaluate_bar(self, market: MarketContext) -> list[LifecycleDecision]:
        """Evaluate all active positions for the given market context.

        Only evaluates positions matching the market symbol.
        Called once per bar close.

        Returns list of decisions (one per active position).
        """
        decisions = []

        for trade_id in list(self._active.keys()):
            position = self._active.get(trade_id)
            if position is None:
                continue
            if position.symbol != market.symbol:
                continue

            # Increment bars held
            new_bars = position.bars_held + 1
            object.__setattr__(position, 'bars_held', new_bars)

            # Convert to TradeState for lifecycle manager
            trade_state = TradeState(
                direction=position.direction.value,
                entry_price=position.entry_price,
                current_sl=position.current_sl,
                take_profit=position.take_profit,
                risk_pips=position.risk_pips,
                pip_size=position.pip_size,
                bars_held=position.bars_held,
                entry_idx=position.entry_bar_index,
            )

            market_update = market.to_trade_management_market()

            # Evaluate
            result = self._lifecycle_manager.evaluate(trade_state, market_update)

            # Convert to LifecycleDecision
            decision = self._convert_decision(trade_id, result, market)

            # Apply state changes
            if decision.is_sl_move and decision.new_sl is not None:
                # State integrity: stage pending SL, do NOT commit yet
                # SL is only committed after broker confirmation via commit_sl()
                self._pending_sl[trade_id] = decision.new_sl

            if decision.is_exit:
                self._active.pop(trade_id, None)
                self._pending_sl.pop(trade_id, None)
                self._confirmed_sl.pop(trade_id, None)

            # Record event
            event = LifecycleEvent(
                trade_id=trade_id,
                timestamp=market.timestamp,
                bar_index=market.bar_index,
                decision=decision,
            )
            self._events.append(event)

            decisions.append(decision)

        return decisions

    def _convert_decision(
        self,
        trade_id: str,
        result,
        market: MarketContext,
    ) -> LifecycleDecision:
        """Convert TradeManager result to LifecycleDecision."""
        if result.action == TradeAction.EXIT:
            reason_map = {
                "SL": ExitReason.STOP_LOSS,
                "TP": ExitReason.TAKE_PROFIT,
                "MH": ExitReason.MAX_HOLD,
            }
            return LifecycleDecision(
                action=LifecycleAction.EXIT,
                trade_id=trade_id,
                exit_price=result.exit_price,
                exit_reason=reason_map.get(result.exit_reason, ExitReason.MANUAL),
            )
        elif result.action == TradeAction.MOVE_STOP:
            return LifecycleDecision(
                action=LifecycleAction.MOVE_STOP,
                trade_id=trade_id,
                new_sl=result.new_sl,
            )
        else:
            return LifecycleDecision(
                action=LifecycleAction.HOLD,
                trade_id=trade_id,
            )

    def reconcile(
        self,
        broker_positions: dict[str, float],
    ) -> list[ReconciliationResult]:
        """Compare internal SL state with broker-reported SL.

        Args:
            broker_positions: {trade_id: broker_reported_sl}

        Returns:
            List of ReconciliationResult, one per active position.
        """
        results = []
        for trade_id, position in self._active.items():
            broker_sl = broker_positions.get(trade_id)
            if broker_sl is None:
                results.append(ReconciliationResult(
                    trade_id=trade_id,
                    internal_sl=position.current_sl,
                    broker_sl=0.0,
                    mismatch=True,
                    severity="CRITICAL",
                ))
                continue

            mismatch = abs(position.current_sl - broker_sl) > 1e-10
            results.append(ReconciliationResult(
                trade_id=trade_id,
                internal_sl=position.current_sl,
                broker_sl=broker_sl,
                mismatch=mismatch,
                severity="CRITICAL" if mismatch else "OK",
            ))

        return results

    def record_modification(
        self,
        trade_id: str,
        result: ModificationResult,
    ) -> None:
        """Record broker modification result against the latest event."""
        for event in reversed(self._events):
            if event.trade_id == trade_id and event.modification_result is None:
                event.modification_result = result
                break

    # ------------------------------------------------------------------
    # State Integrity — Pending SL Management
    # ------------------------------------------------------------------

    def get_pending_sl(self, trade_id: str) -> Optional[float]:
        """Get the pending (unconfirmed) SL for a position.

        Returns None if no pending SL change.
        """
        return self._pending_sl.get(trade_id)

    def has_pending_sl(self, trade_id: str) -> bool:
        """Check if a position has an unconfirmed SL change."""
        return trade_id in self._pending_sl

    def commit_sl(self, trade_id: str) -> bool:
        """Commit pending SL to confirmed state after broker confirmation.

        This is the ONLY way to advance current_sl. Lifecycle proposals
        stage a pending SL; broker confirmation triggers this commit.

        Returns:
            True if SL was committed, False if no pending SL.
        """
        if trade_id not in self._pending_sl:
            return False

        pending = self._pending_sl.pop(trade_id)
        position = self._active.get(trade_id)
        if position is None:
            return False

        # Commit to confirmed state
        self._confirmed_sl[trade_id] = pending

        # Update actual position state
        object.__setattr__(position, 'current_sl', pending)

        # Check if breakeven triggered
        if pending == position.entry_price:
            object.__setattr__(position, 'breakeven_triggered', True)

        logger.info(
            "SL committed: %s SL=%.5f (pending removed)",
            trade_id, pending,
        )
        return True

    def rollback_sl(self, trade_id: str) -> bool:
        """Rollback pending SL without committing.

        Called when broker confirmation fails after all retries.

        Returns:
            True if pending SL was rolled back, False if nothing pending.
        """
        if trade_id not in self._pending_sl:
            return False

        pending = self._pending_sl.pop(trade_id)
        logger.warning(
            "SL rollback: %s discarded pending=%.5f, keeping confirmed=%.5f",
            trade_id, pending,
            self._confirmed_sl.get(trade_id, 0.0),
        )
        return True

    def get_confirmed_sl(self, trade_id: str) -> Optional[float]:
        """Get the last broker-confirmed SL for a position."""
        return self._confirmed_sl.get(trade_id)

    def get_current_sl(self, trade_id: str) -> Optional[float]:
        """Get the current SL for a position (confirmed, not pending)."""
        position = self._active.get(trade_id)
        if position is None:
            return None
        return position.current_sl

    def get_trade_history(self, trade_id: str) -> list[LifecycleEvent]:
        """Get all events for a specific trade."""
        return [e for e in self._events if e.trade_id == trade_id]
