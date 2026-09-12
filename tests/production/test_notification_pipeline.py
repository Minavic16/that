"""
NQTS Notification Pipeline Tests
==================================

Tests for events, bus, policy, channels, deduplication,
and failure isolation.
"""

import os
from datetime import datetime, timezone


import pytest
from nestquant.production.notifications.events import NQTSEvent, EventType, Severity, build_event
from nestquant.production.notifications.bus import EventBus, DeliveryStatus
from nestquant.production.notifications.policy import NotificationPolicy, NotificationDecision
from nestquant.production.notifications.channels import (
    FakeNotificationChannel,
    LogNotificationChannel,
    NotificationChannel,
)
from nestquant.production.notifications.dedup import EventDeduplicator, DeduplicationResult


# ═══════════════════════════════════════════════════════════════
# A. Event Creation
# ═══════════════════════════════════════════════════════════════

class TestNQTSEvent:

    def test_valid_event_with_defaults(self):
        event = NQTSEvent()
        assert event.event_id is not None
        assert len(event.event_id) == 12
        assert event.timestamp is not None
        assert event.event_type == EventType.SYSTEM_STARTED
        assert event.severity == Severity.INFORMATION

    def test_event_with_all_fields(self):
        event = NQTSEvent(
            event_id="test123",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=EventType.ORDER_FILLED,
            severity=Severity.CRITICAL,
            source="s8_runtime",
            strategy_id="breakout-1.0",
            experiment_id="ZS-2026-001",
            symbol="EURUSD",
            trade_id="T123",
            message="Order filled at 1.1000",
            payload={"fill_price": 1.1000, "volume": 0.01},
            dedupe_key="order:T123",
        )
        assert event.event_id == "test123"
        assert event.event_type == EventType.ORDER_FILLED
        assert event.severity == Severity.CRITICAL
        assert event.symbol == "EURUSD"
        assert event.trade_id == "T123"
        assert event.payload["fill_price"] == 1.1000

    def test_event_to_dict(self):
        event = NQTSEvent(
            event_type=EventType.STOP_MODIFIED,
            severity=Severity.WARNING,
            symbol="EURUSD",
            trade_id="T1",
        )
        d = event.to_dict()
        assert d["event_type"] == "STOP_MODIFIED"
        assert d["severity"] == "WARNING"
        assert d["symbol"] == "EURUSD"
        assert d["trade_id"] == "T1"

    def test_event_id_unique(self):
        e1 = NQTSEvent()
        e2 = NQTSEvent()
        assert e1.event_id != e2.event_id

    def test_build_event_convenience(self):
        event = build_event(
            EventType.CIRCUIT_BREAKER_OPEN,
            Severity.CRITICAL,
            message="Breaker opened",
            source="protection",
            symbol="EURUSD",
        )
        assert event.event_type == EventType.CIRCUIT_BREAKER_OPEN
        assert event.severity == Severity.CRITICAL
        assert event.message == "Breaker opened"


# ═══════════════════════════════════════════════════════════════
# B. Notification Policy
# ═══════════════════════════════════════════════════════════════

class TestNotificationPolicy:

    def test_information_suppressed(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        event = NQTSEvent(severity=Severity.INFORMATION)
        decision = policy.evaluate(event)
        assert decision.notify is False

    def test_warning_notifies(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        event = NQTSEvent(severity=Severity.WARNING)
        decision = policy.evaluate(event)
        assert decision.notify is True
        assert "telegram" in decision.channels

    def test_critical_notifies(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        event = NQTSEvent(severity=Severity.CRITICAL)
        decision = policy.evaluate(event)
        assert decision.notify is True

    def test_emergency_notifies(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        event = NQTSEvent(severity=Severity.EMERGENCY)
        decision = policy.evaluate(event)
        assert decision.notify is True

    def test_suppressed_event_type(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        policy.suppress_event_type(EventType.HIGH_SPREAD)
        event = NQTSEvent(
            event_type=EventType.HIGH_SPREAD,
            severity=Severity.WARNING,
        )
        decision = policy.evaluate(event)
        assert decision.notify is False

    def test_always_notify_event_type(self):
        policy = NotificationPolicy(default_channels=["telegram"])
        policy.always_notify_event_type(EventType.CIRCUIT_BREAKER_OPEN)
        event = NQTSEvent(
            event_type=EventType.CIRCUIT_BREAKER_OPEN,
            severity=Severity.INFORMATION,
        )
        decision = policy.evaluate(event)
        assert decision.notify is True


# ═══════════════════════════════════════════════════════════════
# C. Channels
# ═══════════════════════════════════════════════════════════════

class TestChannels:

    def test_fake_channel_receives_event(self):
        channel = FakeNotificationChannel()
        event = NQTSEvent(event_type=EventType.ORDER_FILLED)
        result = channel.send(event)
        assert result is True
        assert len(channel.sent) == 1
        assert channel.sent[0].event_type == EventType.ORDER_FILLED

    def test_fake_channel_fail_next(self):
        channel = FakeNotificationChannel()
        channel.set_fail_next()
        event = NQTSEvent(event_type=EventType.ORDER_FILLED)
        result = channel.send(event)
        assert result is False
        assert len(channel.sent) == 0

    def test_channel_failure_does_not_crash(self):
        """Channel exceptions are handled safely by EventBus."""
        class BrokenChannel(NotificationChannel):
            @property
            def name(self):
                return "broken"
            def send(self, event):
                raise RuntimeError("Channel exploded")

        bus = EventBus(
            policy=NotificationPolicy(default_channels=["broken"]),
            channels=[BrokenChannel()],
        )
        event = NQTSEvent(severity=Severity.CRITICAL)
        # Should not raise
        bus.emit(event)


# ═══════════════════════════════════════════════════════════════
# D. EventBus
# ═══════════════════════════════════════════════════════════════

class TestEventBus:

    def test_emit_routes_to_channel(self):
        channel = FakeNotificationChannel()
        bus = EventBus(
            policy=NotificationPolicy(default_channels=["fake"]),
            channels=[channel],
        )
        event = NQTSEvent(severity=Severity.CRITICAL)
        bus.emit(event)
        assert len(channel.sent) == 1

    def test_emit_suppressed_event(self):
        channel = FakeNotificationChannel()
        bus = EventBus(
            policy=NotificationPolicy(default_channels=["fake"]),
            channels=[channel],
        )
        event = NQTSEvent(severity=Severity.INFORMATION)
        bus.emit(event)
        assert len(channel.sent) == 0

    def test_multiple_channels(self):
        ch1 = FakeNotificationChannel(name="ch1")
        ch2 = FakeNotificationChannel(name="ch2")
        bus = EventBus(
            policy=NotificationPolicy(default_channels=["ch1", "ch2"]),
            channels=[ch1, ch2],
        )
        event = NQTSEvent(severity=Severity.CRITICAL)
        bus.emit(event)
        assert len(ch1.sent) == 1
        assert len(ch2.sent) == 1

    def test_delivery_recorded(self):
        channel = FakeNotificationChannel()
        bus = EventBus(
            policy=NotificationPolicy(default_channels=["fake"]),
            channels=[channel],
        )
        event = NQTSEvent(severity=Severity.CRITICAL)
        bus.emit(event)
        assert len(bus.event_log) == 1
        assert bus.event_log[0]["status"] == DeliveryStatus.SENT

    def test_handler_receives_all_events(self):
        received = []
        bus = EventBus()
        bus.add_handler(lambda e: received.append(e))
        bus.emit(NQTSEvent(severity=Severity.INFORMATION))
        bus.emit(NQTSEvent(severity=Severity.CRITICAL))
        assert len(received) == 2


# ═══════════════════════════════════════════════════════════════
# E. Deduplication
# ═══════════════════════════════════════════════════════════════

class TestDeduplication:

    def test_first_event_not_duplicate(self):
        dedup = EventDeduplicator(cooldown_seconds=60)
        event = NQTSEvent(dedupe_key="order:123")
        result = dedup.check(event)
        assert result.is_duplicate is False

    def test_identical_event_is_duplicate(self):
        dedup = EventDeduplicator(cooldown_seconds=60)
        e1 = NQTSEvent(dedupe_key="order:123")
        e2 = NQTSEvent(dedupe_key="order:123")
        dedup.check(e1)
        result = dedup.check(e2)
        assert result.is_duplicate is True

    def test_distinct_keys_not_duplicate(self):
        dedup = EventDeduplicator(cooldown_seconds=60)
        e1 = NQTSEvent(dedupe_key="order:123")
        e2 = NQTSEvent(dedupe_key="order:456")
        dedup.check(e1)
        result = dedup.check(e2)
        assert result.is_duplicate is False

    def test_no_dedupe_key_not_duplicate(self):
        dedup = EventDeduplicator(cooldown_seconds=60)
        event = NQTSEvent(dedupe_key=None)
        result = dedup.check(event)
        assert result.is_duplicate is False

    def test_cleanup_removes_old_entries(self):
        dedup = EventDeduplicator(cooldown_seconds=60)
        dedup._seen = {"old_key": 0.0}  # epoch = very old
        removed = dedup.cleanup(max_age_seconds=10)
        assert removed == 1
        assert "old_key" not in dedup._seen


# ═══════════════════════════════════════════════════════════════
# F. Failure Isolation
# ═══════════════════════════════════════════════════════════════

class TestFailureIsolation:

    def test_channel_failure_does_not_propagate(self):
        """Notification failure must NEVER cause trading failure."""
        class ExplodingChannel(NotificationChannel):
            @property
            def name(self):
                return "explode"
            def send(self, event):
                raise ConnectionError("Telegram unavailable")

        bus = EventBus(
            policy=NotificationPolicy(default_channels=["explode"]),
            channels=[ExplodingChannel()],
        )
        # This must not raise — simulating trade execution path
        bus.emit(NQTSEvent(severity=Severity.CRITICAL))
        # If we reach here, failure isolation worked

    def test_multiple_channel_failures_safe(self):
        """Multiple channel failures are all handled safely."""
        class FailChannel(NotificationChannel):
            def __init__(self, n):
                self._n = n
            @property
            def name(self):
                return f"fail{self._n}"
            def send(self, event):
                raise RuntimeError(f"Channel {self._n} failed")

        bus = EventBus(
            policy=NotificationPolicy(default_channels=["fail1", "fail2", "fail3"]),
            channels=[FailChannel(1), FailChannel(2), FailChannel(3)],
        )
        # Must not raise
        bus.emit(NQTSEvent(severity=Severity.EMERGENCY))
        # All failures recorded
        assert len(bus.event_log) == 3
        assert all(r["status"] == DeliveryStatus.FAILED for r in bus.event_log)


# ═══════════════════════════════════════════════════════════════
# G. Integration Events
# ═══════════════════════════════════════════════════════════════

class TestIntegrationEvents:

    def test_protection_failure_generates_event(self):
        """Verify protection failures can generate NQTS events."""
        event = build_event(
            EventType.PROTECTION_MODIFICATION_FAILED,
            Severity.CRITICAL,
            message="SL modification failed after 3 attempts",
            source="protection",
            trade_id="T1",
            symbol="EURUSD",
        )
        assert event.event_type == EventType.PROTECTION_MODIFICATION_FAILED
        assert event.severity == Severity.CRITICAL

    def test_reconciliation_failure_generates_event(self):
        event = build_event(
            EventType.RECONCILIATION_CRITICAL,
            Severity.CRITICAL,
            message="SL mismatch: internal=1.098, broker=1.096",
            source="reconciliation",
            trade_id="T1",
        )
        assert event.event_type == EventType.RECONCILIATION_CRITICAL

    def test_circuit_breaker_generates_event(self):
        event = build_event(
            EventType.CIRCUIT_BREAKER_OPEN,
            Severity.CRITICAL,
            message="3 critical mismatches",
            source="protection",
        )
        assert event.event_type == EventType.CIRCUIT_BREAKER_OPEN

    def test_execution_failure_generates_event(self):
        event = build_event(
            EventType.ORDER_FAILED,
            Severity.CRITICAL,
            message="Broker rejected: insufficient margin",
            source="mt5_adapter",
            symbol="EURUSD",
        )
        assert event.event_type == EventType.ORDER_FAILED

    def test_full_pipeline_end_to_end(self):
        """Full pipeline: event → policy → dedup → channel."""
        channel = FakeNotificationChannel()
        dedup = EventDeduplicator(cooldown_seconds=60)
        policy = NotificationPolicy(default_channels=["fake"])
        bus = EventBus(policy=policy, channels=[channel])

        # Wrap bus.emit with dedup
        original_emit = bus.emit
        def emit_with_dedup(event):
            result = dedup.check(event)
            if result.is_duplicate:
                return
            original_emit(event)
        bus.emit = emit_with_dedup

        event = build_event(
            EventType.CIRCUIT_BREAKER_OPEN,
            Severity.CRITICAL,
            message="Breaker opened",
            dedupe_key="breaker:open",
        )
        bus.emit(event)
        assert len(channel.sent) == 1

        # Same event again — should be suppressed
        event2 = build_event(
            EventType.CIRCUIT_BREAKER_OPEN,
            Severity.CRITICAL,
            message="Breaker opened again",
            dedupe_key="breaker:open",
        )
        bus.emit(event2)
        assert len(channel.sent) == 1  # still 1
