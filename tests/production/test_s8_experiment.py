"""
Tests for S8 Experiment Identity (S8.0)
=======================================
Verifies experiment configuration, config hashing, and trade logger
experiment identity fields.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_experiment.py -v --noconftest
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure nestquant is importable
# ---------------------------------------------------------------------------

from nestquant.core.configuration.experiment import (
    ExperimentConfig,
    ExperimentPhase,
    RiskIdentity,
    StrategyIdentity,
    UniverseIdentity,
)
from nestquant.production.execution.trade_logger import SignalRecord, TradeLogger


# ===================================================================
# ExperimentConfig
# ===================================================================


class TestExperimentConfig:
    """Test experiment identity and hashing."""

    def test_creates_with_defaults(self):
        cfg = ExperimentConfig()
        assert cfg.experiment_id.startswith("S8-")
        assert cfg.strategy.name == "breakout"
        assert cfg.risk.risk_per_trade_pct == 0.0015
        assert len(cfg.universe.pairs) == 7

    def test_experiment_id_is_unique(self):
        a = ExperimentConfig()
        b = ExperimentConfig()
        assert a.experiment_id != b.experiment_id

    def test_config_hash_is_deterministic(self):
        """Same parameters → same hash, always."""
        a = StrategyIdentity()
        b = StrategyIdentity()
        assert a.config_hash() == b.config_hash()

    def test_config_hash_changes_with_params(self):
        a = StrategyIdentity(parameters={"atr_sl_multiplier": 2.0})
        b = StrategyIdentity(parameters={"atr_sl_multiplier": 3.0})
        assert a.config_hash() != b.config_hash()

    def test_risk_hash_is_deterministic(self):
        a = RiskIdentity()
        b = RiskIdentity()
        assert a.config_hash() == b.config_hash()

    def test_risk_hash_changes_with_params(self):
        a = RiskIdentity(risk_per_trade_pct=0.0015)
        b = RiskIdentity(risk_per_trade_pct=0.003)
        assert a.config_hash() != b.config_hash()

    def test_universe_hash_is_deterministic(self):
        a = UniverseIdentity()
        b = UniverseIdentity()
        assert a.config_hash() == b.config_hash()

    def test_full_config_hash_deterministic(self):
        a = ExperimentConfig()
        b = ExperimentConfig(
            experiment_id=a.experiment_id,
            strategy=a.strategy,
            risk=a.risk,
            universe=a.universe,
        )
        assert a.full_config_hash() == b.full_config_hash()

    def test_full_config_hash_varies_with_strategy(self):
        base = ExperimentConfig()
        modified = ExperimentConfig(
            strategy=StrategyIdentity(version="2.0.0"),
        )
        assert base.full_config_hash() != modified.full_config_hash()

    def test_to_dict_contains_all_hashes(self):
        cfg = ExperimentConfig()
        d = cfg.to_dict()
        assert "experiment_id" in d
        assert "strategy_config_hash" in d
        assert "risk_config_hash" in d
        assert "universe_config_hash" in d
        assert "full_config_hash" in d
        assert "created_at" in d
        assert "strategy" in d
        assert "risk" in d
        assert "universe" in d

    def test_to_dict_is_json_serializable(self):
        cfg = ExperimentConfig()
        d = cfg.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0

    def test_summary_contains_key_info(self):
        cfg = ExperimentConfig()
        s = cfg.summary()
        assert cfg.experiment_id in s
        assert "breakout" in s
        assert cfg.full_config_hash() in s

    def test_frozen_dataclass(self):
        cfg = ExperimentConfig()
        with pytest.raises(AttributeError):
            cfg.experiment_id = "modified"


class TestExperimentPhase:
    """Test experiment lifecycle phases."""

    def test_phases_exist(self):
        assert ExperimentPhase.INITIALIZING == "INITIALIZING"
        assert ExperimentPhase.HEALTH_CHECK == "HEALTH_CHECK"
        assert ExperimentPhase.RUNNING == "RUNNING"
        assert ExperimentPhase.PAUSED == "PAUSED"
        assert ExperimentPhase.STOPPED == "STOPPED"
        assert ExperimentPhase.EMERGENCY_STOP == "EMERGENCY_STOP"


# ===================================================================
# TradeLogger experiment identity
# ===================================================================


class TestTradeLoggerExperimentIdentity:
    """Test that TradeLogger supports experiment identity fields."""

    def test_signal_record_includes_experiment_fields(self):
        record = SignalRecord(
            signal_id="test-signal-001",
            timestamp="2026-09-03T12:00:00+00:00",
            symbol="EUR/USD",
            direction="BUY",
            strategy_params={"lookback": 5},
            swing_level=1.0850,
            signal_bar_close=1.0860,
            expected_entry=1.0850,
            expected_sl=1.0820,
            expected_tp=1.0950,
            atr_at_signal=0.0030,
            spread_at_signal=0.8,
            experiment_id="S8-test123",
            strategy_version="breakout-1.0.0",
            config_hash="abc123",
        )
        d = record.to_dict()
        assert d["experiment_id"] == "S8-test123"
        assert d["strategy_version"] == "breakout-1.0.0"
        assert d["config_hash"] == "abc123"

    def test_signal_record_defaults_experiment_fields_empty(self):
        record = SignalRecord(
            signal_id="test-signal-002",
            timestamp="2026-09-03T12:00:00+00:00",
            symbol="EUR/USD",
            direction="SELL",
            strategy_params={},
            swing_level=1.0850,
            signal_bar_close=1.0860,
            expected_entry=1.0850,
            expected_sl=1.0880,
            expected_tp=1.0750,
            atr_at_signal=0.0030,
            spread_at_signal=0.8,
        )
        d = record.to_dict()
        assert d["experiment_id"] == ""
        assert d["strategy_version"] == ""
        assert d["config_hash"] == ""

    def test_create_signal_with_experiment_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(tmpdir)
            record = logger.create_signal(
                symbol="EUR/USD",
                direction="BUY",
                swing_level=1.0850,
                signal_bar_close=1.0860,
                expected_entry=1.0850,
                expected_sl=1.0820,
                expected_tp=1.0950,
                atr_at_signal=0.0030,
                spread_at_signal=0.8,
                experiment_id="S8-test456",
                strategy_version="breakout-1.0.0",
                config_hash="def456",
            )
            assert record.experiment_id == "S8-test456"
            assert record.strategy_version == "breakout-1.0.0"
            assert record.config_hash == "def456"

            # Verify persisted
            signals = logger.get_signals()
            assert len(signals) == 1
            assert signals[0]["experiment_id"] == "S8-test456"

    def test_create_signal_without_experiment_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(tmpdir)
            record = logger.create_signal(
                symbol="GBP/USD",
                direction="SELL",
                swing_level=1.2700,
                signal_bar_close=1.2690,
                expected_entry=1.2700,
                expected_sl=1.2730,
                expected_tp=1.2600,
                atr_at_signal=0.0040,
                spread_at_signal=1.0,
            )
            assert record.experiment_id == ""
            assert record.strategy_version == ""
            assert record.config_hash == ""

    def test_full_experiment_flow(self):
        """End-to-end: create experiment, log signal with identity, verify persistence."""
        exp = ExperimentConfig(
            strategy=StrategyIdentity(version="1.0.0"),
            risk=RiskIdentity(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(tmpdir)
            record = logger.create_signal(
                symbol="EUR/USD",
                direction="BUY",
                swing_level=1.0850,
                signal_bar_close=1.0860,
                expected_entry=1.0850,
                expected_sl=1.0820,
                expected_tp=1.0950,
                atr_at_signal=0.0030,
                spread_at_signal=0.8,
                experiment_id=exp.experiment_id,
                strategy_version=f"{exp.strategy.name}-{exp.strategy.version}",
                config_hash=exp.full_config_hash(),
            )

            # Verify all experiment identity fields persisted
            signals = logger.get_signals()
            assert len(signals) == 1
            s = signals[0]
            assert s["experiment_id"] == exp.experiment_id
            assert s["strategy_version"] == "breakout-1.0.0"
            assert s["config_hash"] == exp.full_config_hash()
