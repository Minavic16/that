"""
NestQuant S7 Engine — Live Execution Orchestration
====================================================
Ties together all S7 execution components.

This module:
  - Creates and wires MT5Client → MT5ExecutionAdapter → RiskGuard → ExecutionCoordinator
  - Provides health monitoring
  - Provides trade logging
  - Manages position state
  - Exposes a clean execute(intent) interface

This module does NOT:
  - Import MetaTrader5 directly
  - Generate signals (that's the strategy layer's job)
  - Manage portfolio accounting
  - Perform backtesting
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from nestquant.production.execution.adapter import BaseExecutionAdapter
from nestquant.core.contracts.execution_contracts import (
    ExecutionResult,
    RiskDecision,
    TradeIntent,
)
from nestquant.production.execution.health_monitor import HealthMonitor, HealthMonitorConfig
from nestquant.production.execution.mt5_adapter import MT5ExecutionAdapter
from nestquant.production.execution.mt5_client import MT5Client
from nestquant.production.execution.orchestration import ExecutionCoordinator
from nestquant.production.execution.risk_guard import RiskGuard, RiskGuardConfig
from nestquant.production.execution.trade_logger import TradeLogger
from nestquant.production.risk.circuit_breakers import BreakerSuite

# S8 experiment identity (lazy import to avoid circular dependency)
_experiment_config = None


# ---------------------------------------------------------------------------
# S7 Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class S7Config:
    """Configuration for the S7 execution engine."""

    # MT5 connection
    mt5_base_url: str = "http://127.0.0.1:5001"
    mt5_timeout: float = 10.0
    mt5_magic: int = 0
    mt5_deviation: int = 10

    # Risk
    account_balance: float = 5_000_000.0
    leverage: int = 100
    risk_pct: float = 0.003
    max_concurrent_positions: int = 10
    max_position_size_per_pair: float = 1.0
    max_total_exposure: float = 10.0
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10

    # Health monitoring
    health_check_interval: float = 30.0
    max_consecutive_failures: int = 3

    # Logging
    log_dir: str = "/tmp/nestquant_s7_logs"

    # Policy
    policy_version: str = "s7-1.0.0"

    # S8 experiment identity
    experiment_id: str = ""
    strategy_version: str = ""
    config_hash: str = ""


# ---------------------------------------------------------------------------
# S7 Engine
# ---------------------------------------------------------------------------


class S7Engine:
    """Live execution engine for the S7 experiment.

    Wires together:
      MT5Client → MT5ExecutionAdapter → RiskGuard → ExecutionCoordinator

    Provides:
      - execute(intent) → ExecutionResult
      - health_check() → bool
      - status() → dict
      - start() / stop()
    """

    def __init__(self, config: Optional[S7Config] = None) -> None:
        """Initialize the S7 engine.

        Args:
            config: S7 configuration. Uses environment variables and defaults if None.
        """
        self._config = config or self._load_config()

        # Create components
        self._client = MT5Client(
            base_url=self._config.mt5_base_url,
            timeout=self._config.mt5_timeout,
        )
        self._adapter = MT5ExecutionAdapter(
            client=self._client,
            magic=self._config.mt5_magic,
            deviation=self._config.mt5_deviation,
        )
        self._breakers = BreakerSuite()
        self._risk_guard = RiskGuard(
            config=RiskGuardConfig(
                account_balance=self._config.account_balance,
                leverage=self._config.leverage,
                risk_pct=self._config.risk_pct,
                max_concurrent_positions=self._config.max_concurrent_positions,
                max_position_size_per_pair=self._config.max_position_size_per_pair,
                max_total_exposure=self._config.max_total_exposure,
                max_daily_loss_pct=self._config.max_daily_loss_pct,
                max_drawdown_pct=self._config.max_drawdown_pct,
            ),
            breaker_suite=self._breakers,
            policy_version=self._config.policy_version,
        )
        self._coordinator = ExecutionCoordinator(
            risk=self._risk_guard,
            adapter=self._adapter,
        )
        self._trade_logger = TradeLogger(self._config.log_dir)
        self._health_monitor = HealthMonitor(
            client=self._client,
            config=HealthMonitorConfig(
                check_interval_seconds=self._config.health_check_interval,
                max_consecutive_failures=self._config.max_consecutive_failures,
            ),
            trade_logger=self._trade_logger,
        )

    @staticmethod
    def _load_config() -> S7Config:
        """Load configuration from environment variables."""
        return S7Config(
            mt5_base_url=os.environ.get("NESTQUANT_MT5_BASE_URL", "http://127.0.0.1:5001"),
            mt5_timeout=float(os.environ.get("NESTQUANT_MT5_TIMEOUT", "10.0")),
            mt5_magic=int(os.environ.get("NESTQUANT_MT5_MAGIC", "0")),
            mt5_deviation=int(os.environ.get("NESTQUANT_MT5_DEVIATION", "10")),
            account_balance=float(os.environ.get("NESTQUANT_ACCOUNT_BALANCE", "5000000")),
            leverage=int(os.environ.get("NESTQUANT_LEVERAGE", "100")),
            risk_pct=float(os.environ.get("NESTQUANT_RISK_PCT", "0.003")),
            max_concurrent_positions=int(os.environ.get("NESTQUANT_MAX_POSITIONS", "10")),
            max_position_size_per_pair=float(os.environ.get("NESTQUANT_MAX_LOT_PER_PAIR", "1.0")),
            max_total_exposure=float(os.environ.get("NESTQUANT_MAX_TOTAL_EXPOSURE", "10.0")),
            max_daily_loss_pct=float(os.environ.get("NESTQUANT_MAX_DAILY_LOSS", "0.03")),
            max_drawdown_pct=float(os.environ.get("NESTQUANT_MAX_DD", "0.10")),
            health_check_interval=float(os.environ.get("NESTQUANT_HEALTH_INTERVAL", "30.0")),
            max_consecutive_failures=int(os.environ.get("NESTQUANT_MAX_FAILURES", "3")),
            log_dir=os.environ.get("NESTQUANT_LOG_DIR", "/tmp/nestquant_s7_logs"),
            policy_version=os.environ.get("NESTQUANT_POLICY_VERSION", "s7-1.0.0"),
            experiment_id=os.environ.get("NESTQUANT_EXPERIMENT_ID", ""),
            strategy_version=os.environ.get("NESTQUANT_STRATEGY_VERSION", ""),
            config_hash=os.environ.get("NESTQUANT_CONFIG_HASH", ""),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> S7Config:
        return self._config

    @property
    def adapter(self) -> MT5ExecutionAdapter:
        return self._adapter

    @property
    def risk_guard(self) -> RiskGuard:
        return self._risk_guard

    @property
    def coordinator(self) -> ExecutionCoordinator:
        return self._coordinator

    @property
    def trade_logger(self) -> TradeLogger:
        return self._trade_logger

    @property
    def health_monitor(self) -> HealthMonitor:
        return self._health_monitor

    def execute(self, intent: TradeIntent, signal_id: str = "") -> ExecutionResult:
        """Execute a trade intent through the full pipeline.

        Flow: intent → risk guard → order → MT5 → result

        Args:
            intent: The strategy's trade signal.
            signal_id: Optional signal ID for traceability (links to TradeLogger signal record).

        Returns:
            ExecutionResult from the execution pipeline.
        """
        # Update position state before risk check
        self._sync_positions()

        # Execute through the coordinator
        result = self._coordinator.orchestrate(intent)

        # Log the result with signal_id propagation
        self._log_execution(intent, result, signal_id=signal_id)

        # Update risk guard with any new state
        self._sync_positions()

        return result

    def health_check(self) -> bool:
        """Check if the MT5 bridge is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        status = self._health_monitor.check()
        return status.is_connected

    def status(self) -> dict:
        """Get the full engine status."""
        return {
            "config": {
                "mt5_base_url": self._config.mt5_base_url,
                "policy_version": self._config.policy_version,
                "account_balance": self._config.account_balance,
            },
            "health": self._health_monitor.status_dict(),
            "risk": self._risk_guard.status(),
            "trade_logger": self._trade_logger.count_records(),
        }

    def start(self) -> None:
        """Start the engine (health monitoring)."""
        self._health_monitor.start_monitoring()
        self._trade_logger.log_infrastructure_event(
            event_type="STARTUP",
            description="S7 engine started",
            impact="NO_IMPACT",
        )

    def stop(self) -> None:
        """Stop the engine."""
        self._health_monitor.stop_monitoring()
        self._trade_logger.log_infrastructure_event(
            event_type="SHUTDOWN",
            description="S7 engine stopped",
            impact="NO_IMPACT",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _sync_positions(self) -> None:
        """Sync open positions from MT5 to the risk guard."""
        try:
            positions = self._adapter.get_positions()
            self._risk_guard.update_positions(positions)
        except Exception:
            pass  # Position sync failure is non-fatal

    def _log_execution(
        self,
        intent: TradeIntent,
        result: ExecutionResult,
        signal_id: str = "",
    ) -> None:
        """Log an execution attempt.

        Args:
            intent: The original trade intent.
            result: The execution result.
            signal_id: Signal ID for traceability (links signal → order → fill).
        """
        if result.is_filled:
            self._trade_logger.create_order(
                signal_id=signal_id,
                order_id=result.order_id or "",
                symbol=intent.pair,
                direction=intent.direction.value,
                volume=0,  # Would need to track from risk decision
                requested_price=result.requested_price,
                sl=intent.stop_loss,
                tp=intent.take_profit,
                spread_at_submission=0.0,
                execution_latency_ms=0.0,
            )
        elif result.is_rejected or result.is_error:
            self._trade_logger.log_infrastructure_event(
                event_type="EXECUTION_FAILED",
                description=f"Signal {signal_id}: {result.rejection_reason}",
                impact="MISSED_SIGNAL",
            )

    def __repr__(self) -> str:
        conn = "connected" if self._health_monitor.is_connected else "disconnected"
        return f"<S7Engine({conn}, policy={self._config.policy_version})>"
