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

from nestquant.production.notifications.events import (
    NQTSEvent,
    EventType,
    Severity,
    build_event,
)
from nestquant.production.notifications.bus import EventBus, DeliveryStatus
from nestquant.production.notifications.policy import NotificationPolicy, NotificationDecision
from nestquant.production.notifications.channels import (
    NotificationChannel,
    FakeNotificationChannel,
    TelegramChannel,
    LogNotificationChannel,
)
from nestquant.production.notifications.dedup import EventDeduplicator, DeduplicationResult

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
