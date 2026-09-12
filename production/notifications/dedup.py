"""
NQTS Notification Pipeline — Event Deduplication
=================================================

Prevents the same underlying failure from generating multiple
identical notifications.

Uses dedupe_key and cooldown windows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from nestquant.production.notifications.events import NQTSEvent


# ---------------------------------------------------------------------------
# Deduplication Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeduplicationResult:
    """Result of deduplication check."""
    is_duplicate: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Deduplication Store
# ---------------------------------------------------------------------------


class EventDeduplicator:
    """Tracks recently seen events and suppresses duplicates.

    Uses dedupe_key as the primary deduplication mechanism.
    Supports cooldown periods to suppress repeated events.
    """

    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        """
        Args:
            cooldown_seconds: Minimum time between duplicate notifications.
        """
        self._cooldown_seconds = cooldown_seconds
        self._seen: dict[str, float] = {}  # dedupe_key → last_seen_timestamp

    def check(self, event: NQTSEvent) -> DeduplicationResult:
        """Check if this event is a duplicate.

        Args:
            event: The event to check.

        Returns:
            DeduplicationResult with is_duplicate flag.
        """
        if event.dedupe_key is None:
            return DeduplicationResult(
                is_duplicate=False,
                reason="No dedupe_key — not a duplicate",
            )

        now = time.time()
        last_seen = self._seen.get(event.dedupe_key)

        if last_seen is not None:
            elapsed = now - last_seen
            if elapsed < self._cooldown_seconds:
                return DeduplicationResult(
                    is_duplicate=True,
                    reason=(
                        f"Duplicate within cooldown: "
                        f"{elapsed:.1f}s < {self._cooldown_seconds}s"
                    ),
                )

        # Record this event
        self._seen[event.dedupe_key] = now
        return DeduplicationResult(
            is_duplicate=False,
            reason="Not a duplicate or cooldown expired",
        )

    def clear(self) -> None:
        """Clear all tracked events."""
        self._seen.clear()

    def cleanup(self, max_age_seconds: float = 3600.0) -> int:
        """Remove entries older than max_age_seconds.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        to_remove = [
            key for key, ts in self._seen.items()
            if now - ts > max_age_seconds
        ]
        for key in to_remove:
            del self._seen[key]
        return len(to_remove)
