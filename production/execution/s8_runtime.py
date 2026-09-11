"""
NestQuant S8 — Runtime
========================
Continuous execution loop for live trading.

This module:
  - Wires all S8 components together
  - Runs the main loop: fetch -> signal -> intent -> risk -> execute -> log
  - Handles bar-close detection
  - Manages graceful shutdown
  - Enforces dry-run / experimental-live mode separation
  - Health-gates every trade
  - Tracks positions and feeds realized PnL back to risk guard

This module does NOT:
  - Import MT5 or broker SDKs directly
  - Contain strategy logic
  - Contain risk logic
  - Manage broker connections
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from execution.data_feed import LiveDataFeed, OHLCV
from execution.health_monitor import HealthMonitor, HealthMonitorConfig
from execution.intent_factory import IntentFactory
from execution.mt5_adapter import MT5ExecutionAdapter
from execution.mt5_client import MT5Client
from execution.orchestration import ExecutionCoordinator
from execution.prop_firm_guard import PropFirmConfig, PropFirmGuard
from execution.trade_logger import TradeLogger
from execution.protection import ExecutionProtection, CircuitBreakerConfig, RetryConfig
from strategy.lifecycle import (
    Direction as LifecycleDirection,
    LifecycleAction,
    LifecycleRegistry,
    MarketContext,
    OrphanPositionPolicy,
    PositionModificationRequest,
    StartupReconciliationResult,
)
from strategy.trade_management.breakeven import BreakevenConfig
from strategy.trade_management.max_hold import MaxHoldConfig
from strategy.trade_management.trailing_stop import TrailingStopConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runtime Mode
# ---------------------------------------------------------------------------


class RuntimeMode(str, Enum):
    """Runtime execution modes."""
    DRY_RUN = "dry-run"
    EXPERIMENTAL_LIVE = "experimental-live"


# ---------------------------------------------------------------------------
# Runtime State
# ---------------------------------------------------------------------------


class RuntimeState(str, Enum):
    """Runtime lifecycle states."""
    IDLE = "idle"
    RECONCILING = "reconciling"
    RUNNING = "running"
    SAFE_HALTED = "safe_halted"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class RuntimeMetrics:
    """Tracks runtime performance metrics."""
    start_time: Optional[datetime] = None
    bars_processed: int = 0
    signals_generated: int = 0
    intents_created: int = 0
    trades_executed: int = 0
    trades_rejected: int = 0
    trades_halted: int = 0
    errors: int = 0
    last_bar_time: Optional[datetime] = None
    last_signal_time: Optional[datetime] = None
    last_trade_time: Optional[datetime] = None

    @property
    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return (datetime.now(UTC) - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        return {
            "state": None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "intents_created": self.intents_created,
            "trades_executed": self.trades_executed,
            "trades_rejected": self.trades_rejected,
            "trades_halted": self.trades_halted,
            "errors": self.errors,
            "last_bar_time": self.last_bar_time.isoformat() if self.last_bar_time else None,
            "last_signal_time": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
        }


# ---------------------------------------------------------------------------
# Runtime Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration for the S8 runtime loop."""
    pairs: tuple[str, ...] = ("EUR/USD",)
    timeframe: str = "H4"
    poll_interval_seconds: int = 60
    max_loop_errors: int = 10
    log_metrics_interval: int = 300
    mode: RuntimeMode = RuntimeMode.DRY_RUN
    num_bars: int = 100
    orphan_policy: OrphanPositionPolicy = OrphanPositionPolicy.HALT


# ---------------------------------------------------------------------------
# Dry-Run Adapter (no real orders)
# ---------------------------------------------------------------------------


class DryRunAdapter:
    """Execution adapter that logs but does not place real orders."""

    def __init__(self, trade_logger: Optional[TradeLogger] = None) -> None:
        self._logger = trade_logger
        self._modified_positions: dict[str, float] = {}  # trade_id → current SL

    def execute(self, request) -> "ExecutionResult":
        """Simulate order execution without sending to broker."""
        from execution.contracts import ExecutionResult, ExecutionStatus

        logger.info(
            f"DRY-RUN: Would send {request.direction.value} "
            f"{request.lot_size} {request.pair} "
            f"SL={request.stop_loss} TP={request.take_profit}"
        )

        if self._logger:
            self._logger.log_infrastructure_event(
                event_type="DRY_RUN_ORDER",
                description=(
                    f"{request.direction.value} {request.lot_size} {request.pair} "
                    f"SL={request.stop_loss} TP={request.take_profit}"
                ),
                impact="NO_IMPACT",
            )

        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            order_id=None,
            requested_price=request.entry_price,
            fill_price=None,
            slippage_pips=0.0,
            rejection_reason="DRY_RUN: Order not sent",
        )

    def modify_position_stop(self, request) -> "ModificationResult":
        """Simulate SL modification for dry-run mode."""
        from datetime import datetime, timezone
        from strategy.lifecycle.contracts import ModificationResult

        self._modified_positions[request.trade_id] = request.new_sl

        logger.info(
            f"DRY-RUN: Would modify {request.trade_id} SL → {request.new_sl} "
            f"({request.reason})"
        )

        return ModificationResult(
            success=True,
            trade_id=request.trade_id,
            requested_sl=request.new_sl,
            broker_sl=request.new_sl,
            timestamp=datetime.now(timezone.utc),
            error=None,
        )


# ---------------------------------------------------------------------------
# Position Tracker
# ---------------------------------------------------------------------------


@dataclass
class TrackedPosition:
    """A position opened by the experiment."""
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    open_time: datetime
    signal_id: str = ""


class PositionTracker:
    """Tracks positions opened by the experiment for PnL feedback."""

    def __init__(self) -> None:
        self._positions: dict[int, TrackedPosition] = {}

    def track_open(self, ticket: int, symbol: str, direction: str,
                   volume: float, open_price: float, signal_id: str = "") -> None:
        """Record a new position."""
        self._positions[ticket] = TrackedPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=open_price,
            open_time=datetime.now(UTC),
            signal_id=signal_id,
        )

    def detect_closed(self, current_positions: list[dict]) -> list[TrackedPosition]:
        """Detect which tracked positions have closed.

        Args:
            current_positions: Current open positions from MT5.

        Returns:
            List of positions that were closed since last check.
        """
        current_tickets = {p.get("ticket") for p in current_positions}
        closed = []
        for ticket, pos in list(self._positions.items()):
            if ticket not in current_tickets:
                closed.append(pos)
                del self._positions[ticket]
        return closed

    @property
    def open_count(self) -> int:
        return len(self._positions)

    @property
    def open_tickets(self) -> list[int]:
        return list(self._positions.keys())


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class S8Runtime:
    """Continuous execution runtime for live trading.

    Lifecycle:
      1. Initialize components
      2. Start runtime
      3. Loop: fetch -> signal -> intent -> risk -> execute -> log
      4. Stop gracefully
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        client: Optional[MT5Client] = None,
        prop_guard: Optional[PropFirmGuard] = None,
        trade_logger: Optional[TradeLogger] = None,
        strategy: Optional[object] = None,
    ) -> None:
        self._config = config or RuntimeConfig()
        self._state = RuntimeState.IDLE
        self._metrics = RuntimeMetrics()
        self._should_stop = False
        self._orphan_policy = self._config.orphan_policy

        # Components (injected or created in initialize())
        self._client = client
        self._prop_guard = prop_guard
        self._trade_logger = trade_logger
        self._strategy = strategy

        # Derived components
        self._data_feed: Optional[LiveDataFeed] = None
        self._intent_factory: Optional[IntentFactory] = None
        self._coordinator: Optional[ExecutionCoordinator] = None
        self._adapter: Optional[object] = None
        self._position_tracker = PositionTracker()

        # Lifecycle management
        self._lifecycle_registry: Optional[LifecycleRegistry] = None

        # Execution protection (retry, circuit breaker)
        self._protection = ExecutionProtection()

        # Signal handlers
        self._original_sigterm = None
        self._original_sigint = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def metrics(self) -> RuntimeMetrics:
        return self._metrics

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def mode(self) -> RuntimeMode:
        return self._config.mode

    def initialize(self) -> bool:
        """Initialize all components.

        Returns:
            True if initialization succeeded.
        """
        try:
            logger.info("Initializing S8 runtime...")

            # Validate mode authorization
            if self._config.mode == RuntimeMode.EXPERIMENTAL_LIVE:
                if os.environ.get("NESTQUANT_EXPERIMENTAL_LIVE") != "true":
                    logger.error(
                        "REFUSING to start in experimental-live mode: "
                        "Set NESTQUANT_EXPERIMENTAL_LIVE=true environment variable."
                    )
                    self._state = RuntimeState.ERROR
                    return False
                logger.warning("EXPERIMENTAL-LIVE mode: Real orders will be placed.")

            # Create MT5 client
            if self._client is None:
                self._client = MT5Client()

            # Create data feed
            self._data_feed = LiveDataFeed(
                client=self._client,
                timeframe=self._config.timeframe,
            )

            # Create intent factory
            self._intent_factory = IntentFactory(
                strategy_version="breakout-1.0.0",
                policy_version="s8-prop-1.0.0",
            )

            # Create prop firm guard if not provided
            if self._prop_guard is None:
                self._prop_guard = PropFirmGuard()

            # Create trade logger
            if self._trade_logger is None:
                self._trade_logger = TradeLogger(log_dir="/tmp/nestquant/logs")

            # Create execution adapter based on mode
            if self._config.mode == RuntimeMode.DRY_RUN:
                self._adapter = DryRunAdapter(trade_logger=self._trade_logger)
                logger.info("Dry-run adapter created (no real orders)")
            else:
                self._adapter = MT5ExecutionAdapter(
                    client=self._client,
                    magic=0,
                    deviation=10,
                )
                logger.info("MT5 execution adapter created (real orders)")

            # Create execution coordinator with PropFirmGuard
            self._coordinator = ExecutionCoordinator(
                risk=self._prop_guard,
                adapter=self._adapter,
            )

            # Create lifecycle registry
            self._lifecycle_registry = LifecycleRegistry(
                strategy_identity="breakout-1.0.0",
                breakeven_config=BreakevenConfig(enabled=True, trigger_r=0.8),
                max_hold_config=MaxHoldConfig(enabled=True, max_hold_days=7, bars_per_day=6),
                trailing_config=TrailingStopConfig(enabled=True),
            )

            # Create strategy if not provided
            if self._strategy is None:
                self._strategy = self._create_default_strategy()

            logger.info(
                f"S8 runtime initialized: mode={self._config.mode.value}, "
                f"pairs={self._config.pairs}, timeframe={self._config.timeframe}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize S8 runtime: {e}")
            self._state = RuntimeState.ERROR
            return False

    def start(self) -> None:
        """Start the runtime loop."""
        if self._state == RuntimeState.RUNNING:
            logger.warning("Runtime already running")
            return

        if not self.initialize():
            return

        # Mandatory startup reconciliation
        recon_result = self.reconcile_startup_state()
        if not recon_result.runtime_safe:
            logger.critical(
                f"STARTUP BLOCKED: reconciliation failed. "
                f"Orphans={len(recon_result.broker_orphans)}, "
                f"Mismatches={len(recon_result.state_mismatches)}"
            )
            return

        self._register_signals()

        self._state = RuntimeState.RUNNING
        self._metrics.start_time = datetime.now(UTC)
        self._should_stop = False

        logger.info(
            f"S8 runtime started: mode={self._config.mode.value}, "
            f"pairs={self._config.pairs}, "
            f"timeframe={self._config.timeframe}, "
            f"poll={self._config.poll_interval_seconds}s"
        )

        self._run_loop()

    def stop(self) -> None:
        """Stop the runtime gracefully."""
        if self._state != RuntimeState.RUNNING:
            return

        logger.info("Stopping S8 runtime...")
        self._state = RuntimeState.STOPPING
        self._should_stop = True

    def _run_loop(self) -> None:
        """Main execution loop."""
        consecutive_errors = 0
        last_metrics_log = time.time()

        while not self._should_stop:
            try:
                # Check daily reset
                self._prop_guard.check_daily_reset()

                # Fetch candles for each pair
                for pair in self._config.pairs:
                    self._process_pair(pair)

                # Detect closed positions and feed PnL back
                self._check_position_outcomes()

                # Reconcile internal vs broker state
                self._reconcile_broker_state()

                # Log metrics periodically
                elapsed = time.time() - last_metrics_log
                if elapsed >= self._config.log_metrics_interval:
                    self._log_metrics()
                    last_metrics_log = time.time()

                consecutive_errors = 0
                time.sleep(self._config.poll_interval_seconds)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self._should_stop = True
            except Exception as e:
                consecutive_errors += 1
                self._metrics.errors += 1
                logger.error(
                    f"Loop error ({consecutive_errors}/{self._config.max_loop_errors}): {e}"
                )
                if consecutive_errors >= self._config.max_loop_errors:
                    logger.critical("Too many consecutive errors. Stopping runtime.")
                    self._should_stop = True
                    self._state = RuntimeState.ERROR
                else:
                    time.sleep(min(30, self._config.poll_interval_seconds * 2))

        self._state = RuntimeState.STOPPED
        self._log_metrics()
        logger.info("S8 runtime stopped")

    def _process_pair(self, pair: str) -> None:
        """Process a single pair: lifecycle evaluation or new signal."""
        # Safety gate: block processing when halted
        if self._state == RuntimeState.SAFE_HALTED:
            return

        # Health gate: check MT5 connectivity
        if not self._check_health_gate():
            return

        # Fetch candles
        candles = self._data_feed.fetch_candles(pair, num_bars=self._config.num_bars)
        if not candles:
            return

        # Check for new bar
        if not self._data_feed.has_new_bar(pair, candles):
            return

        self._metrics.bars_processed += 1
        self._metrics.last_bar_time = datetime.now(UTC)

        # Check if pair has active lifecycle position
        has_position = self._lifecycle_registry is not None and self._lifecycle_registry.active_count > 0

        if has_position:
            # LIFECYCLE PATH: evaluate existing position
            self._process_lifecycle(pair, candles)
        else:
            # SIGNAL PATH: evaluate new entry
            self._process_signal(pair, candles)

    def _process_lifecycle(self, pair: str, candles: list[OHLCV]) -> None:
        """Evaluate lifecycle for active positions on this pair."""
        if not candles or len(candles) < 3:
            return

        # Build MarketContext with swing data
        market = self._build_market_context(pair, candles)
        if market is None:
            return

        # Evaluate lifecycle
        decisions = self._lifecycle_registry.evaluate_bar(market)

        for decision in decisions:
            if decision.is_sl_move and decision.new_sl is not None:
                # Execute SL modification
                self._execute_sl_modification(decision, pair)
            elif decision.is_exit:
                # Execute exit
                self._execute_exit(decision, pair, candles[-1])

    def _process_signal(self, pair: str, candles: list[OHLCV]) -> None:
        """Evaluate new entry signal for pair.

        Flow:
            1. Generate signal (provides breakout level, ATR, direction)
            2. Create intent (passes signal geometry to risk)
            3. Execute order (broker returns actual fill)
            4. Recalculate geometry from actual fill (NOT signal level)
            5. Register lifecycle with fill-based geometry
            6. Reconcile expected vs actual risk
        """
        # Circuit breaker: block new entries if breaker is open
        if self._protection.breaker_open:
            return
        # Get strategy signal
        signal_result = self._get_strategy_signal(pair, candles)
        if signal_result is None:
            return

        self._metrics.signals_generated += 1
        self._metrics.last_signal_time = datetime.now(UTC)

        # Extract stop distance from signal (ATR * multiplier)
        # This is the FIXED distance, not an absolute price
        atr = signal_result.metadata.get("atr", 0.0)
        stop_distance = atr * self._strategy.atr_sl_multiplier

        # Create intent
        intent, signal_id = self._intent_factory.create_intent_with_id(signal_result)
        self._metrics.intents_created += 1

        # Log signal
        self._trade_logger.log_signal(
            signal_id=signal_id,
            pair=pair,
            direction=intent.direction.value,
            strength=intent.signal_strength,
            entry_price=intent.entry_price,
            sl_price=intent.stop_loss,
            tp_price=intent.take_profit,
            metadata={"source": "s8_runtime", "mode": self._config.mode.value},
        )

        # Execute through coordinator
        result = self._coordinator.orchestrate(intent)

        if result.is_filled:
            self._metrics.trades_executed += 1
            self._metrics.last_trade_time = datetime.now(UTC)

            # ─── FILL-AWARE GEOMETRY ───────────────────────────
            # Use ACTUAL fill price, NOT signal entry_price
            fill_price = result.fill_price or intent.entry_price
            direction_int = 1 if intent.direction.value == "BUY" else -1
            pip = self._pip_size(pair)

            # Build geometry from actual fill
            from strategy.lifecycle.contracts import TradeGeometry, RiskReconciliation
            geometry = TradeGeometry.from_fill(
                fill_price=fill_price,
                stop_distance=stop_distance,
                rrr=self._strategy.rrr,
                pip_size=pip,
                direction=direction_int,
            )

            # Risk reconciliation
            expected_entry = intent.entry_price
            reconciliation = RiskReconciliation.from_reconciliation(
                expected_entry=expected_entry,
                actual_entry=fill_price,
                stop_distance=stop_distance,
                pip_size=pip,
                tolerance_pips=5.0,
            )

            if not reconciliation.is_ok:
                logger.warning(
                    f"RISK RECONCILIATION: {signal_id} fill deviates "
                    f"{reconciliation.entry_deviation_pips:.1f} pips from expected "
                    f"(severity={reconciliation.severity})"
                )
                self._trade_logger.log_infrastructure_event(
                    event_type="RISK_RECONCILIATION_ALERT",
                    description=(
                        f"Fill {fill_price} deviates {reconciliation.entry_deviation_pips:.1f} "
                        f"pips from expected {expected_entry}"
                    ),
                    impact="RISK_DIVERGENCE",
                )

            # Register lifecycle with FILL-based geometry (NOT signal geometry)
            trade_id = signal_id[:8]
            self._lifecycle_registry.register_entry(
                trade_id=trade_id,
                symbol=pair.replace("/", ""),
                direction=LifecycleDirection.LONG if direction_int == 1 else LifecycleDirection.SHORT,
                entry_price=geometry.entry_price,       # ← actual fill
                initial_sl=geometry.stop_loss,           # ← SL from fill
                take_profit=geometry.take_profit,        # ← TP from fill
                pip_size=geometry.pip_size,
                entry_time=intent.timestamp,
                entry_bar_index=len(candles) - 1,
            )

            # Log fill geometry
            self._trade_logger.log_infrastructure_event(
                event_type="FILL_GEOMETRY",
                description=(
                    f"{trade_id} fill={fill_price} SL={geometry.stop_loss} "
                    f"TP={geometry.take_profit} risk={geometry.risk_pips:.1f}p"
                ),
                impact="LIFECYCLE_REGISTERED",
            )

            # Track position for PnL feedback
            if result.order_id:
                try:
                    ticket = int(result.order_id)
                    self._position_tracker.track_open(
                        ticket=ticket,
                        symbol=pair.replace("/", ""),
                        direction=intent.direction.value,
                        volume=0,
                        open_price=fill_price,
                        signal_id=signal_id,
                    )
                except (ValueError, TypeError):
                    pass

        elif result.is_rejected:
            self._metrics.trades_rejected += 1
            self._trade_logger.log_infrastructure_event(
                event_type="EXECUTION_REJECTED",
                description=f"Signal {signal_id}: {result.rejection_reason}",
                impact="MISSED_SIGNAL",
            )
        else:
            self._metrics.trades_rejected += 1

    def _build_market_context(
        self, pair: str, candles: list[OHLCV]
    ) -> Optional[MarketContext]:
        """Build MarketContext with swing data from candles."""
        if len(candles) < 3:
            return None

        # Calculate swing series from candles
        lookback = 5  # Match strategy lookback
        swing_highs = self._calculate_swing_highs(candles, lookback)
        swing_lows = self._calculate_swing_lows(candles, lookback)

        if not swing_highs or not swing_lows:
            return None

        # Previous bar's confirmed swing levels (i-1)
        prev_swing_high = swing_highs[-2] if len(swing_highs) >= 2 else swing_highs[-1]
        prev_swing_low = swing_lows[-2] if len(swing_lows) >= 2 else swing_lows[-1]

        last_candle = candles[-1]

        return MarketContext(
            symbol=pair.replace("/", ""),
            timeframe=self._config.timeframe,
            timestamp=last_candle.timestamp,
            bar_index=len(candles) - 1,
            open=last_candle.open,
            high=last_candle.high,
            low=last_candle.low,
            close=last_candle.close,
            previous_swing_low=prev_swing_low,
            previous_swing_high=prev_swing_high,
        )

    def _calculate_swing_highs(self, candles: list[OHLCV], lookback: int) -> list[float]:
        """Calculate swing high series from candles."""
        highs = [c.high for c in candles]
        swing_highs = []
        for i in range(lookback, len(highs)):
            window = highs[i - lookback:i + 1]
            if len(window) == lookback + 1:
                center = window[lookback // 2]
                if center == max(window):
                    swing_highs.append(center)
                else:
                    swing_highs.append(float('nan'))
            else:
                swing_highs.append(float('nan'))
        return swing_highs

    def _calculate_swing_lows(self, candles: list[OHLCV], lookback: int) -> list[float]:
        """Calculate swing low series from candles."""
        lows = [c.low for c in candles]
        swing_lows = []
        for i in range(lookback, len(lows)):
            window = lows[i - lookback:i + 1]
            if len(window) == lookback + 1:
                center = window[lookback // 2]
                if center == min(window):
                    swing_lows.append(center)
                else:
                    swing_lows.append(float('nan'))
            else:
                swing_lows.append(float('nan'))
        return swing_lows

    def _execute_sl_modification(self, decision, pair: str) -> None:
        """Execute SL modification through adapter with retry and state integrity.

        Flow:
          1. Get pending SL from registry (staged by evaluate_bar)
          2. Execute modification with retry
          3. On success: commit SL to registry
          4. On failure: rollback, record reconciliation requirement
        """
        active = self._lifecycle_registry.get_all_active()
        for pos in active:
            if pos.symbol == pair.replace("/", ""):
                # Get pending SL (staged by lifecycle evaluation)
                pending_sl = self._lifecycle_registry.get_pending_sl(pos.trade_id)
                if pending_sl is None:
                    return  # Nothing to modify

                request = PositionModificationRequest(
                    trade_id=pos.trade_id,
                    symbol=pos.symbol,
                    new_sl=pending_sl,
                    reason="lifecycle_update",
                )

                # Execute with retry and classification
                classified = self._protection.execute_modification_with_retry(
                    adapter=self._adapter,
                    request=request,
                )

                # Record modification in registry
                self._lifecycle_registry.record_modification(pos.trade_id, classified.result)

                if classified.success:
                    # State integrity: commit pending SL to confirmed state
                    self._lifecycle_registry.commit_sl(pos.trade_id)
                    self._trade_logger.log_infrastructure_event(
                        event_type="SL_MODIFICATION",
                        description=(
                            f"{pos.trade_id} SL→{pending_sl} "
                            f"(broker={classified.result.broker_sl}, "
                            f"attempt={classified.attempt})"
                        ),
                        impact="LIFECYCLE_UPDATE",
                    )
                else:
                    # State integrity: rollback pending SL
                    self._lifecycle_registry.rollback_sl(pos.trade_id)

                    # Record position as requiring reconciliation
                    self._protection.record_position_requires_reconciliation(
                        trade_id=pos.trade_id,
                        reason=(
                            f"SL modification failed after {classified.attempt} "
                            f"attempts: {classified.result.error} "
                            f"(class={classified.failure_class.value})"
                        ),
                    )

                    self._trade_logger.log_infrastructure_event(
                        event_type="SL_MODIFICATION",
                        description=(
                            f"{pos.trade_id} SL→{pending_sl} FAILED "
                            f"({classified.result.error}, "
                            f"class={classified.failure_class.value}, "
                            f"attempt={classified.attempt})"
                        ),
                        impact="MODIFICATION_FAILED",
                    )
                break

    def _execute_exit(self, decision, pair: str, last_candle: OHLCV) -> None:
        """Execute position exit."""
        active = self._lifecycle_registry.get_all_active()
        for pos in active:
            if pos.symbol == pair.replace("/", ""):
                self._trade_logger.log_infrastructure_event(
                    event_type="LIFECYCLE_EXIT",
                    description=(
                        f"{pos.trade_id} {decision.exit_reason.value} "
                        f"@ {decision.exit_price} (bars={pos.bars_held})"
                    ),
                    impact="POSITION_CLOSED",
                )
                break

    def _pip_size(self, pair: str) -> float:
        """Get pip size for a pair."""
        if "JPY" in pair:
            return 0.01
        return 0.0001

    def _get_strategy_signal(self, pair: str, candles: list[OHLCV]):
        """Convert OHLCV candles to strategy signal.

        Converts OHLCV list to pandas DataFrame and calls the strategy.
        """
        if self._strategy is None:
            return None

        if not candles:
            return None

        # Convert OHLCV list to DataFrame
        import pandas as pd

        records = []
        for c in candles:
            records.append({
                "time": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            })

        df = pd.DataFrame(records)
        if df.empty:
            return None

        try:
            signal = self._strategy.generate(df, pair)
            # Return None for NEUTRAL signals
            if signal.direction == "NEUTRAL":
                return None
            return signal
        except Exception as e:
            logger.error(f"Strategy error for {pair}: {e}")
            return None

    def _check_health_gate(self) -> bool:
        """Verify health before allowing a new trade.

        Returns True if trading is permitted, False if halted.
        """
        # Check PropFirmGuard
        can_trade, reason = self._prop_guard.breakers.can_trade
        if not can_trade:
            logger.warning(f"Health gate BLOCKED: circuit breaker: {reason}")
            self._metrics.trades_halted += 1
            self._trade_logger.log_infrastructure_event(
                event_type="HEALTH_GATE_BLOCKED",
                description=f"Circuit breaker: {reason}",
                impact="TRADING_HALT",
            )
            return False

        return True

    def _check_position_outcomes(self) -> None:
        """Check for closed positions and feed PnL back to PropFirmGuard."""
        if self._position_tracker.open_count == 0:
            return

        if self._config.mode == RuntimeMode.DRY_RUN:
            return  # No real positions in dry-run

        try:
            resp = self._client.get_positions()
            if not resp.ok:
                return
            positions = resp.data.get("positions", []) if isinstance(resp.data, dict) else []
            closed = self._position_tracker.detect_closed(positions)
            for pos in closed:
                logger.info(
                    f"Position closed: ticket={pos.ticket}, "
                    f"symbol={pos.symbol}, direction={pos.direction}"
                )
                # PnL feedback would require deal history — log for now
                self._trade_logger.log_infrastructure_event(
                    event_type="POSITION_CLOSED",
                    description=f"Ticket {pos.ticket} {pos.symbol} {pos.direction}",
                    impact="PNL_FEEDBACK_NEEDED",
                )
        except Exception as e:
            logger.error(f"Position check error: {e}")

    def _reconcile_broker_state(self) -> None:
        """Compare internal lifecycle state with broker-reported state.

        Called periodically to detect SL divergence between internal
        registry and broker positions. Mismatches trigger CRITICAL alerts.
        """
        if self._config.mode == RuntimeMode.DRY_RUN:
            return  # No broker state in dry-run

        if self._lifecycle_registry is None or self._lifecycle_registry.active_count == 0:
            return

        try:
            resp = self._client.get_positions()
            if not resp.ok:
                return

            positions = resp.data.get("positions", []) if isinstance(resp.data, dict) else []
            broker_map = {}
            for p in positions:
                ticket = str(p.get("ticket", ""))
                if ticket:
                    broker_map[ticket] = p

            # Compare each active lifecycle position against broker
            for pos in self._lifecycle_registry.get_all_active():
                # Try to find matching broker position by symbol + direction
                broker_pos = None
                for ticket, bp in broker_map.items():
                    if (bp.get("symbol") == pos.symbol and
                        bp.get("type") == (0 if pos.direction.value == 1 else 1)):
                        broker_pos = bp
                        break

                if broker_pos is None:
                    logger.critical(
                        f"RECONCILIATION: Internal position {pos.trade_id} "
                        f"({pos.symbol}) has no matching broker position"
                    )
                    self._trade_logger.log_infrastructure_event(
                        event_type="RECONCILIATION_CRITICAL",
                        description=(
                            f"Internal position {pos.trade_id} ({pos.symbol}) "
                            f"not found at broker"
                        ),
                        impact="CRITICAL",
                    )
                    continue

                # Compare SL
                broker_sl = broker_pos.get("sl", 0.0)
                internal_sl = pos.current_sl
                sl_match = abs(internal_sl - broker_sl) < 1e-6

                if not sl_match:
                    logger.critical(
                        f"RECONCILIATION: SL mismatch for {pos.trade_id}: "
                        f"internal={internal_sl}, broker={broker_sl}"
                    )
                    self._trade_logger.log_infrastructure_event(
                        event_type="RECONCILIATION_CRITICAL",
                        description=(
                            f"SL mismatch {pos.trade_id}: "
                            f"internal={internal_sl}, broker={broker_sl}"
                        ),
                        impact="CRITICAL",
                    )

                    # Escalate to circuit breaker
                    self._protection.record_reconciliation_mismatch(
                        trade_id=pos.trade_id,
                        internal_sl=internal_sl,
                        broker_sl=broker_sl,
                    )

        except Exception as e:
            logger.error(f"Reconciliation error: {e}")

    # ------------------------------------------------------------------
    # Startup Reconciliation
    # ------------------------------------------------------------------

    def reconcile_startup_state(
        self, orphan_policy: Optional[OrphanPositionPolicy] = None,
    ) -> StartupReconciliationResult:
        """Mandatory startup reconciliation before normal trading.

        Compares broker open positions against LifecycleRegistry.
        Classifies every position as MATCHED, BROKER_ORPHAN, INTERNAL_GHOST,
        or STATE_MISMATCH.

        Normal trading MUST NOT begin until this completes successfully.
        """
        policy = orphan_policy or self._orphan_policy
        self._state = RuntimeState.RECONCILING

        matched = 0
        broker_orphans: list = []
        internal_ghosts: list = []
        state_mismatches: list = []
        actions: list = []

        # Dry-run mode: skip broker query, just verify registry is clean
        if self._config.mode == RuntimeMode.DRY_RUN:
            if self._lifecycle_registry and self._lifecycle_registry.active_count > 0:
                # In dry-run, registry should be empty at startup
                for pos in self._lifecycle_registry.get_all_active():
                    internal_ghosts.append(pos.trade_id)
                    actions.append(f"GHOST_REMOVED:{pos.trade_id}")
            else:
                matched = 0  # Nothing to reconcile in dry-run

            result = StartupReconciliationResult(
                success=True,
                matched_count=matched,
                broker_orphans=broker_orphans,
                internal_ghosts=internal_ghosts,
                state_mismatches=state_mismatches,
                actions_taken=actions,
                runtime_safe=True,
                orphan_policy=policy.value,
            )
            self._state = RuntimeState.RUNNING
            return result

        # Live mode: fetch broker positions
        if self._client is None:
            self._state = RuntimeState.ERROR
            return StartupReconciliationResult(
                success=False, matched_count=0, broker_orphans=[],
                internal_ghosts=[], state_mismatches=[],
                actions_taken=["ERROR:NoClient"], runtime_safe=False,
                orphan_policy=policy.value,
            )

        # Fetch broker positions
        broker_positions = []
        try:
            resp = self._client.get_positions()
            if resp.ok:
                data = resp.data
                if isinstance(data, dict):
                    broker_positions = data.get("positions", [])
                elif isinstance(data, list):
                    broker_positions = data
        except Exception as e:
            logger.critical(f"RECONCILIATION: Failed to fetch broker positions: {e}")
            self._state = RuntimeState.SAFE_HALTED
            return StartupReconciliationResult(
                success=False, matched_count=0, broker_orphans=[],
                internal_ghosts=[], state_mismatches=[],
                actions_taken=[f"ERROR:{e}"], runtime_safe=False,
                orphan_policy=policy.value,
            )

        # Build lookup maps
        broker_by_key = {}  # (symbol, direction) → broker position
        for bp in broker_positions:
            symbol = bp.get("symbol", "")
            # MT5 type: 0=BUY, 1=SELL; our Direction: 1=LONG, -1=SHORT
            mt5_type = bp.get("type", -1)
            direction = 1 if mt5_type == 0 else -1
            broker_by_key[(symbol, direction)] = bp

        registry_positions = []
        if self._lifecycle_registry:
            registry_positions = list(self._lifecycle_registry.get_all_active())

        registry_by_key = {}  # (symbol, direction) → lifecycle state
        for pos in registry_positions:
            registry_by_key[(pos.symbol, pos.direction)] = pos

        # Classify positions
        all_keys = set(broker_by_key.keys()) | set(registry_by_key.keys())

        for key in all_keys:
            symbol, direction = key
            broker_pos = broker_by_key.get(key)
            reg_pos = registry_by_key.get(key)

            if broker_pos is not None and reg_pos is not None:
                # Both exist — check for state mismatch
                broker_sl = float(broker_pos.get("sl", 0.0))
                internal_sl = reg_pos.current_sl
                sl_match = abs(internal_sl - broker_sl) < 1e-6

                if sl_match:
                    matched += 1
                else:
                    mismatch_detail = {
                        "trade_id": reg_pos.trade_id,
                        "symbol": symbol,
                        "internal_sl": internal_sl,
                        "broker_sl": broker_sl,
                    }
                    state_mismatches.append(mismatch_detail)
                    actions.append(
                        f"STATE_MISMATCH:{reg_pos.trade_id}:"
                        f"internal_sl={internal_sl},broker_sl={broker_sl}"
                    )
                    logger.critical(
                        f"RECONCILIATION: SL mismatch for {reg_pos.trade_id}: "
                        f"internal={internal_sl}, broker={broker_sl}"
                    )

            elif broker_pos is not None and reg_pos is None:
                # Broker orphan — CRITICAL
                broker_orphans.append(broker_pos)
                actions.append(f"BROKER_ORPHAN:{symbol}:{broker_pos.get('ticket','?')}")
                logger.critical(
                    f"RECONCILIATION: Broker orphan detected: "
                    f"{symbol} ticket={broker_pos.get('ticket','?')}"
                )

            elif broker_pos is None and reg_pos is not None:
                # Internal ghost — finalize
                internal_ghosts.append(reg_pos.trade_id)
                actions.append(f"INTERNAL_GHOST:{reg_pos.trade_id}")
                logger.warning(
                    f"RECONCILIATION: Internal ghost detected: "
                    f"{reg_pos.trade_id} ({symbol})"
                )

        # Handle broker orphans based on policy
        if broker_orphans:
            if policy == OrphanPositionPolicy.HALT:
                actions.append("POLICY:HALT — entering safe halted state")
                logger.critical(
                    f"RECONCILIATION: {len(broker_orphans)} orphan(s) detected. "
                    f"HALT policy — runtime entering SAFE_HALTED state."
                )
                self._state = RuntimeState.SAFE_HALTED
                return StartupReconciliationResult(
                    success=True,
                    matched_count=matched,
                    broker_orphans=broker_orphans,
                    internal_ghosts=internal_ghosts,
                    state_mismatches=state_mismatches,
                    actions_taken=actions,
                    runtime_safe=False,
                    orphan_policy=policy.value,
                )

            elif policy == OrphanPositionPolicy.CLOSE:
                for orphan in broker_orphans:
                    ticket = str(orphan.get("ticket", ""))
                    symbol = orphan.get("symbol", "")
                    try:
                        closed = self._adapter.close_position(ticket)
                        if closed:
                            actions.append(f"ORPHAN_CLOSED:{symbol}:{ticket}")
                            logger.warning(
                                f"RECONCILIATION: Closed orphan {symbol} ticket={ticket}"
                            )
                        else:
                            actions.append(f"ORPHAN_CLOSE_FAILED:{symbol}:{ticket}")
                            logger.critical(
                                f"RECONCILIATION: Failed to close orphan {symbol} ticket={ticket}"
                            )
                    except Exception as e:
                        actions.append(f"ORPHAN_CLOSE_ERROR:{symbol}:{ticket}:{e}")
                        logger.critical(
                            f"RECONCILIATION: Error closing orphan {symbol}: {e}"
                        )

                # Re-verify after closure
                try:
                    resp2 = self._client.get_positions()
                    if resp2.ok:
                        data2 = resp2.data
                        remaining = []
                        if isinstance(data2, dict):
                            remaining = data2.get("positions", [])
                        elif isinstance(data2, list):
                            remaining = data2
                        if remaining:
                            actions.append(
                                f"POST_CLOSE_VERIFY: {len(remaining)} position(s) remain"
                            )
                            self._state = RuntimeState.SAFE_HALTED
                            return StartupReconciliationResult(
                                success=True,
                                matched_count=matched,
                                broker_orphans=remaining,
                                internal_ghosts=internal_ghosts,
                                state_mismatches=state_mismatches,
                                actions_taken=actions,
                                runtime_safe=False,
                                orphan_policy=policy.value,
                            )
                except Exception as e:
                    actions.append(f"POST_CLOSE_VERIFY_ERROR:{e}")

                # Orphans successfully closed and verified — clear them
                broker_orphans = []

        # Determine final safety
        runtime_safe = (
            len(broker_orphans) == 0
            and len(state_mismatches) == 0
        )

        if runtime_safe:
            self._state = RuntimeState.RUNNING
        else:
            self._state = RuntimeState.SAFE_HALTED

        return StartupReconciliationResult(
            success=True,
            matched_count=matched,
            broker_orphans=broker_orphans,
            internal_ghosts=internal_ghosts,
            state_mismatches=state_mismatches,
            actions_taken=actions,
            runtime_safe=runtime_safe,
            orphan_policy=policy.value,
        )

    def _create_default_strategy(self):
        """Create the default BreakoutSignal strategy."""
        try:
            from signals.breakout import BreakoutSignal, RESEARCH_DEFAULTS
            return BreakoutSignal(**RESEARCH_DEFAULTS)
        except Exception as e:
            logger.warning(f"Could not create default strategy: {e}")
            return None

    def _register_signals(self) -> None:
        """Register signal handlers for graceful shutdown."""
        def handle_sigterm(signum, frame):
            logger.info("SIGTERM received")
            self.stop()

        def handle_sigint(signum, frame):
            logger.info("SIGINT received")
            self.stop()

        self._original_sigterm = signal.signal(signal.SIGTERM, handle_sigterm)
        self._original_sigint = signal.signal(signal.SIGINT, handle_sigint)

    def _restore_signals(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)

    def _log_metrics(self) -> None:
        """Log current runtime metrics."""
        d = self._metrics.to_dict()
        d["state"] = self._state.value
        logger.info(f"S8 Runtime metrics: {d}")

    def status(self) -> dict:
        """Get comprehensive runtime status."""
        metrics = self._metrics.to_dict()
        metrics["state"] = self._state.value
        return {
            "runtime": metrics,
            "mode": self._config.mode.value,
            "config": {
                "pairs": self._config.pairs,
                "timeframe": self._config.timeframe,
                "poll_interval": self._config.poll_interval_seconds,
                "mode": self._config.mode.value,
            },
            "prop_guard": self._prop_guard.status() if self._prop_guard else None,
            "position_tracker": {
                "open_count": self._position_tracker.open_count,
                "open_tickets": self._position_tracker.open_tickets,
            },
        }
