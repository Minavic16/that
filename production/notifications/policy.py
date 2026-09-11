"""
NQTS Notification Pipeline — Notification Policy
=================================================

Decides whether an event should produce a notification
and through which channels.

Channel-agnostic: does not know about Telegram, email, etc.
Only knows about severity levels and routing rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from notifications.events import NQTSEvent, Severity


# ---------------------------------------------------------------------------
# Policy Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotificationDecision:
    """Result of policy evaluation."""
    notify: bool
    channels: list  # list of channel names or references
    reason: str = ""


# ---------------------------------------------------------------------------
# Notification Policy
# ---------------------------------------------------------------------------


class NotificationPolicy:
    """Decides whether and where to notify for a given event.

    Default policy:
      INFORMATION → log only (no external notification)
      WARNING     → log + optional external
      CRITICAL    → log + immediate external
      EMERGENCY   → log + immediate external (multiple channels)

    This is channel-agnostic. Channel routing is configured externally.
    """

    def __init__(self, default_channels: Optional[list] = None):
        """
        Args:
            default_channels: List of channel names to use for notifications
                             that require external notification.
        """
        self._default_channels = list(default_channels or [])
        self._suppressed_types: set = set()
        self._always_notify_types: set = set()

    def evaluate(self, event: NQTSEvent) -> NotificationDecision:
        """Evaluate whether this event should produce a notification.

        Args:
            event: The NQTS event to evaluate.

        Returns:
            NotificationDecision with notify flag and target channels.
        """
        # Check if event type is explicitly suppressed
        if event.event_type in self._suppressed_types:
            return NotificationDecision(
                notify=False,
                channels=[],
                reason=f"Event type {event.event_type.value} explicitly suppressed",
            )

        # Check if event type always notifies
        if event.event_type in self._always_notify_types:
            return NotificationDecision(
                notify=True,
                channels=list(self._default_channels),
                reason=f"Event type {event.event_type.value} always notifies",
            )

        # Route by severity
        if event.severity == Severity.INFORMATION:
            return NotificationDecision(
                notify=False,
                channels=[],
                reason="INFORMATION severity: log only",
            )

        if event.severity == Severity.WARNING:
            return NotificationDecision(
                notify=True,
                channels=list(self._default_channels),
                reason="WARNING severity: log + optional external",
            )

        if event.severity == Severity.CRITICAL:
            return NotificationDecision(
                notify=True,
                channels=list(self._default_channels),
                reason="CRITICAL severity: immediate external",
            )

        if event.severity == Severity.EMERGENCY:
            return NotificationDecision(
                notify=True,
                channels=list(self._default_channels),
                reason="EMERGENCY severity: immediate external",
            )

        # Default: no notification
        return NotificationDecision(
            notify=False,
            channels=[],
            reason="Unknown severity: no notification",
        )

    def suppress_event_type(self, event_type) -> None:
        """Explicitly suppress notifications for an event type."""
        self._suppressed_types.add(event_type)

    def always_notify_event_type(self, event_type) -> None:
        """Always notify for an event type regardless of severity."""
        self._always_notify_types.add(event_type)
