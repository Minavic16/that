"""
Tests for nestquant.config.policies module.
"""

import json
import os
import tempfile

import pytest

from nestquant.core.configuration.policies import (
    ExecutionParams,
    HardLimits,
    LiveParameterPolicy,
    PolicyValidationError,
    RiskParams,
    StrategyParams,
    assert_valid,
    dict_to_policy,
    json_to_policy,
    load_policy,
    policy_to_dict,
    policy_to_json,
    save_policy,
    validate_execution,
    validate_hard_limits,
    validate_policy,
    validate_risk,
    validate_strategy,
)


class TestStrategyParams:
    def test_default_values(self):
        s = StrategyParams()
        assert s.z_entry_threshold == 2.2
        assert s.z_exit_threshold == 0.5
        assert s.lookback == 20
        assert s.atr_period == 14
        assert s.atr_sl_multiplier == 3.0
        assert s.rrr == 2.0
        assert s.min_divergence == 10.0
        assert s.breakeven_ratio == 1.5
        assert s.enable_macro_filter is True

    def test_custom_values(self):
        s = StrategyParams(z_entry_threshold=3.0, lookback=50)
        assert s.z_entry_threshold == 3.0
        assert s.lookback == 50

    def test_frozen(self):
        s = StrategyParams()
        with pytest.raises(AttributeError):
            s.z_entry_threshold = 99

    def test_validation_positive_thresholds(self):
        s = StrategyParams(z_entry_threshold=-1.0)
        errors = validate_strategy(s)
        assert any("z_entry_threshold" in e for e in errors)

    def test_validation_zero_lookback(self):
        s = StrategyParams(lookback=0)
        errors = validate_strategy(s)
        assert any("lookback" in e for e in errors)

    def test_valid_strategy(self):
        s = StrategyParams()
        errors = validate_strategy(s)
        assert errors == []


class TestExecutionParams:
    def test_default_values(self):
        e = ExecutionParams()
        assert e.max_lot == 0.20
        assert e.min_lot == 0.01
        assert e.max_open_trades == 1
        assert e.commission_per_lot == 6.0

    def test_frozen(self):
        e = ExecutionParams()
        with pytest.raises(AttributeError):
            e.max_lot = 99

    def test_validation_max_lot_zero(self):
        e = ExecutionParams(max_lot=0)
        errors = validate_execution(e)
        assert any("max_lot" in e for e in errors)

    def test_validation_max_lot_negative(self):
        e = ExecutionParams(max_lot=-0.1)
        errors = validate_execution(e)
        assert any("max_lot" in e for e in errors)

    def test_validation_min_lot_gt_max_lot(self):
        e = ExecutionParams(min_lot=1.0, max_lot=0.5)
        errors = validate_execution(e)
        assert any("min_lot" in e and "max_lot" in e for e in errors)

    def test_validation_max_open_trades_zero(self):
        e = ExecutionParams(max_open_trades=0)
        errors = validate_execution(e)
        assert any("max_open_trades" in e for e in errors)

    def test_valid_execution(self):
        e = ExecutionParams()
        errors = validate_execution(e)
        assert errors == []


class TestRiskParams:
    def test_default_values(self):
        r = RiskParams()
        assert r.risk_per_trade == 0.02
        assert r.initial_balance == 200.0
        assert r.max_dd_pct == 55.0

    def test_frozen(self):
        r = RiskParams()
        with pytest.raises(AttributeError):
            r.risk_per_trade = 99

    def test_validation_risk_per_trade_zero(self):
        r = RiskParams(risk_per_trade=0)
        errors = validate_risk(r)
        assert any("risk_per_trade" in e for e in errors)

    def test_validation_risk_per_trade_gt_one(self):
        r = RiskParams(risk_per_trade=1.5)
        errors = validate_risk(r)
        assert any("risk_per_trade" in e for e in errors)

    def test_validation_initial_balance_zero(self):
        r = RiskParams(initial_balance=0)
        errors = validate_risk(r)
        assert any("initial_balance" in e for e in errors)

    def test_valid_risk(self):
        r = RiskParams()
        errors = validate_risk(r)
        assert errors == []


class TestHardLimits:
    def test_default_values(self):
        h = HardLimits()
        assert h.hard_dd_pct == 8.0
        assert h.soft_dd_pct == 6.0
        assert h.max_consecutive_losses == 5
        assert h.daily_loss_limit_pct == 0.03

    def test_frozen(self):
        h = HardLimits()
        with pytest.raises(AttributeError):
            h.hard_dd_pct = 99

    def test_validation_hard_dd_lte_soft_dd(self):
        h = HardLimits(hard_dd_pct=5.0, soft_dd_pct=6.0)
        errors = validate_hard_limits(h)
        assert any("hard_dd_pct" in e and "soft_dd_pct" in e for e in errors)

    def test_validation_hard_dd_eq_soft_dd(self):
        h = HardLimits(hard_dd_pct=6.0, soft_dd_pct=6.0)
        errors = validate_hard_limits(h)
        assert any("hard_dd_pct" in e and "soft_dd_pct" in e for e in errors)

    def test_validation_max_consecutive_losses_zero(self):
        h = HardLimits(max_consecutive_losses=0)
        errors = validate_hard_limits(h)
        assert any("max_consecutive_losses" in e for e in errors)

    def test_validation_max_consecutive_losses_negative(self):
        h = HardLimits(max_consecutive_losses=-1)
        errors = validate_hard_limits(h)
        assert any("max_consecutive_losses" in e for e in errors)

    def test_validation_daily_loss_limit_out_of_range(self):
        h = HardLimits(daily_loss_limit_pct=1.5)
        errors = validate_hard_limits(h)
        assert any("daily_loss_limit_pct" in e for e in errors)

    def test_valid_hard_limits(self):
        h = HardLimits()
        errors = validate_hard_limits(h)
        assert errors == []


class TestLiveParameterPolicy:
    def test_default_creation(self):
        p = LiveParameterPolicy()
        assert p.policy_version == "1.0.0"
        assert p.research_run_id == ""
        assert isinstance(p.strategy, StrategyParams)
        assert isinstance(p.execution, ExecutionParams)
        assert isinstance(p.risk, RiskParams)
        assert isinstance(p.hard_limits, HardLimits)

    def test_frozen(self):
        p = LiveParameterPolicy()
        with pytest.raises(AttributeError):
            p.policy_version = "2.0.0"

    def test_custom_creation(self):
        p = LiveParameterPolicy(
            policy_version="1.2.3",
            research_run_id="ZS-2026-001",
            strategy=StrategyParams(z_entry_threshold=3.0),
        )
        assert p.policy_version == "1.2.3"
        assert p.research_run_id == "ZS-2026-001"
        assert p.strategy.z_entry_threshold == 3.0


class TestValidation:
    def test_valid_policy(self):
        p = LiveParameterPolicy(research_run_id="test-run-001")
        errors = validate_policy(p)
        assert errors == []

    def test_invalid_version(self):
        p = LiveParameterPolicy(
            policy_version="not-a-version",
            research_run_id="test-run-001",
        )
        errors = validate_policy(p)
        assert any("policy_version" in e for e in errors)

    def test_empty_research_run_id(self):
        p = LiveParameterPolicy(research_run_id="")
        errors = validate_policy(p)
        assert any("research_run_id" in e for e in errors)

    def test_whitespace_research_run_id(self):
        p = LiveParameterPolicy(research_run_id="   ")
        errors = validate_policy(p)
        assert any("research_run_id" in e for e in errors)

    def test_assert_valid_raises(self):
        p = LiveParameterPolicy(
            policy_version="bad",
            research_run_id="",
        )
        with pytest.raises(PolicyValidationError) as exc_info:
            assert_valid(p)
        assert len(exc_info.value.errors) >= 2

    def test_assert_valid_passes(self):
        p = LiveParameterPolicy(research_run_id="test-run")
        assert_valid(p)  # should not raise


class TestSerialization:
    def test_policy_to_dict_roundtrip(self):
        p = LiveParameterPolicy(
            policy_version="1.2.3",
            research_run_id="ZS-2026-001",
            strategy=StrategyParams(z_entry_threshold=3.0),
            execution=ExecutionParams(max_lot=0.5),
            risk=RiskParams(risk_per_trade=0.01),
            hard_limits=HardLimits(hard_dd_pct=10.0),
        )
        d = policy_to_dict(p)
        p2 = dict_to_policy(d)
        assert p.policy_version == p2.policy_version
        assert p.research_run_id == p2.research_run_id
        assert p.strategy.z_entry_threshold == p2.strategy.z_entry_threshold
        assert p.execution.max_lot == p2.execution.max_lot
        assert p.risk.risk_per_trade == p2.risk.risk_per_trade
        assert p.hard_limits.hard_dd_pct == p2.hard_limits.hard_dd_pct

    def test_policy_to_json_roundtrip(self):
        p = LiveParameterPolicy(
            policy_version="2.0.0",
            research_run_id="ZS-2026-002",
        )
        raw = policy_to_json(p)
        p2 = json_to_policy(raw)
        assert p.policy_version == p2.policy_version
        assert p.research_run_id == p2.research_run_id

    def test_json_is_valid_json(self):
        p = LiveParameterPolicy(research_run_id="test")
        raw = policy_to_json(p)
        d = json.loads(raw)
        assert "policy_version" in d
        assert "strategy" in d
        assert "execution" in d
        assert "risk" in d
        assert "hard_limits" in d

    def test_json_to_policy_validates_by_default(self):
        raw = json.dumps({
            "policy_version": "bad-version",
            "research_run_id": "",
        })
        with pytest.raises(PolicyValidationError):
            json_to_policy(raw, validate=True)

    def test_json_to_policy_skip_validation(self):
        raw = json.dumps({
            "policy_version": "bad-version",
            "research_run_id": "",
        })
        p = json_to_policy(raw, validate=False)
        assert p.policy_version == "bad-version"


class TestFilePersistence:
    def test_save_and_load(self):
        p = LiveParameterPolicy(
            policy_version="1.0.0",
            research_run_id="ZS-2026-003",
            strategy=StrategyParams(z_entry_threshold=2.5),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "policy.json")
            save_policy(p, path)
            assert os.path.exists(path)

            p2 = load_policy(path)
            assert p.policy_version == p2.policy_version
            assert p.research_run_id == p2.research_run_id
            assert p.strategy.z_entry_threshold == p2.strategy.z_entry_threshold

    def test_save_validates(self):
        p = LiveParameterPolicy(
            policy_version="bad",
            research_run_id="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "policy.json")
            with pytest.raises(PolicyValidationError):
                save_policy(p, path)

    def test_load_validates_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "policy.json")
            # Write invalid policy directly
            with open(path, "w") as f:
                json.dump({
                    "policy_version": "bad",
                    "research_run_id": "",
                }, f)
            with pytest.raises(PolicyValidationError):
                load_policy(path, validate=True)

    def test_load_skip_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "policy.json")
            with open(path, "w") as f:
                json.dump({
                    "policy_version": "bad",
                    "research_run_id": "",
                }, f)
            p = load_policy(path, validate=False)
            assert p.policy_version == "bad"
