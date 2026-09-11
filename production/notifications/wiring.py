"""
NQTS Notification Pipeline — Event-to-Telegram Wiring
=====================================================

Connects NQTSEventBus → NotificationPolicy → TelegramChannel.

CRITICAL and EMERGENCY events are sent to Telegram immediately.
WARNING events are sent with lower priority.
INFORMATION events are log-only.

Usage:
    from notifications.wiring import create_notification_pipeline
    bus = create_notification_pipeline()
    bus.emit(build_event(...))
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from notifications.events import NQTSEvent, Severity, build_event, EventType
from notifications.bus import EventBus, DeliveryStatus
from notifications.policy import NotificationPolicy
from notifications.channels import TelegramChannel, LogNotificationChannel
from notifications.dedup import EventDeduplicator

logger = logging.getLogger("nqts.notifications")

# Default cooldowns per severity (seconds)
SEVERITY_COOLDOWNS = {
    Severity.INFORMATION: 300,
    Severity.WARNING: 60,
    Severity.CRITICAL: 10,
    Severity.EMERGENCY: 0,  # never deduplicated
}


def create_notification_pipeline(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    default_channels: Optional[list[str]] = None,
) -> EventBus:
    """Create and wire the full notification pipeline.

    Returns an EventBus that routes events through policy → channels.
    """
    channels = default_channels or ["telegram", "log"]

    # Build channels
    telegram = TelegramChannel(
        bot_token=bot_token or os.environ.get("TELEGRAM_BOT_TOKEN"),
        chat_id=chat_id or os.environ.get("TELEGRAM_CHAT_ID"),
    )
    log_ch = LogNotificationChannel()

    channel_list = [telegram, log_ch]

    # Build policy
    policy = NotificationPolicy(default_channels=channels)

    # Build bus (policy + list of channel instances)
    bus = EventBus(policy=policy, channels=channel_list)

    return bus


def emit_alert(
    bus: EventBus,
    event_type: EventType,
    severity: Severity,
    message: str,
    source: str = "s8_runtime",
    symbol: Optional[str] = None,
    trade_id: Optional[str] = None,
) -> DeliveryStatus:
    """Convenience: build event and emit through pipeline."""
    event = build_event(
        event_type=event_type,
        severity=severity,
        message=message,
        source=source,
        symbol=symbol,
        trade_id=trade_id,
    )
    return bus.emit(event)


def emit_critical(
    bus: EventBus,
    event_type: EventType,
    message: str,
    source: str = "s8_runtime",
    symbol: Optional[str] = None,
) -> DeliveryStatus:
    """Emit a CRITICAL alert → Telegram + log."""
    return emit_alert(
        bus, event_type, Severity.CRITICAL, message, source, symbol
    )


def emit_emergency(
    bus: EventBus,
    event_type: EventType,
    message: str,
    source: str = "s8_runtime",
) -> DeliveryStatus:
    """Emit an EMERGENCY alert → Telegram + log (never deduplicated)."""
    event = build_event(
        event_type=event_type,
        severity=Severity.EMERGENCY,
        message=message,
        source=source,
    )
    return bus.emit(event)


def emit_warning(
    bus: EventBus,
    event_type: EventType,
    message: str,
    source: str = "s8_runtime",
    symbol: Optional[str] = None,
) -> DeliveryStatus:
    """Emit a WARNING alert → Telegram + log."""
    return emit_alert(
        bus, event_type, Severity.WARNING, message, source, symbol
    )
