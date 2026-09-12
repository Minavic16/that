"""
NQTS Notification Pipeline — Notification Channels
====================================================

Generic notification channel interface and implementations.

Channel failure MUST NOT propagate to callers. All channel.send()
calls are wrapped in try/except by the EventBus.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from nestquant.production.notifications.events import NQTSEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base Channel
# ---------------------------------------------------------------------------


class NotificationChannel(ABC):
    """Abstract base class for notification channels.

    All channels must implement send().
    Channel failures must not raise exceptions (caught by EventBus).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name for logging and routing."""
        ...

    @abstractmethod
    def send(self, event: NQTSEvent) -> bool:
        """Send a notification for the given event.

        Args:
            event: The NQTS event to deliver.

        Returns:
            True if sent successfully, False otherwise.
        """
        ...


# ---------------------------------------------------------------------------
# Fake Channel (testing)
# ---------------------------------------------------------------------------


class FakeNotificationChannel(NotificationChannel):
    """Fake channel for testing. Records all sent events."""

    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self._sent: list[NQTSEvent] = []
        self._fail_next: bool = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def sent(self) -> list[NQTSEvent]:
        return list(self._sent)

    def send(self, event: NQTSEvent) -> bool:
        """Record the event. Returns False if fail_next is set."""
        if self._fail_next:
            self._fail_next = False
            return False
        self._sent.append(event)
        return True

    def set_fail_next(self) -> None:
        """Configure the next send() to fail."""
        self._fail_next = True

    def clear(self) -> None:
        """Clear sent history."""
        self._sent.clear()


# ---------------------------------------------------------------------------
# Telegram Channel (stub)
# ---------------------------------------------------------------------------


class TelegramChannel(NotificationChannel):
    """Telegram notification channel.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
    Does not import requests at module level — lazy import on first send.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, event: NQTSEvent) -> bool:
        """Send event to Telegram. Returns False on failure."""
        import os
        token = self._bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = self._chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            logger.warning("Telegram credentials not configured — notification suppressed")
            return False

        try:
            import urllib.request
            import urllib.parse
            import json

            text = self._format_message(event)
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200

        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def _format_message(self, event: NQTSEvent) -> str:
        """Format event as Telegram message."""
        severity_emoji = {
            "INFORMATION": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🔴",
            "EMERGENCY": "🚨",
        }
        emoji = severity_emoji.get(event.severity.value, "")
        parts = [
            f"{emoji} <b>{event.event_type.value}</b>",
            f"Severity: {event.severity.value}",
        ]
        if event.source:
            parts.append(f"Source: {event.source}")
        if event.symbol:
            parts.append(f"Symbol: {event.symbol}")
        if event.trade_id:
            parts.append(f"Trade: {event.trade_id}")
        if event.message:
            parts.append(f"\n{event.message}")
        return "\n".join(parts)

    def send_report(self, title: str, content: str, chat_id: Optional[str] = None) -> bool:
        """Send a longer report message to Telegram.

        Splits content into chunks if needed (Telegram 4096 char limit).
        """
        import os
        token = self._bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        cid = chat_id or self._chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not cid:
            logger.warning("Telegram credentials not configured — report suppressed")
            return False

        try:
            import urllib.request
            import urllib.parse

            full_text = f"<b>{title}</b>\n\n{content}"
            # Split into 4000-char chunks (leave margin for HTML)
            chunks = []
            while len(full_text) > 4000:
                split_at = full_text.rfind("\n", 0, 4000)
                if split_at == -1:
                    split_at = 4000
                chunks.append(full_text[:split_at])
                full_text = full_text[split_at:].lstrip("\n")
            chunks.append(full_text)

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            for chunk in chunks:
                data = urllib.parse.urlencode({
                    "chat_id": cid,
                    "text": chunk,
                    "parse_mode": "HTML",
                }).encode("utf-8")
                req = urllib.request.Request(url, data=data, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status != 200:
                        return False
            return True

        except Exception as e:
            logger.error(f"Telegram report send failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Log Channel (always available)
# ---------------------------------------------------------------------------


class LogNotificationChannel(NotificationChannel):
    """Channel that logs events via Python logging."""

    def __init__(self, name: str = "log") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def send(self, event: NQTSEvent) -> bool:
        """Log the event."""
        log_fn = {
            "INFORMATION": logger.info,
            "WARNING": logger.warning,
            "CRITICAL": logger.critical,
            "EMERGENCY": logger.critical,
        }.get(event.severity.value, logger.info)
        log_fn(f"NOTIFICATION: {event.event_type.value}: {event.message}")
        return True
