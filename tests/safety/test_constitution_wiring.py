"""
Tests for Constitution Risk Wiring — PART A remediation.
These tests verify that the constitution risk parameters are correctly
wired into the risk guard architecture.

Run: python3 -m pytest tests/test_constitution_wiring.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure nestquant is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_constitution_values():
    """Verify constitution risk parameters match specification."""
    from config.constitution import CONSTITUTION, ConstitutionRiskConfig

    assert CONSTITUTION.risk_per_trade_pct == 0.0015, "risk_per_trade_pct must be 0.15%"
    assert CONSTITUTION.max_concurrent_positions == 3, "max_concurrent_positions must be 3"
    assert CONSTITUTION.max_position_size_per_pair == 0.10, "max_position_size_per_pair must be 0.10"
    assert CONSTITUTION.max_total_exposure == 3.0, "max_total_exposure must be 3.0"
    assert CONSTITUTION.max_daily_loss_pct == 0.03, "max_daily_loss_pct must be 3%"
    assert CONSTITUTION.max_drawdown_pct == 0.08, "max_drawdown_pct must be 8%"
    assert CONSTITUTION.max_trades_per_day == 4, "max_trades_per_day must be 4"

    # Verify frozen
    try:
        CONSTITUTION.risk_per_trade_pct = 0.01
        assert False, "Constitution should be frozen"
    except AttributeError:
        pass


def test_risk_guard_config_derives_from_constitution():
    """Verify RiskGuardConfig defaults come from constitution."""
    from execution.risk_guard import RiskGuardConfig
    from config.constitution import CONSTITUTION

    config = RiskGuardConfig()

    assert config.risk_pct == CONSTITUTION.risk_per_trade_pct
    assert config.max_concurrent_positions == CONSTITUTION.max_concurrent_positions
    assert config.max_position_size_per_pair == CONSTITUTION.max_position_size_per_pair
    assert config.max_total_exposure == CONSTITUTION.max_total_exposure
    assert config.max_daily_loss_pct == CONSTITUTION.max_daily_loss_pct
    assert config.max_drawdown_pct == CONSTITUTION.max_drawdown_pct
    assert config.max_trades_per_day == CONSTITUTION.max_trades_per_day


def test_risk_guard_enforces_max_trades_per_day():
    """Verify max_trades_per_day is enforced."""
    from execution.risk_guard import RiskGuard, RiskGuardConfig
    from execution.contracts import TradeIntent, Direction
    from datetime import datetime, timezone

    config = RiskGuardConfig(
        account_balance=100000,
        max_trades_per_day=2,
    )
    guard = RiskGuard(config=config)

    # Create a valid intent
    intent = TradeIntent(
        pair="EUR/USD",
        direction=Direction.BUY,
        signal_strength=0.5,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1175,
        strategy="breakout",
        policy_version="test",
        timestamp=datetime.now(timezone.utc),
    )

    # First two trades should be evaluated (may pass or fail on other gates)
    guard._trade_count_today = 0
    d1 = guard.evaluate(intent)
    guard._trade_count_today = 1
    d2 = guard.evaluate(intent)

    # Third trade should be rejected by max_trades_per_day
    guard._trade_count_today = 2
    d3 = guard.evaluate(intent)
    assert not d3.approved, "Third trade should be rejected"
    assert "Max trades per day" in d3.reason, f"Rejection reason should mention trades/day: {d3.reason}"


def test_risk_guard_exposes_constitution_source():
    """Verify status() reports constitution as source."""
    from execution.risk_guard import RiskGuard

    guard = RiskGuard()
    status = guard.status()

    assert status["constitution_source"] == "config.constitution.CONSTITUTION"
    assert status["max_trades_per_day"] == 4
    assert status["risk_per_trade_pct"] == 0.0015
    assert status["max_drawdown_pct"] == 0.08
    assert status["max_total_exposure"] == 3.0


def test_prop_firm_guard_uses_constitution():
    """Verify PropFirmGuard derives from constitution."""
    from execution.prop_firm_guard import PropFirmGuard, PropFirmConfig
    from config.constitution import CONSTITUTION

    guard = PropFirmGuard()
    status = guard.status()

    assert status["prop_firm"]["constitution_source"] == "config.constitution.CONSTITUTION"
    assert status["prop_firm"]["max_trades_per_day"] == CONSTITUTION.max_trades_per_day


def test_constitution_is_authoritative_source():
    """Verify constitution is the only source of truth."""
    from config.constitution import CONSTITUTION
    from execution.risk_guard import RiskGuardConfig

    # All RiskGuardConfig defaults must match constitution
    rc = RiskGuardConfig()
    assert rc.risk_pct == CONSTITUTION.risk_per_trade_pct
    assert rc.max_concurrent_positions == CONSTITUTION.max_concurrent_positions
    assert rc.max_position_size_per_pair == CONSTITUTION.max_position_size_per_pair
    assert rc.max_total_exposure == CONSTITUTION.max_total_exposure
    assert rc.max_daily_loss_pct == CONSTITUTION.max_daily_loss_pct
    assert rc.max_drawdown_pct == CONSTITUTION.max_drawdown_pct
    assert rc.max_trades_per_day == CONSTITUTION.max_trades_per_day
