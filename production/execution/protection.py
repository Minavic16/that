"""
NestQuant Execution Protection — Failure Handling & Circuit Breaking
====================================================================

Provides bounded retry, failure classification, state integrity enforcement,
and reconciliation circuit breaking for execution protection.

This module does NOT:
- Modify strategy logic
- Modify signal generation
- Modify lifecycle ordering
- Perform risk calculations
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from nestquant.production.strategy.lifecycle.contracts import ModificationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure Classification
# ---------------------------------------------------------------------------


class FailureClass(str, Enum):
    """Classification of modification failures."""
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    UNKNOWN = "UNKNOWN"


# MT5 retcodes that are permanent failures (do not retry)
NON_RETRYABLE_RETCODES = {
    10013,  # Invalid request
    10014,  # Invalid volume
    10015,  # Invalid price
    10016,  # Invalid stops
    10018,  # Market is closed
    10019,  # Not enough money
    10021,  # No quotes
    10026,  # Auto trading disabled
    10027,  # Too frequent requests
    10030,  # Invalid duration
}

# Error substrings that indicate retryable failures
RETRYABLE_ERROR_PATTERNS = [
    "Connection failed",
    "Connection refused",
    "Connection reset",
    "Connection aborted",
    "timeout",
    "timed out",
    "Temporary failure",
    "Bridge internal error",
    "502",
    "503",
    "504",
]


def classify_failure(result: ModificationResult) -> FailureClass:
    """Classify a modification failure as retryable or non-retryable.

    Args:
        result: The modification result to classify.

    Returns:
        FailureClass enum value.
    """
    if result.success:
        return FailureClass.NON_RETRYABLE  # Not a failure

    error = (result.error or "").lower()

    # Check for non-retryable MT5 retcodes
    for retcode in NON_RETRYABLE_RETCODES:
        if f"retcode {retcode}" in error:
            return FailureClass.NON_RETRYABLE

    # Check for invalid ticket
    if "invalid ticket" in error:
        return FailureClass.NON_RETRYABLE

    # Check for retryable patterns
    for pattern in RETRYABLE_ERROR_PATTERNS:
        if pattern.lower() in error:
            return FailureClass.RETRYABLE

    return FailureClass.UNKNOWN


# ---------------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for SL modification retry behavior."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt (0-indexed)."""
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_seconds)


# ---------------------------------------------------------------------------
# Circuit Breaker Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for reconciliation circuit breaker."""
    max_critical_failures: int = 3
    block_new_entries: bool = True


# ---------------------------------------------------------------------------
# Execution Protection Events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionProtectionEvent:
    """Structured event for execution protection actions."""
    event_type: str
    timestamp: datetime
    trade_id: str
    description: str
    severity: str  # INFO, WARNING, CRITICAL

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "trade_id": self.trade_id,
            "description": self.description,
            "severity": self.severity,
        }


# ---------------------------------------------------------------------------
# Modification Result with Failure Classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifiedModificationResult:
    """Modification result annotated with failure classification."""
    result: ModificationResult
    failure_class: FailureClass
    attempt: int
    total_attempts: int

    @property
    def success(self) -> bool:
        return self.result.success

    @property
    def should_retry(self) -> bool:
        return (
            not self.success
            and self.failure_class == FailureClass.RETRYABLE
            and self.attempt < self.total_attempts
        )

    @property
    def is_permanent_failure(self) -> bool:
        return (
            not self.success
            and self.failure_class in (FailureClass.NON_RETRYABLE, FailureClass.UNKNOWN)
        )


# ---------------------------------------------------------------------------
# Execution Protection
# ---------------------------------------------------------------------------


class ExecutionProtection:
    """Coordinates retry logic, failure classification, and circuit breaking.

    This is the single entry point for all execution protection concerns.
    The runtime should call execute_modification_with_retry() instead of
    calling the adapter directly.
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._retry_config = retry_config or RetryConfig()
        self._cb_config = circuit_breaker_config or CircuitBreakerConfig()
        self._sleep_fn = sleep_fn or time.sleep

        # Circuit breaker state
        self._critical_mismatch_count: int = 0
        self._breaker_open: bool = False
        self._reset_count: int = 0

        # Event log
        self._events: list[ExecutionProtectionEvent] = []

    @property
    def breaker_open(self) -> bool:
        """Whether the circuit breaker is currently blocking new entries."""
        return self._breaker_open

    @property
    def critical_mismatch_count(self) -> int:
        return self._critical_mismatch_count

    @property
    def events(self) -> list[ExecutionProtectionEvent]:
        return list(self._events)

    # ------------------------------------------------------------------
    # Retry Logic
    # ------------------------------------------------------------------

    def execute_modification_with_retry(
        self,
        adapter,
        request,
    ) -> ClassifiedModificationResult:
        """Execute SL modification with bounded retry and failure classification.

        Args:
            adapter: The execution adapter with modify_position_stop().
            request: The PositionModificationRequest.

        Returns:
            ClassifiedModificationResult with final outcome and classification.
        """
        max_attempts = self._retry_config.max_retries + 1  # 1 initial + N retries
        last_result = None

        for attempt in range(max_attempts):
            # Emit attempt event
            self._emit_event(ExecutionProtectionEvent(
                event_type="MODIFICATION_ATTEMPT",
                timestamp=datetime.now(timezone.utc),
                trade_id=request.trade_id,
                description=f"Attempt {attempt + 1}/{max_attempts} SL→{request.new_sl}",
                severity="INFO",
            ))

            # Execute
            result = adapter.modify_position_stop(request)
            failure_class = classify_failure(result)

            classified = ClassifiedModificationResult(
                result=result,
                failure_class=failure_class,
                attempt=attempt + 1,
                total_attempts=max_attempts,
            )

            if result.success:
                self._emit_event(ExecutionProtectionEvent(
                    event_type="MODIFICATION_CONFIRMED",
                    timestamp=datetime.now(timezone.utc),
                    trade_id=request.trade_id,
                    description=(
                        f"SL confirmed: requested={request.new_sl} "
                        f"broker={result.broker_sl} (attempt {attempt + 1})"
                    ),
                    severity="INFO",
                ))
                return classified

            last_result = classified

            # Check if should retry
            if not classified.should_retry:
                # Non-retryable or exhausted
                self._emit_event(ExecutionProtectionEvent(
                    event_type="MODIFICATION_FAILED",
                    timestamp=datetime.now(timezone.utc),
                    trade_id=request.trade_id,
                    description=(
                        f"SL modification failed: {result.error} "
                        f"(class={failure_class.value}, attempt {attempt + 1})"
                    ),
                    severity="CRITICAL",
                ))
                return classified

            # Retryable — emit retry event and sleep
            self._emit_event(ExecutionProtectionEvent(
                event_type="MODIFICATION_RETRY",
                timestamp=datetime.now(timezone.utc),
                trade_id=request.trade_id,
                description=(
                    f"Retryable failure: {result.error} "
                    f"(attempt {attempt + 1}/{max_attempts})"
                ),
                severity="WARNING",
            ))

            delay = self._retry_config.delay_for_attempt(attempt)
            self._sleep_fn(delay)

        # All retries exhausted
        return last_result

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def record_reconciliation_mismatch(
        self,
        trade_id: str,
        internal_sl: float,
        broker_sl: float,
    ) -> None:
        """Record a critical reconciliation mismatch.

        Increments the mismatch counter and opens the breaker
        if threshold is exceeded.
        """
        self._critical_mismatch_count += 1

        self._emit_event(ExecutionProtectionEvent(
            event_type="RECONCILIATION_CRITICAL",
            timestamp=datetime.now(timezone.utc),
            trade_id=trade_id,
            description=(
                f"SL mismatch: internal={internal_sl}, broker={broker_sl} "
                f"(count={self._critical_mismatch_count})"
            ),
            severity="CRITICAL",
        ))

        if (
            self._critical_mismatch_count >= self._cb_config.max_critical_failures
            and not self._breaker_open
        ):
            self._breaker_open = True
            self._emit_event(ExecutionProtectionEvent(
                event_type="EXECUTION_CIRCUIT_BREAKER_OPEN",
                timestamp=datetime.now(timezone.utc),
                trade_id="SYSTEM",
                description=(
                    f"Circuit breaker OPEN: {self._critical_mismatch_count} "
                    f"critical mismatches (threshold={self._cb_config.max_critical_failures})"
                ),
                severity="CRITICAL",
            ))
            logger.critical(
                f"EXECUTION CIRCUIT BREAKER OPEN: "
                f"{self._critical_mismatch_count} critical mismatches"
            )

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker.

        Allows new entries again. Mismatch counter is preserved
        for audit purposes.
        """
        if self._breaker_open:
            self._breaker_open = False
            self._reset_count += 1
            self._emit_event(ExecutionProtectionEvent(
                event_type="EXECUTION_CIRCUIT_BREAKER_RESET",
                timestamp=datetime.now(timezone.utc),
                trade_id="SYSTEM",
                description=(
                    f"Circuit breaker RESET (reset #{self._reset_count})"
                ),
                severity="INFO",
            ))
            logger.info("EXECUTION CIRCUIT BREAKER RESET")

    def record_position_requires_reconciliation(
        self,
        trade_id: str,
        reason: str,
    ) -> None:
        """Record that a position requires manual reconciliation."""
        self._emit_event(ExecutionProtectionEvent(
            event_type="POSITION_REQUIRES_RECONCILIATION",
            timestamp=datetime.now(timezone.utc),
            trade_id=trade_id,
            description=f"Position requires reconciliation: {reason}",
            severity="CRITICAL",
        ))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit_event(self, event: ExecutionProtectionEvent) -> None:
        """Record event and log it."""
        self._events.append(event)
        log_fn = {
            "INFO": logger.info,
            "WARNING": logger.warning,
            "CRITICAL": logger.critical,
        }.get(event.severity, logger.info)
        log_fn(f"EXECUTION_PROTECTION: {event.event_type}: {event.description}")
