"""
NQTS Notification Pipeline — Event Bus
=======================================

Central event dispatcher. Components emit events to the bus.
The bus routes events through the notification policy to channels.

Failure isolation: channel failures MUST NOT propagate to callers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from notifications.events import NQTSEvent, EventType, Severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Delivery Record
# ---------------------------------------------------------------------------


class DeliveryStatus:
    """Outcome of a notification delivery attempt."""
    SENT = "SENT"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------


class EventBus:
    """Central event dispatcher for NQTS.

    Components call bus.emit(event) to publish events.
    The bus routes events through the notification policy to channels.

    Failure isolation: channel errors are caught and logged,
    never propagated to callers.
    """

    def __init__(self, policy=None, channels=None):
        """
        Args:
            policy: NotificationPolicy instance. If None, all events are suppressed.
            channels: List of NotificationChannel instances. If None, no channels.
        """
        from notifications.policy import NotificationPolicy
        self._policy = policy or NotificationPolicy()
        self._channels = list(channels or [])
        self._event_log: list[dict] = []  # delivery audit trail
        self._handlers: list[Callable] = []  # additional event handlers

    def add_channel(self, channel) -> None:
        """Add a notification channel."""
        self._channels.append(channel)

    def add_handler(self, handler: Callable[[NQTSEvent], None]) -> None:
        """Add a raw event handler (receives all events before policy)."""
        self._handlers.append(handler)

    def emit(self, event: NQTSEvent) -> None:
        """Emit an event through the notification pipeline.

        Flow:
          1. Notify raw handlers (all events)
          2. Evaluate notification policy
          3. Dispatch to appropriate channels
          4. Record delivery outcome

        Never raises exceptions to callers.
        """
        # Step 1: Raw handlers (for logging, etc.)
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        # Step 2: Evaluate policy
        decision = self._policy.evaluate(event)

        # Step 3: Record and dispatch
        if not decision.notify:
            self._record_delivery(event, DeliveryStatus.SUPPRESSED, channels=[])
            return

        # Step 4: Dispatch to channels
        for channel_ref in decision.channels:
            # Resolve channel name to channel object
            channel = self._resolve_channel(channel_ref)
            if channel is None:
                continue
            try:
                channel.send(event)
                self._record_delivery(
                    event, DeliveryStatus.SENT, channels=[channel.name]
                )
            except Exception as e:
                logger.error(
                    f"Channel {channel.name} delivery failed: {e}"
                )
                self._record_delivery(
                    event, DeliveryStatus.FAILED,
                    channels=[channel.name], error=str(e),
                )

    def _record_delivery(
        self,
        event: NQTSEvent,
        status: str,
        channels: list[str],
        error: Optional[str] = None,
    ) -> None:
        """Record delivery outcome for audit trail."""
        record = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "timestamp": event.timestamp.isoformat(),
            "status": status,
            "channels": channels,
            "error": error,
        }
        self._event_log.append(record)

    @property
    def event_log(self) -> list[dict]:
        return list(self._event_log)

    def _resolve_channel(self, channel_ref):
        """Resolve a channel name or object to a channel instance."""
        if isinstance(channel_ref, str):
            # Look up by name
            for ch in self._channels:
                if ch.name == channel_ref:
                    return ch
            return None
        # Already a channel object
        return channel_ref
