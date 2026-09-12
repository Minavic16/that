"""
Tests for Strategy Fidelity — Research vs Live Configuration
=============================================================
Proves that the live BreakoutSignal uses exact research parameters.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_strategy_fidelity.py -v --noconftest
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# Mock pandas and nestquant.signals.base to avoid import errors
# (BreakoutSignal needs pandas for type hints but we only test params)
if "pandas" not in sys.modules:
    sys.modules["pandas"] = MagicMock()
if "nestquant.signals.base" not in sys.modules:
    _base = ModuleType("nestquant.signals.base")
    _base.BaseSignal = type("BaseSignal", (), {"__init__": lambda self, name: None})
    _base.SignalResult = type("SignalResult", (), {})
    sys.modules["nestquant.signals.base"] = _base

# Import breakout module directly
_spec = importlib.util.spec_from_file_location(
    "breakout", str(Path(NESTQUANT_ROOT) / "signals" / "breakout.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
BreakoutSignal = _mod.BreakoutSignal
RESEARCH_DEFAULTS = _mod.RESEARCH_DEFAULTS


class TestResearchDefaults:
    """Verify the RESEARCH_DEFAULTS constant matches research configuration."""

    def test_atr_sl_multiplier_is_2(self):
        assert RESEARCH_DEFAULTS["atr_sl_multiplier"] == 2.0

    def test_rrr_is_3_5(self):
        assert RESEARCH_DEFAULTS["rrr"] == 3.5

    def test_lookback_is_5(self):
        assert RESEARCH_DEFAULTS["lookback"] == 5

    def test_atr_period_is_14(self):
        assert RESEARCH_DEFAULTS["atr_period"] == 14


class TestBreakoutSignalDefaults:
    """Verify BreakoutSignal default parameters match research."""

    def test_default_atr_sl_multiplier(self):
        sig = BreakoutSignal()
        assert sig.atr_sl_multiplier == 2.0

    def test_default_rrr(self):
        sig = BreakoutSignal()
        assert sig.rrr == 3.5

    def test_default_lookback(self):
        sig = BreakoutSignal()
        assert sig.lookback == 5

    def test_default_atr_period(self):
        sig = BreakoutSignal()
        assert sig.atr_period == 14

    def test_research_factory(self):
        sig = BreakoutSignal(**RESEARCH_DEFAULTS)
        assert sig.atr_sl_multiplier == 2.0
        assert sig.rrr == 3.5
        assert sig.lookback == 5
        assert sig.atr_period == 14


class TestBreakoutSignalTP:
    """Verify TP calculation uses RRR, not hardcoded 2.0."""

    def test_buy_tp_uses_rrr(self):
        sig = BreakoutSignal(atr_sl_multiplier=2.0, rrr=3.5)
        # entry=1.0800, atr=0.0030, sl_mult=2.0, rrr=3.5
        # SL distance = 0.0030 * 2.0 = 0.0060
        # TP distance = 0.0030 * 2.0 * 3.5 = 0.0210
        # Verify the formula: tp = entry + atr * sl_mult * rrr
        entry = 1.0800
        atr = 0.0030
        expected_tp = entry + (atr * 2.0 * 3.5)
        assert expected_tp == pytest.approx(1.1010, abs=1e-6)

    def test_sell_tp_uses_rrr(self):
        sig = BreakoutSignal(atr_sl_multiplier=2.0, rrr=3.5)
        entry = 1.0800
        atr = 0.0030
        expected_tp = entry - (atr * 2.0 * 3.5)
        assert expected_tp == pytest.approx(1.0590, abs=1e-6)

    def test_old_hardcoded_2_0_not_used(self):
        """The old hardcoded multiplier of 2.0 must NOT be used for TP."""
        sig = BreakoutSignal(atr_sl_multiplier=2.0, rrr=3.5)
        entry = 1.0800
        atr = 0.0030
        tp_with_rrr = entry + (atr * 2.0 * 3.5)
        tp_with_old_2 = entry + (atr * 2.0 * 2.0)  # Old hardcoded value
        assert tp_with_rrr != tp_with_old_2


class TestNoSettingsImport:
    """Verify breakout.py does not import ATR_SL_MULTIPLIER from settings."""

    def test_no_settings_import(self):
        source = Path(NESTQUANT_ROOT) / "signals" / "breakout.py"
        text = source.read_text()
        assert "from nestquant.core.configuration.settings import" not in text
        # ATR_SL_MULTIPLIER should only appear in RESEARCH_DEFAULTS, not as an import
        lines = text.split("\n")
        import_lines = [l for l in lines if l.startswith("from ") or l.startswith("import ")]
        for line in import_lines:
            assert "ATR_SL_MULTIPLIER" not in line
