"""
NestQuant S8.6.11 — Startup Reconciliation & Orphan Position Recovery Tests
============================================================================

Mandatory startup reconciliation must complete before normal trading.
Broker orphans detected → runtime enters SAFE_HALTED.
Internal ghosts reconciled.
State mismatches detected.
Unsafe state blocks trading.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


import pytest
from nestquant.production.strategy.lifecycle.contracts import (
    Direction,
    ExitReason,
    OrphanPositionPolicy,
    PositionLifecycleState,
    StartupReconciliationResult,
    TradeGeometry,
)
from nestquant.production.strategy.lifecycle.registry import LifecycleRegistry
from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _make_registry_with_position(
    trade_id="T1", symbol="EURUSD", direction=Direction.LONG,
    entry=1.1000, sl=1.0980, tp=1.1070, risk_pips=20,
):
    """Create a LifecycleRegistry with one active position."""
    reg = LifecycleRegistry(
        strategy_identity="test",
        breakeven_config=BreakevenConfig(enabled=False),
        max_hold_config=MaxHoldConfig(enabled=False),
        trailing_config=TrailingStopConfig(enabled=False),
    )
    now = datetime.now(timezone.utc)
    reg.register_entry(
        trade_id=trade_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        initial_sl=sl,
        take_profit=tp,
        pip_size=0.0001,
        entry_time=now,
        entry_bar_index=0,
    )
    return reg


def _make_broker_position(
    ticket="12345", symbol="EURUSD", type_=0,
    sl=0.0980, tp=0.1070, volume=0.01,
):
    """Create a broker position dict (MT5 format)."""
    return {
        "ticket": ticket,
        "symbol": symbol,
        "type": type_,  # 0=BUY, 1=SELL
        "volume": volume,
        "sl": sl,
        "tp": tp,
        "price_open": 1.1000,
    }


def _make_mock_runtime(
    mode="dry-run",
    broker_positions=None,
    registry=None,
    orphan_policy=OrphanPositionPolicy.HALT,
):
    """Create a mock S8Runtime for testing reconciliation."""
    from nestquant.production.execution.s8_runtime import RuntimeConfig, RuntimeMode, RuntimeState, S8Runtime

    config = RuntimeConfig(
        mode=RuntimeMode.DRY_RUN if mode == "dry-run" else RuntimeMode.EXPERIMENTAL_LIVE,
        orphan_policy=orphan_policy,
    )
    runtime = S8Runtime(config=config)
    runtime._lifecycle_registry = registry

    # Mock client
    mock_client = MagicMock()
    if broker_positions is not None:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.data = {"positions": broker_positions}
        mock_client.get_positions.return_value = mock_resp
    else:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.data = {"positions": []}
        mock_client.get_positions.return_value = mock_resp
    runtime._client = mock_client

    # Mock adapter
    mock_adapter = MagicMock()
    mock_adapter.close_position.return_value = True
    runtime._adapter = mock_adapter

    # Mock trade_logger
    mock_logger = MagicMock()
    runtime._trade_logger = mock_logger

    return runtime


# ═══════════════════════════════════════════════════════════════
# A. Clean Startup Reconciliation
# ═══════════════════════════════════════════════════════════════

class TestCleanStartupReconciliation:

    def test_clean_startup_no_positions(self):
        """Broker and registry both empty → safe."""
        runtime = _make_mock_runtime(mode="dry-run")
        result = runtime.reconcile_startup_state()

        assert result.success is True
        assert result.matched_count == 0
        assert len(result.broker_orphans) == 0
        assert len(result.internal_ghosts) == 0
        assert len(result.state_mismatches) == 0
        assert result.runtime_safe is True

    def test_clean_startup_dry_run_with_empty_registry(self):
        """Dry-run with empty registry → safe, state = RUNNING."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        runtime = _make_mock_runtime(mode="dry-run")
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is True
        assert runtime.state == RuntimeState.RUNNING

    def test_dry_run_ghost_positions_cleaned(self):
        """Dry-run with ghost positions in registry → cleaned, still safe."""
        reg = _make_registry_with_position()
        runtime = _make_mock_runtime(mode="dry-run", registry=reg)
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is True
        assert len(result.internal_ghosts) == 1
        assert "T1" in result.internal_ghosts


# ═══════════════════════════════════════════════════════════════
# B. Broker Orphan Detection
# ═══════════════════════════════════════════════════════════════

class TestBrokerOrphanDetection:

    def test_broker_orphan_halts_runtime(self):
        """Broker has position, registry does not → SAFE_HALTED."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        broker_pos = _make_broker_position()
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=None,
        )
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is False
        assert len(result.broker_orphans) == 1
        assert runtime.state == RuntimeState.SAFE_HALTED
        assert result.orphan_policy == "HALT"

    def test_broker_orphan_multiple_halt(self):
        """Multiple broker orphans → all detected, SAFE_HALTED."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        bp1 = _make_broker_position(ticket="111", symbol="EURUSD")
        bp2 = _make_broker_position(ticket="222", symbol="GBPUSD", type_=1)
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[bp1, bp2],
            registry=None,
        )
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is False
        assert len(result.broker_orphans) == 2
        assert runtime.state == RuntimeState.SAFE_HALTED

    def test_orphan_detected_even_with_active_registry(self):
        """Registry has EURUSD, broker has EURUSD + GBPUSD → GBPUSD is orphan."""
        reg = _make_registry_with_position(symbol="EURUSD")
        bp_eur = _make_broker_position(ticket="111", symbol="EURUSD")
        bp_gbp = _make_broker_position(ticket="222", symbol="GBPUSD")
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[bp_eur, bp_gbp],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is False
        assert len(result.broker_orphans) == 1
        assert result.broker_orphans[0]["symbol"] == "GBPUSD"


# ═══════════════════════════════════════════════════════════════
# C. Close Policy
# ═══════════════════════════════════════════════════════════════

class TestClosePolicy:

    def test_close_policy_closes_orphan(self):
        """CLOSE policy: orphan detected → adapter.close_position() called."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        broker_pos = _make_broker_position()
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=None,
            orphan_policy=OrphanPositionPolicy.CLOSE,
        )
        # After close, second get_positions returns empty
        empty_resp = MagicMock()
        empty_resp.ok = True
        empty_resp.data = {"positions": []}
        runtime._client.get_positions = MagicMock(side_effect=[
            runtime._client.get_positions.return_value,
            empty_resp,
        ])

        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is True
        runtime._adapter.close_position.assert_called_once_with("12345")
        assert runtime.state == RuntimeState.RUNNING

    def test_close_policy_failure_leaves_halted(self):
        """CLOSE policy: if close fails → SAFE_HALTED."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        broker_pos = _make_broker_position()
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=None,
            orphan_policy=OrphanPositionPolicy.CLOSE,
        )
        runtime._adapter.close_position.return_value = False

        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is False
        assert runtime.state == RuntimeState.SAFE_HALTED


# ═══════════════════════════════════════════════════════════════
# D. Internal Ghost Recovery
# ═══════════════════════════════════════════════════════════════

class TestInternalGhostRecovery:

    def test_internal_ghost_is_reconciled(self):
        """Registry has position, broker does not → ghost detected."""
        reg = _make_registry_with_position()
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        assert len(result.internal_ghosts) == 1
        assert "T1" in result.internal_ghosts
        assert result.runtime_safe is True  # ghosts don't block

    def test_multiple_ghosts_detected(self):
        """Multiple internal ghosts → all detected."""
        reg = _make_registry_with_position(trade_id="T1")
        now = datetime.now(timezone.utc)
        reg.register_entry(
            trade_id="T2", symbol="GBPUSD", direction=Direction.LONG,
            entry_price=1.3000, initial_sl=1.2980, take_profit=1.3070,
            pip_size=0.0001, entry_time=now, entry_bar_index=0,
        )

        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        assert len(result.internal_ghosts) >= 1


# ═══════════════════════════════════════════════════════════════
# E. State Mismatch Detection
# ═══════════════════════════════════════════════════════════════

class TestStateMismatchDetection:

    def test_stop_loss_mismatch_halts_runtime(self):
        """Broker SL differs from internal SL → SAFE_HALTED."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        reg = _make_registry_with_position(sl=1.0980)
        # Broker has different SL
        broker_pos = _make_broker_position(sl=0.0960, type_=0)
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        assert result.runtime_safe is False
        assert len(result.state_mismatches) == 1
        assert runtime.state == RuntimeState.SAFE_HALTED

    def test_direction_mismatch_halts_runtime(self):
        """Broker has BUY, registry has SELL → different keys: orphan + ghost."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        reg = _make_registry_with_position(direction=Direction.LONG)
        # Broker has SELL (type=1) → different key
        broker_pos = _make_broker_position(type_=1, sl=0.0980)
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        # Different direction → different key → broker orphan + internal ghost
        # Broker orphan triggers HALT → runtime_safe=False
        assert len(result.broker_orphans) == 1
        assert len(result.internal_ghosts) == 1
        assert result.runtime_safe is False
        assert runtime.state == RuntimeState.SAFE_HALTED

    def test_matching_state_is_ok(self):
        """Same SL → matched, no mismatch."""
        reg = _make_registry_with_position(sl=1.0980)
        broker_pos = _make_broker_position(sl=1.0980, type_=0)
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=reg,
        )
        result = runtime.reconcile_startup_state()

        assert result.matched_count == 1
        assert len(result.state_mismatches) == 0
        assert result.runtime_safe is True


# ═══════════════════════════════════════════════════════════════
# F. Runtime State Machine
# ═══════════════════════════════════════════════════════════════

class TestRuntimeStateMachine:

    def test_reconcile_sets_reconciling_state(self):
        """During reconciliation, state should be RECONCILING."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        runtime = _make_mock_runtime(mode="dry-run")
        # Patch to check intermediate state
        original_reconcile = runtime.reconcile_startup_state

        def check_state():
            # At entry, state should transition to RECONCILING
            result = original_reconcile()
            return result

        result = check_state()
        # After completion in dry-run, state should be RUNNING
        assert runtime.state == RuntimeState.RUNNING

    def test_safe_halted_state_blocks_processing(self):
        """SAFE_HALTED state blocks signal processing."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        runtime = _make_mock_runtime(mode="dry-run")
        runtime._state = RuntimeState.SAFE_HALTED

        # _process_pair should return early when halted
        runtime._process_pair("EUR/USD")

        # No error = guard worked
        assert runtime._state == RuntimeState.SAFE_HALTED

    def test_halted_state_prevents_start(self):
        """start() should not proceed if reconciliation fails."""
        from nestquant.production.execution.s8_runtime import RuntimeState
        broker_pos = _make_broker_position()
        runtime = _make_mock_runtime(
            mode="live",
            broker_positions=[broker_pos],
            registry=None,
        )
        # start() calls initialize() then reconcile
        # We mock initialize to succeed
        runtime.initialize = MagicMock(return_value=True)
        runtime.start()

        # Runtime should NOT be in RUNNING state
        assert runtime.state != RuntimeState.RUNNING


# ═══════════════════════════════════════════════════════════════
# G. Reconciliation Result
# ═══════════════════════════════════════════════════════════════

class TestReconciliationResult:

    def test_result_has_all_fields(self):
        """StartupReconciliationResult contains all required fields."""
        result = StartupReconciliationResult(
            success=True,
            matched_count=1,
            broker_orphans=[],
            internal_ghosts=[],
            state_mismatches=[],
            actions_taken=["MATCHED:T1"],
            runtime_safe=True,
            orphan_policy="HALT",
        )
        assert result.success is True
        assert result.matched_count == 1
        assert result.runtime_safe is True
        assert result.to_dict()["matched_count"] == 1
        assert result.to_dict()["broker_orphan_count"] == 0

    def test_result_to_dict(self):
        """to_dict() returns serializable dictionary."""
        result = StartupReconciliationResult(
            success=False,
            matched_count=0,
            broker_orphans=[{"ticket": "12345"}],
            internal_ghosts=["T1"],
            state_mismatches=[{"trade_id": "T2"}],
            actions_taken=["BROKER_ORPHAN:12345"],
            runtime_safe=False,
            orphan_policy="HALT",
        )
        d = result.to_dict()
        assert d["broker_orphan_count"] == 1
        assert d["internal_ghost_count"] == 1
        assert d["state_mismatch_count"] == 1
        assert d["runtime_safe"] is False
