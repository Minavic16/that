"""
NQTS Notification Pipeline — Canonical Event Model
===================================================

Defines the canonical NQTS event and event taxonomy.

Events are the ONLY way components communicate with the notification system.
No component should send Telegram messages, emails, or push notifications directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Notification severity levels."""
    INFORMATION = "INFORMATION"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


# ---------------------------------------------------------------------------
# Event Taxonomy
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Canonical NQTS event taxonomy.

    Only events actually supportable by the current architecture are included.
    """

    # System
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_STOPPED = "SYSTEM_STOPPED"
    SYSTEM_HEALTH_DEGRADED = "SYSTEM_HEALTH_DEGRADED"
    SYSTEM_HEALTH_FAILED = "SYSTEM_HEALTH_FAILED"

    # Execution
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_FAILED = "ORDER_FAILED"
    EXECUTION_RETRY = "EXECUTION_RETRY"

    # Position / Lifecycle
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    STOP_MODIFIED = "STOP_MODIFIED"
    STOP_MODIFICATION_FAILED = "STOP_MODIFICATION_FAILED"
    POSITION_REQUIRES_RECONCILIATION = "POSITION_REQUIRES_RECONCILIATION"

    # Protection
    PROTECTION_MODIFICATION_FAILED = "PROTECTION_MODIFICATION_FAILED"
    PROTECTION_RETRY = "PROTECTION_RETRY"
    PROTECTION_CONFIRMED = "PROTECTION_CONFIRMED"

    # Risk / Safety
    RISK_LIMIT_WARNING = "RISK_LIMIT_WARNING"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    CIRCUIT_BREAKER_RESET = "CIRCUIT_BREAKER_RESET"
    UNEXPECTED_EXPOSURE = "UNEXPECTED_EXPOSURE"

    # Monitoring
    HIGH_SPREAD = "HIGH_SPREAD"
    HIGH_LATENCY = "HIGH_LATENCY"
    EXECUTION_DEGRADATION = "EXECUTION_DEGRADATION"

    # Reconciliation
    RECONCILIATION_CRITICAL = "RECONCILIATION_CRITICAL"
    RECONCILIATION_GHOST = "RECONCILIATION_GHOST"
    RECONCILIATION_ORPHAN = "RECONCILIATION_ORPHAN"


# ---------------------------------------------------------------------------
# Canonical Event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NQTSEvent:
    """Canonical NQTS event.

    Not every field will be populated for every event.
    Use None for absent fields.
    """
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType = EventType.SYSTEM_STARTED
    severity: Severity = Severity.INFORMATION
    source: Optional[str] = None
    strategy_id: Optional[str] = None
    experiment_id: Optional[str] = None
    symbol: Optional[str] = None
    trade_id: Optional[str] = None
    message: str = ""
    payload: Optional[dict[str, Any]] = None
    dedupe_key: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging/dispatch."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "source": self.source,
            "strategy_id": self.strategy_id,
            "experiment_id": self.experiment_id,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "message": self.message,
            "payload": self.payload,
            "dedupe_key": self.dedupe_key,
        }


# ---------------------------------------------------------------------------
# Event Builder (convenience)
# ---------------------------------------------------------------------------


def build_event(
    event_type: EventType,
    severity: Severity = Severity.INFORMATION,
    *,
    message: str = "",
    source: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    experiment_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> NQTSEvent:
    """Build a canonical NQTS event with convenience defaults."""
    return NQTSEvent(
        event_type=event_type,
        severity=severity,
        source=source,
        strategy_id=strategy_id,
        experiment_id=experiment_id,
        symbol=symbol,
        trade_id=trade_id,
        message=message,
        payload=payload,
        dedupe_key=dedupe_key,
    )
