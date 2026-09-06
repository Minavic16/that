"""
NQTS Notification Pipeline
===========================

Architecture:
  NQTS components → emit NQTSEvent → EventBus → NotificationPolicy → Channels

Components:
  - events: NQTSEvent, EventType, Severity, build_event
  - bus: EventBus (central dispatcher)
  - policy: NotificationPolicy (decide notify/channel)
  - channels: NotificationChannel, FakeNotificationChannel, TelegramChannel
  - dedup: EventDeduplicator
"""

from notifications.events import (
    NQTSEvent,
    EventType,
    Severity,
    build_event,
)
from notifications.bus import EventBus, DeliveryStatus
from notifications.policy import NotificationPolicy, NotificationDecision
from notifications.channels import (
    NotificationChannel,
    FakeNotificationChannel,
    TelegramChannel,
    LogNotificationChannel,
)
from notifications.dedup import EventDeduplicator, DeduplicationResult

__all__ = [
    "NQTSEvent",
    "EventType",
    "Severity",
    "build_event",
    "EventBus",
    "DeliveryStatus",
    "NotificationPolicy",
    "NotificationDecision",
    "NotificationChannel",
    "FakeNotificationChannel",
    "TelegramChannel",
    "LogNotificationChannel",
    "EventDeduplicator",
    "DeduplicationResult",
]
