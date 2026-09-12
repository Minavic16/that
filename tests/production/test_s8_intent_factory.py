"""
Tests for S8.2 — Intent Factory
=================================
Verifies SignalResult → TradeIntent conversion, signal_id generation,
direction mapping, validation, and experiment identity propagation.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_intent_factory.py -v --noconftest
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import pytest


from nestquant.core.contracts.execution_contracts import Direction, TradeIntent
from nestquant.production.execution.intent_factory import IntentFactory, IntentFactoryError

# Mock SignalResult to avoid importing signals.base (which requires pandas)
# This is a lightweight mirror of the real SignalResult for testing only.


@dataclass
class MockSignalResult:
    pair: str
    direction: str
    strength: float
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.direction in ("BUY", "SELL") and self.strength > 0.0


SignalResult = MockSignalResult


# ===================================================================
# IntentFactory
# ===================================================================


class TestIntentFactoryCreation:
    def test_creates_with_defaults(self):
        factory = IntentFactory()
        assert factory.strategy_version == "breakout-1.0.0"
        assert factory.experiment_id == ""

    def test_creates_with_custom_params(self):
        factory = IntentFactory(
            strategy_version="breakout-2.0.0",
            policy_version="s8-1.0.0",
            experiment_id="S8-test123",
            config_hash="abc123",
        )
        assert factory.strategy_version == "breakout-2.0.0"
        assert factory.experiment_id == "S8-test123"


class TestCreateIntent:
    def _make_buy_signal(self) -> SignalResult:
        return SignalResult(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.0850,
            sl_price=1.0820,
            tp_price=1.0950,
            metadata={"swing_high": 1.0850, "atr": 0.0030},
        )

    def _make_sell_signal(self) -> SignalResult:
        return SignalResult(
            pair="GBP/USD",
            direction="SELL",
            strength=0.8,
            entry_price=1.2700,
            sl_price=1.2730,
            tp_price=1.2600,
            metadata={},
        )

    def test_buy_signal_creates_buy_intent(self):
        factory = IntentFactory()
        intent = factory.create_intent(self._make_buy_signal())

        assert intent.pair == "EUR/USD"
        assert intent.direction == Direction.BUY
        assert intent.entry_price == 1.0850
        assert intent.stop_loss == 1.0820
        assert intent.take_profit == 1.0950
        assert intent.signal_strength == 1.0

    def test_sell_signal_creates_sell_intent(self):
        factory = IntentFactory()
        intent = factory.create_intent(self._make_sell_signal())

        assert intent.pair == "GBP/USD"
        assert intent.direction == Direction.SELL
        assert intent.entry_price == 1.2700
        assert intent.stop_loss == 1.2730
        assert intent.take_profit == 1.2600

    def test_intent_has_timestamp(self):
        factory = IntentFactory()
        intent = factory.create_intent(self._make_buy_signal())

        assert intent.timestamp is not None
        assert intent.timestamp.tzinfo == UTC

    def test_intent_uses_provided_timestamp(self):
        factory = IntentFactory()
        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        intent = factory.create_intent(self._make_buy_signal(), timestamp=ts)

        assert intent.timestamp == ts

    def test_intent_has_strategy_version(self):
        factory = IntentFactory(strategy_version="breakout-2.0.0")
        intent = factory.create_intent(self._make_buy_signal())

        assert intent.strategy == "breakout-2.0.0"

    def test_intent_has_policy_version(self):
        factory = IntentFactory(policy_version="s8-1.0.0")
        intent = factory.create_intent(self._make_buy_signal())

        assert intent.policy_version == "s8-1.0.0"

    def test_intent_validates(self):
        factory = IntentFactory()
        intent = factory.create_intent(self._make_buy_signal())
        errors = intent.validate()
        assert errors == []

    def test_intent_is_valid_trade_intent(self):
        factory = IntentFactory()
        intent = factory.create_intent(self._make_buy_signal())
        assert isinstance(intent, TradeIntent)


class TestCreateIntentValidation:
    def test_neutral_signal_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(pair="EUR/USD", direction="NEUTRAL", strength=0.0)
        with pytest.raises(IntentFactoryError, match="inactive signal"):
            factory.create_intent(signal)

    def test_zero_strength_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=0.0,
            entry_price=1.0850, sl_price=1.0820, tp_price=1.0950,
        )
        with pytest.raises(IntentFactoryError, match="inactive signal"):
            factory.create_intent(signal)

    def test_no_entry_price_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=None, sl_price=1.0820, tp_price=1.0950,
        )
        with pytest.raises(IntentFactoryError, match="entry_price"):
            factory.create_intent(signal)

    def test_zero_entry_price_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=0.0, sl_price=1.0820, tp_price=1.0950,
        )
        with pytest.raises(IntentFactoryError, match="entry_price"):
            factory.create_intent(signal)

    def test_no_sl_price_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=1.0850, sl_price=None, tp_price=1.0950,
        )
        with pytest.raises(IntentFactoryError, match="sl_price"):
            factory.create_intent(signal)

    def test_no_tp_price_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=1.0850, sl_price=1.0820, tp_price=None,
        )
        with pytest.raises(IntentFactoryError, match="tp_price"):
            factory.create_intent(signal)

    def test_invalid_direction_rejected(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="LONG", strength=1.0,
            entry_price=1.0850, sl_price=1.0820, tp_price=1.0950,
        )
        # "LONG" is not BUY/SELL, so is_active returns False → inactive signal error
        with pytest.raises(IntentFactoryError):
            factory.create_intent(signal)


class TestCreateIntentWithId:
    def test_returns_tuple(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=1.0850, sl_price=1.0820, tp_price=1.0950,
        )
        result = factory.create_intent_with_id(signal)

        assert isinstance(result, tuple)
        assert len(result) == 2
        intent, signal_id = result
        assert isinstance(intent, TradeIntent)
        assert isinstance(signal_id, str)
        assert len(signal_id) > 0

    def test_signal_id_is_unique(self):
        factory = IntentFactory()
        signal = SignalResult(
            pair="EUR/USD", direction="BUY", strength=1.0,
            entry_price=1.0850, sl_price=1.0820, tp_price=1.0950,
        )
        _, id1 = factory.create_intent_with_id(signal)
        _, id2 = factory.create_intent_with_id(signal)
        assert id1 != id2


class TestRepr:
    def test_repr_contains_strategy(self):
        factory = IntentFactory(strategy_version="breakout-2.0.0")
        r = repr(factory)
        assert "breakout-2.0.0" in r

    def test_repr_contains_experiment(self):
        factory = IntentFactory(experiment_id="S8-test123")
        r = repr(factory)
        assert "S8-test123" in r
