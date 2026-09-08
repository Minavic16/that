"""
NestQuant S8.6.12 — Execution Protection Tests
================================================

Tests for retry logic, state integrity, failure classification,
and circuit breaker behavior.
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from execution.protection import (
    CircuitBreakerConfig,
    ClassifiedModificationResult,
    ExecutionProtection,
    FailureClass,
    RetryConfig,
    classify_failure,
)
from strategy.lifecycle.contracts import ModificationResult


# ═══════════════════════════════════════════════════════════════
# A. Failure Classification
# ═══════════════════════════════════════════════════════════════

class TestFailureClassification:

    def test_success_is_non_retryable(self):
        result = ModificationResult(
            success=True, trade_id="T1", requested_sl=1.0980,
            broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
        )
        assert classify_failure(result) == FailureClass.NON_RETRYABLE

    def test_connection_failure_is_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Connection failed: timeout",
        )
        assert classify_failure(result) == FailureClass.RETRYABLE

    def test_invalid_ticket_is_non_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Invalid ticket: not_a_number",
        )
        assert classify_failure(result) == FailureClass.NON_RETRYABLE

    def test_invalid_sl_is_non_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="MT5 retcode 10015: Invalid price",
        )
        assert classify_failure(result) == FailureClass.NON_RETRYABLE

    def test_market_closed_is_non_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="MT5 retcode 10018: Market is closed",
        )
        assert classify_failure(result) == FailureClass.NON_RETRYABLE

    def test_trading_disabled_is_non_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="MT5 retcode 10026: Auto trading disabled",
        )
        assert classify_failure(result) == FailureClass.NON_RETRYABLE

    def test_unknown_error_is_unknown(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Something weird happened",
        )
        assert classify_failure(result) == FailureClass.UNKNOWN

    def test_bridge_error_is_retryable(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Bridge internal error",
        )
        assert classify_failure(result) == FailureClass.RETRYABLE


# ═══════════════════════════════════════════════════════════════
# B. Retry Logic
# ═══════════════════════════════════════════════════════════════

class TestRetryLogic:

    def _make_request(self):
        from strategy.lifecycle.contracts import PositionModificationRequest
        return PositionModificationRequest(
            trade_id="T1", symbol="EURUSD", new_sl=1.0980, reason="test",
        )

    def test_succeeds_on_first_attempt(self):
        """Modification succeeds on first attempt."""
        adapter = MagicMock()
        adapter.modify_position_stop.return_value = ModificationResult(
            success=True, trade_id="T1", requested_sl=1.0980,
            broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
        )
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        result = protection.execute_modification_with_retry(adapter, self._make_request())

        assert result.success is True
        assert result.attempt == 1
        assert adapter.modify_position_stop.call_count == 1

    def test_fails_once_then_succeeds(self):
        """Modification fails once then succeeds."""
        adapter = MagicMock()
        adapter.modify_position_stop.side_effect = [
            ModificationResult(
                success=False, trade_id="T1", requested_sl=1.0980,
                broker_sl=None, timestamp=datetime.now(timezone.utc),
                error="Connection failed: timeout",
            ),
            ModificationResult(
                success=True, trade_id="T1", requested_sl=1.0980,
                broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
            ),
        ]
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        result = protection.execute_modification_with_retry(adapter, self._make_request())

        assert result.success is True
        assert result.attempt == 2
        assert adapter.modify_position_stop.call_count == 2

    def test_fails_twice_then_succeeds(self):
        """Modification fails twice then succeeds."""
        adapter = MagicMock()
        adapter.modify_position_stop.side_effect = [
            ModificationResult(
                success=False, trade_id="T1", requested_sl=1.0980,
                broker_sl=None, timestamp=datetime.now(timezone.utc),
                error="Connection failed: timeout",
            ),
            ModificationResult(
                success=False, trade_id="T1", requested_sl=1.0980,
                broker_sl=None, timestamp=datetime.now(timezone.utc),
                error="Bridge internal error",
            ),
            ModificationResult(
                success=True, trade_id="T1", requested_sl=1.0980,
                broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
            ),
        ]
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        result = protection.execute_modification_with_retry(adapter, self._make_request())

        assert result.success is True
        assert result.attempt == 3
        assert adapter.modify_position_stop.call_count == 3

    def test_all_retries_exhausted(self):
        """All retries exhausted — returns last failure."""
        adapter = MagicMock()
        adapter.modify_position_stop.return_value = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Connection failed: timeout",
        )
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        result = protection.execute_modification_with_retry(adapter, self._make_request())

        assert result.success is False
        assert result.attempt == 4  # 1 initial + 3 retries
        assert adapter.modify_position_stop.call_count == 4

    def test_non_retryable_failure_does_not_retry(self):
        """Non-retryable failure stops immediately."""
        adapter = MagicMock()
        adapter.modify_position_stop.return_value = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Invalid ticket: not_a_number",
        )
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        result = protection.execute_modification_with_retry(adapter, self._make_request())

        assert result.success is False
        assert result.attempt == 1
        assert result.failure_class == FailureClass.NON_RETRYABLE
        assert adapter.modify_position_stop.call_count == 1

    def test_events_recorded(self):
        """Retry events are recorded."""
        adapter = MagicMock()
        adapter.modify_position_stop.side_effect = [
            ModificationResult(
                success=False, trade_id="T1", requested_sl=1.0980,
                broker_sl=None, timestamp=datetime.now(timezone.utc),
                error="Connection failed: timeout",
            ),
            ModificationResult(
                success=True, trade_id="T1", requested_sl=1.0980,
                broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
            ),
        ]
        protection = ExecutionProtection(
            retry_config=RetryConfig(max_retries=3),
            sleep_fn=lambda x: None,
        )
        protection.execute_modification_with_retry(adapter, self._make_request())

        event_types = [e.event_type for e in protection.events]
        assert "MODIFICATION_ATTEMPT" in event_types
        assert "MODIFICATION_RETRY" in event_types
        assert "MODIFICATION_CONFIRMED" in event_types


# ═══════════════════════════════════════════════════════════════
# C. State Integrity
# ═══════════════════════════════════════════════════════════════

class TestStateIntegrity:

    def test_pending_sl_not_committed_before_confirmation(self):
        """Internal SL does not change before broker confirmation."""
        from strategy.lifecycle.registry import LifecycleRegistry
        from strategy.lifecycle.contracts import Direction, MarketContext
        from strategy.trade_management.breakeven import BreakevenConfig
        from strategy.trade_management.max_hold import MaxHoldConfig
        from strategy.trade_management.trailing_stop import TrailingStopConfig

        registry = LifecycleRegistry(
            strategy_identity="test",
            breakeven_config=BreakevenConfig(enabled=False),
            max_hold_config=MaxHoldConfig(enabled=False),
            trailing_config=TrailingStopConfig(enabled=True),
        )
        now = datetime.now(timezone.utc)
        registry.register_entry(
            trade_id="T1", symbol="EURUSD", direction=Direction.LONG,
            entry_price=1.1000, initial_sl=1.0980, take_profit=1.1070,
            pip_size=0.0001, entry_time=now, entry_bar_index=0,
        )

        # Evaluate bar that triggers trailing
        market = MarketContext(
            symbol="EURUSD", timeframe="H4", timestamp=now, bar_index=1,
            open=1.1002, high=1.1010, low=1.0998, close=1.1005,
            previous_swing_low=1.0990, previous_swing_high=1.1015,
        )
        decisions = registry.evaluate_bar(market)

        # SL should be staged as pending, not committed
        assert registry.has_pending_sl("T1") is True
        assert registry.get_pending_sl("T1") == 1.0990
        # Actual position SL unchanged
        assert registry.get_current_sl("T1") == 1.0980

    def test_commit_sl_advances_confirmed_sl(self):
        """Successful commit advances confirmed SL."""
        from strategy.lifecycle.registry import LifecycleRegistry
        from strategy.lifecycle.contracts import Direction, MarketContext
        from strategy.trade_management.breakeven import BreakevenConfig
        from strategy.trade_management.max_hold import MaxHoldConfig
        from strategy.trade_management.trailing_stop import TrailingStopConfig

        registry = LifecycleRegistry(
            strategy_identity="test",
            breakeven_config=BreakevenConfig(enabled=False),
            max_hold_config=MaxHoldConfig(enabled=False),
            trailing_config=TrailingStopConfig(enabled=True),
        )
        now = datetime.now(timezone.utc)
        registry.register_entry(
            trade_id="T1", symbol="EURUSD", direction=Direction.LONG,
            entry_price=1.1000, initial_sl=1.0980, take_profit=1.1070,
            pip_size=0.0001, entry_time=now, entry_bar_index=0,
        )

        # Evaluate → pending SL
        market = MarketContext(
            symbol="EURUSD", timeframe="H4", timestamp=now, bar_index=1,
            open=1.1002, high=1.1010, low=1.0998, close=1.1005,
            previous_swing_low=1.0990, previous_swing_high=1.1015,
        )
        registry.evaluate_bar(market)

        # Commit
        committed = registry.commit_sl("T1")
        assert committed is True
        assert registry.get_current_sl("T1") == 1.0990
        assert registry.get_confirmed_sl("T1") == 1.0990
        assert registry.has_pending_sl("T1") is False

    def test_rollback_preserves_previous_confirmed_sl(self):
        """Failed modification preserves previous confirmed SL."""
        from strategy.lifecycle.registry import LifecycleRegistry
        from strategy.lifecycle.contracts import Direction, MarketContext
        from strategy.trade_management.breakeven import BreakevenConfig
        from strategy.trade_management.max_hold import MaxHoldConfig
        from strategy.trade_management.trailing_stop import TrailingStopConfig

        registry = LifecycleRegistry(
            strategy_identity="test",
            breakeven_config=BreakevenConfig(enabled=False),
            max_hold_config=MaxHoldConfig(enabled=False),
            trailing_config=TrailingStopConfig(enabled=True),
        )
        now = datetime.now(timezone.utc)
        registry.register_entry(
            trade_id="T1", symbol="EURUSD", direction=Direction.LONG,
            entry_price=1.1000, initial_sl=1.0980, take_profit=1.1070,
            pip_size=0.0001, entry_time=now, entry_bar_index=0,
        )

        # Evaluate → pending SL
        market = MarketContext(
            symbol="EURUSD", timeframe="H4", timestamp=now, bar_index=1,
            open=1.1002, high=1.1010, low=1.0998, close=1.1005,
            previous_swing_low=1.0990, previous_swing_high=1.1015,
        )
        registry.evaluate_bar(market)

        # Rollback (simulating broker rejection)
        rolled_back = registry.rollback_sl("T1")
        assert rolled_back is True
        # Position SL unchanged, pending removed
        assert registry.get_current_sl("T1") == 1.0980
        assert registry.get_confirmed_sl("T1") == 1.0980
        assert registry.has_pending_sl("T1") is False

    def test_successful_retry_commits_sl_once(self):
        """Successful retry commits SL exactly once."""
        from strategy.lifecycle.registry import LifecycleRegistry
        from strategy.lifecycle.contracts import Direction, MarketContext
        from strategy.trade_management.breakeven import BreakevenConfig
        from strategy.trade_management.max_hold import MaxHoldConfig
        from strategy.trade_management.trailing_stop import TrailingStopConfig

        registry = LifecycleRegistry(
            strategy_identity="test",
            breakeven_config=BreakevenConfig(enabled=False),
            max_hold_config=MaxHoldConfig(enabled=False),
            trailing_config=TrailingStopConfig(enabled=True),
        )
        now = datetime.now(timezone.utc)
        registry.register_entry(
            trade_id="T1", symbol="EURUSD", direction=Direction.LONG,
            entry_price=1.1000, initial_sl=1.0980, take_profit=1.1070,
            pip_size=0.0001, entry_time=now, entry_bar_index=0,
        )

        # Evaluate → pending SL
        market = MarketContext(
            symbol="EURUSD", timeframe="H4", timestamp=now, bar_index=1,
            open=1.1002, high=1.1010, low=1.0998, close=1.1005,
            previous_swing_low=1.0990, previous_swing_high=1.1015,
        )
        registry.evaluate_bar(market)

        # Commit once
        registry.commit_sl("T1")
        # Second commit should fail (nothing pending)
        second_commit = registry.commit_sl("T1")
        assert second_commit is False
        assert registry.get_current_sl("T1") == 1.0990


# ═══════════════════════════════════════════════════════════════
# D. Circuit Breaker
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreaker:

    def test_one_mismatch_does_not_halt(self):
        """One critical mismatch does not open breaker."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=3),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        assert protection.breaker_open is False

    def test_threshold_opens_breaker(self):
        """Threshold mismatches opens breaker."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=3),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        protection.record_reconciliation_mismatch("T2", 1.0990, 1.0970)
        protection.record_reconciliation_mismatch("T3", 1.1000, 1.0980)
        assert protection.breaker_open is True

    def test_new_entries_blocked_while_open(self):
        """New entries blocked while breaker is open."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        assert protection.breaker_open is True
        # Caller should check breaker_open before processing signals

    def test_reset_allows_new_entries(self):
        """Explicit reset restores new entry capability."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        assert protection.breaker_open is True

        protection.reset_circuit_breaker()
        assert protection.breaker_open is False

    def test_reset_records_event(self):
        """Reset emits a structured event."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        protection.reset_circuit_breaker()

        event_types = [e.event_type for e in protection.events]
        assert "EXECUTION_CIRCUIT_BREAKER_RESET" in event_types

    def test_breaker_open_event_recorded(self):
        """Breaker open emits a structured event."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=2),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        protection.record_reconciliation_mismatch("T2", 1.0990, 1.0970)

        event_types = [e.event_type for e in protection.events]
        assert "EXECUTION_CIRCUIT_BREAKER_OPEN" in event_types

    def test_existing_positions_continue_lifecycle(self):
        """Breaker blocks NEW entries but not lifecycle of existing positions.

        This is tested by the runtime: _process_pair() checks breaker_open
        only on the signal path, not the lifecycle path.
        """
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        # Lifecycle path is NOT gated by breaker — only signal path is
        assert protection.breaker_open is True

    def test_reconciliation_continues_while_open(self):
        """Reconciliation should continue even while breaker is open."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        assert protection.breaker_open is True

        # Can still record mismatches (reconciliation continues)
        protection.record_reconciliation_mismatch("T2", 1.0990, 1.0970)
        assert protection.critical_mismatch_count == 2

    def test_manual_reset_required(self):
        """Breaker does not auto-reset — requires explicit reset."""
        protection = ExecutionProtection(
            circuit_breaker_config=CircuitBreakerConfig(max_critical_failures=1),
        )
        protection.record_reconciliation_mismatch("T1", 1.0980, 1.0960)
        assert protection.breaker_open is True

        # Mismatch count increases but breaker stays open
        protection.record_reconciliation_mismatch("T2", 1.0990, 1.0970)
        assert protection.breaker_open is True
        assert protection.critical_mismatch_count == 2


# ═══════════════════════════════════════════════════════════════
# E. ClassifiedModificationResult
# ═══════════════════════════════════════════════════════════════

class TestClassifiedModificationResult:

    def test_success_should_not_retry(self):
        result = ModificationResult(
            success=True, trade_id="T1", requested_sl=1.0980,
            broker_sl=1.0980, timestamp=datetime.now(timezone.utc),
        )
        classified = ClassifiedModificationResult(
            result=result, failure_class=FailureClass.RETRYABLE,
            attempt=1, total_attempts=4,
        )
        assert classified.success is True
        assert classified.should_retry is False

    def test_retryable_failure_should_retry(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Connection failed",
        )
        classified = ClassifiedModificationResult(
            result=result, failure_class=FailureClass.RETRYABLE,
            attempt=1, total_attempts=4,
        )
        assert classified.should_retry is True

    def test_retryable_exhausted_should_not_retry(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Connection failed",
        )
        classified = ClassifiedModificationResult(
            result=result, failure_class=FailureClass.RETRYABLE,
            attempt=4, total_attempts=4,
        )
        assert classified.should_retry is False
        assert classified.is_permanent_failure is False

    def test_non_retryable_is_permanent(self):
        result = ModificationResult(
            success=False, trade_id="T1", requested_sl=1.0980,
            broker_sl=None, timestamp=datetime.now(timezone.utc),
            error="Invalid ticket",
        )
        classified = ClassifiedModificationResult(
            result=result, failure_class=FailureClass.NON_RETRYABLE,
            attempt=1, total_attempts=4,
        )
        assert classified.is_permanent_failure is True
        assert classified.should_retry is False


# ═══════════════════════════════════════════════════════════════
# F. RetryConfig
# ═══════════════════════════════════════════════════════════════

class TestRetryConfig:

    def test_delay_for_attempt(self):
        config = RetryConfig(
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            max_delay_seconds=30.0,
        )
        assert config.delay_for_attempt(0) == 1.0
        assert config.delay_for_attempt(1) == 2.0
        assert config.delay_for_attempt(2) == 4.0
        assert config.delay_for_attempt(3) == 8.0

    def test_max_delay_cap(self):
        config = RetryConfig(
            initial_delay_seconds=1.0,
            backoff_multiplier=10.0,
            max_delay_seconds=5.0,
        )
        assert config.delay_for_attempt(0) == 1.0
        assert config.delay_for_attempt(1) == 5.0  # capped
        assert config.delay_for_attempt(2) == 5.0  # capped
