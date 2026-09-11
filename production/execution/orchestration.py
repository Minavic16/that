"""
NestQuant Execution Orchestration — Broker-Agnostic Pipeline
============================================================
Coordinates the flow between strategy, risk, and execution layers.

Pipeline:
    TradeIntent
         ↓
    RiskEvaluator.evaluate()
         ↓
    RiskDecision
         ↓
    ExecutionCoordinator
         ↓
    ExecutionAdapter.execute()
         ↓
    ExecutionResult

Architectural rules:
  - No MT5 imports
  - No network calls
  - No strategy calculations
  - No risk calculations in coordinator
  - No logging
  - No monitoring
  - No alerts
  - Policy version mismatch → hard rejection
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nestquant.execution.contracts import (
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
    RiskDecision,
    TradeIntent,
)


# ---------------------------------------------------------------------------
# Protocol: RiskEvaluator — Strategy → Risk boundary
# ---------------------------------------------------------------------------


@runtime_checkable
class RiskEvaluator(Protocol):
    """Protocol for per-trade risk evaluation.

    An implementation receives a TradeIntent and produces a RiskDecision.
    The implementation is responsible for all risk logic: lot sizing,
    drawdown checks, exposure limits, circuit breaker integration, etc.

    The orchestration layer does NOT perform any of these calculations.
    """

    def evaluate(self, intent: TradeIntent) -> RiskDecision:
        """Evaluate a trade intent and return a risk decision.

        Args:
            intent: The strategy's trade signal.

        Returns:
            RiskDecision with approval status, lot_size, and reason.
        """
        ...


# ---------------------------------------------------------------------------
# Protocol: ExecutionAdapter — Execution → Broker boundary
# ---------------------------------------------------------------------------


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Protocol for broker-agnostic order execution.

    An implementation translates an OrderRequest into a broker-specific
    API call and returns an ExecutionResult. The implementation handles:
    - Broker connection
    - Order routing
    - Fill confirmation
    - Error handling

    The orchestration layer does NOT perform any broker interaction.
    """

    def execute(self, request: OrderRequest) -> ExecutionResult:
        """Execute an order request.

        Args:
            request: The order to execute.

        Returns:
            ExecutionResult with fill details or rejection/error status.
        """
        ...


# ---------------------------------------------------------------------------
# Orchestration error
# ---------------------------------------------------------------------------


class OrchestrationError(ValueError):
    """Raised when orchestration fails due to contract violations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# ExecutionCoordinator — the orchestration owner
# ---------------------------------------------------------------------------


class ExecutionCoordinator:
    """Orchestrates the execution pipeline.

    The coordinator owns the flow:
      1. Receive TradeIntent
      2. Ask RiskEvaluator for decision
      3. If rejected → return rejection result (no adapter call)
      4. If approved → construct OrderRequest
      5. Send OrderRequest to ExecutionAdapter
      6. Return ExecutionResult

    The coordinator does NOT:
      - Calculate risk
      - Size positions
      - Determine lot sizes
      - Evaluate drawdowns
      - Connect to brokers
      - Send network requests
    """

    def __init__(self, risk: RiskEvaluator, adapter: ExecutionAdapter) -> None:
        self._risk = risk
        self._adapter = adapter

    @property
    def risk(self) -> RiskEvaluator:
        return self._risk

    @property
    def adapter(self) -> ExecutionAdapter:
        return self._adapter

    def orchestrate(self, intent: TradeIntent) -> ExecutionResult:
        """Execute the full pipeline for a trade intent.

        Args:
            intent: The strategy's trade signal.

        Returns:
            ExecutionResult from either risk rejection or broker execution.

        Raises:
            OrchestrationError: If policy versions mismatch between intent
                and risk decision.
        """
        # Step 1: Validate the intent itself
        intent.assert_valid()

        # Step 2: Evaluate risk
        decision = self._risk.evaluate(intent)

        # Step 3: Validate the decision
        decision.assert_valid()

        # Step 4: Policy version integrity
        if decision.policy_version != intent.policy_version:
            raise OrchestrationError(
                f"Policy version mismatch: intent has '{intent.policy_version}', "
                f"decision has '{decision.policy_version}'"
            )

        # Step 5: If rejected, return rejection result without calling adapter
        if not decision.approved:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order_id=None,
                requested_price=intent.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=f"Risk rejected: {decision.reason}",
            )

        # Step 6: Approved — construct OrderRequest from intent + decision
        request = OrderRequest(
            pair=intent.pair,
            direction=intent.direction,
            lot_size=decision.lot_size,
            entry_price=intent.entry_price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            policy_version=intent.policy_version,
        )

        # Step 7: Execute via adapter
        return self._adapter.execute(request)

    def __repr__(self) -> str:
        risk_name = type(self._risk).__name__
        adapter_name = type(self._adapter).__name__
        return f"<ExecutionCoordinator(risk={risk_name}, adapter={adapter_name})>"
