"""
NestQuant Execution Adapter Boundary — Broker-Agnostic Adapter Layer
====================================================================
Defines the adapter boundary for broker-agnostic order execution.

This module provides:
  - Adapter-specific exceptions
  - A base adapter class with validation boundary
  - A deterministic test adapter for unit/integration testing

Architectural rules:
  - No MT5 imports
  - No broker SDK imports
  - No network calls
  - No strategy logic
  - No risk calculations
  - No logging
  - No monitoring
  - No alerts

The ExecutionAdapter Protocol is defined in orchestration.py.
This module provides concrete base classes and test doubles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from nestquant.execution.contracts import (
    ContractValidationError,
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
)


# ---------------------------------------------------------------------------
# Adapter exceptions
# ---------------------------------------------------------------------------


class AdapterError(Exception):
    """Base exception for adapter-level errors."""


class AdapterValidationError(AdapterError):
    """Raised when the adapter receives a request it cannot process.

    This is defense-in-depth validation at the adapter boundary.
    The contracts already validate, but the adapter may have additional
    broker-specific constraints (e.g., lot size increments, session hours).

    This exception is distinct from ContractValidationError:
      - ContractValidationError = contract schema violated
      - AdapterValidationError = adapter cannot process this valid contract
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Adapter validation failed: {'; '.join(errors)}")


class AdapterConnectionError(AdapterError):
    """Raised when the adapter cannot connect to the broker.

    This is distinct from ExecutionStatus.ERROR:
      - ERROR = the broker received the order but execution failed
      - ConnectionError = the adapter cannot reach the broker at all
    """

    def __init__(self, message: str = "Adapter not connected") -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Base adapter — validation boundary
# ---------------------------------------------------------------------------


class BaseExecutionAdapter(ABC):
    """Abstract base class for execution adapters.

    Provides:
      - OrderRequest validation at the adapter boundary (defense-in-depth)
      - Template method pattern: validate → execute_impl
      - Subclasses implement execute_impl() with broker-specific logic

    Subclasses MUST NOT:
      - Import MT5 or broker SDKs at module level
      - Make network calls in __init__
      - Perform risk calculations
      - Perform strategy calculations
    """

    def __init__(self, name: str = "base") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def execute(self, request: OrderRequest) -> ExecutionResult:
        """Execute an order with validation boundary.

        Flow:
          1. Validate the request (defense-in-depth)
          2. If invalid → raise AdapterValidationError
          3. If valid → delegate to execute_impl()

        Args:
            request: The order to execute.

        Returns:
            ExecutionResult from the broker adapter.

        Raises:
            AdapterValidationError: If the request fails adapter validation.
        """
        self._validate_request(request)
        return self._execute_impl(request)

    def _validate_request(self, request: OrderRequest) -> None:
        """Validate the order request at the adapter boundary.

        This is defense-in-depth. The contracts already validate,
        but the adapter may have additional constraints.

        Override this method to add broker-specific validation.
        """
        errors = request.validate()
        if errors:
            raise AdapterValidationError(errors)

    @abstractmethod
    def _execute_impl(self, request: OrderRequest) -> ExecutionResult:
        """Broker-specific execution logic.

        Args:
            request: The validated order to execute.

        Returns:
            ExecutionResult with fill details or rejection/error status.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self._name})>"


# ---------------------------------------------------------------------------
# Test adapter — deterministic fake for testing
# ---------------------------------------------------------------------------


class FakeExecutionAdapter(BaseExecutionAdapter):
    """Deterministic fake adapter for unit/integration testing.

    Returns pre-configured ExecutionResult outcomes. Makes no broker
    calls, no network requests, and imports no broker-specific modules.

    Use ONLY for testing. Do not use in production.
    """

    def __init__(
        self,
        *,
        status: ExecutionStatus = ExecutionStatus.FILLED,
        order_id: str = "TEST-001",
        fill_price: Optional[float] = None,
        slippage_pips: float = 0.0,
        rejection_reason: Optional[str] = None,
    ) -> None:
        """Initialize the test adapter.

        Args:
            status: The execution status to return.
            order_id: The order ID to include in the result.
            fill_price: Fill price for FILLED results. If None, uses request.entry_price.
            slippage_pips: Slippage to report.
            rejection_reason: Reason for REJECTED/ERROR results.
        """
        super().__init__(name="test")
        self._status = status
        self._order_id = order_id
        self._fill_price = fill_price
        self._slippage_pips = slippage_pips
        self._rejection_reason = rejection_reason
        self._execution_count = 0
        self._last_request: Optional[OrderRequest] = None

    @property
    def execution_count(self) -> int:
        """Number of executions attempted."""
        return self._execution_count

    @property
    def last_request(self) -> Optional[OrderRequest]:
        """The last OrderRequest received, or None if no executions."""
        return self._last_request

    def _execute_impl(self, request: OrderRequest) -> ExecutionResult:
        """Return the pre-configured result."""
        self._execution_count += 1
        self._last_request = request

        if self._status == ExecutionStatus.FILLED:
            fill = self._fill_price if self._fill_price is not None else request.entry_price
            return ExecutionResult(
                status=ExecutionStatus.FILLED,
                order_id=self._order_id,
                requested_price=request.entry_price,
                fill_price=fill,
                slippage_pips=self._slippage_pips,
                rejection_reason=None,
            )
        elif self._status == ExecutionStatus.REJECTED:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=self._rejection_reason or "Broker rejected",
            )
        else:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=self._rejection_reason or "Execution failed",
            )
