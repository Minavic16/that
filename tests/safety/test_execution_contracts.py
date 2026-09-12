"""
Tests for nestquant.execution.contracts module.
"""

from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from nestquant.core.contracts.execution_contracts import (
    ContractValidationError,
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
    RiskDecision,
    TradeIntent,
)


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


class TestDirection:
    def test_buy_value(self):
        assert Direction.BUY == "BUY"

    def test_sell_value(self):
        assert Direction.SELL == "SELL"

    def test_from_string(self):
        assert Direction("BUY") is Direction.BUY
        assert Direction("SELL") is Direction.SELL

    def test_invalid_direction(self):
        with pytest.raises(ValueError):
            Direction("HOLD")


# ---------------------------------------------------------------------------
# TradeIntent
# ---------------------------------------------------------------------------


class TestTradeIntent:
    def _valid_intent(self, **overrides) -> TradeIntent:
        defaults = dict(
            pair="EUR/USD",
            direction=Direction.BUY,
            signal_strength=0.75,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            strategy="zscore",
            policy_version="1.0.0",
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return TradeIntent(**defaults)

    def test_valid_construction(self):
        t = self._valid_intent()
        assert t.pair == "EUR/USD"
        assert t.direction == Direction.BUY
        assert t.signal_strength == 0.75
        assert t.entry_price == 1.1000
        assert t.stop_loss == 1.0950
        assert t.take_profit == 1.1150
        assert t.strategy == "zscore"
        assert t.policy_version == "1.0.0"

    def test_frozen(self):
        t = self._valid_intent()
        with pytest.raises(AttributeError):
            t.pair = "GBP/USD"

    def test_valid_sell(self):
        t = self._valid_intent(
            direction=Direction.SELL,
            stop_loss=1.1050,
            take_profit=1.0850,
        )
        assert t.direction == Direction.SELL
        assert t.validate() == []

    def test_validation_empty_pair(self):
        t = self._valid_intent(pair="")
        errors = t.validate()
        assert any("pair" in e for e in errors)

    def test_validation_whitespace_pair(self):
        t = self._valid_intent(pair="   ")
        errors = t.validate()
        assert any("pair" in e for e in errors)

    def test_validation_negative_entry(self):
        t = self._valid_intent(entry_price=-1.0)
        errors = t.validate()
        assert any("entry_price" in e for e in errors)

    def test_validation_zero_stop_loss(self):
        t = self._valid_intent(stop_loss=0)
        errors = t.validate()
        assert any("stop_loss" in e for e in errors)

    def test_validation_negative_take_profit(self):
        t = self._valid_intent(take_profit=-1.0)
        errors = t.validate()
        assert any("take_profit" in e for e in errors)

    def test_validation_signal_strength_below_range(self):
        t = self._valid_intent(signal_strength=-0.1)
        errors = t.validate()
        assert any("signal_strength" in e for e in errors)

    def test_validation_signal_strength_above_range(self):
        t = self._valid_intent(signal_strength=1.1)
        errors = t.validate()
        assert any("signal_strength" in e for e in errors)

    def test_validation_signal_strength边界(self):
        t0 = self._valid_intent(signal_strength=0.0)
        t1 = self._valid_intent(signal_strength=1.0)
        assert t0.validate() == []
        assert t1.validate() == []

    def test_validation_empty_policy_version(self):
        t = self._valid_intent(policy_version="")
        errors = t.validate()
        assert any("policy_version" in e for e in errors)

    def test_validation_naive_timestamp(self):
        t = self._valid_intent(timestamp=datetime(2026, 1, 15, 12, 0, 0))
        errors = t.validate()
        assert any("timezone" in e for e in errors)

    def test_validation_non_utc_timestamp(self):
        from datetime import timedelta
        tz = timezone(timedelta(hours=5))
        t = self._valid_intent(timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=tz))
        errors = t.validate()
        assert any("UTC" in e for e in errors)

    def test_buy_sl_above_entry_rejected(self):
        t = self._valid_intent(
            direction=Direction.BUY,
            stop_loss=1.1050,  # above entry 1.1000
        )
        errors = t.validate()
        assert any("stop_loss" in e and "entry_price" in e for e in errors)

    def test_buy_tp_below_entry_rejected(self):
        t = self._valid_intent(
            direction=Direction.BUY,
            take_profit=1.0900,  # below entry 1.1000
        )
        errors = t.validate()
        assert any("take_profit" in e and "entry_price" in e for e in errors)

    def test_sell_sl_below_entry_rejected(self):
        t = self._valid_intent(
            direction=Direction.SELL,
            stop_loss=1.0900,  # below entry 1.1000
        )
        errors = t.validate()
        assert any("stop_loss" in e and "entry_price" in e for e in errors)

    def test_sell_tp_above_entry_rejected(self):
        t = self._valid_intent(
            direction=Direction.SELL,
            take_profit=1.1100,  # above entry 1.1000
        )
        errors = t.validate()
        assert any("take_profit" in e and "entry_price" in e for e in errors)

    def test_assert_valid_passes(self):
        t = self._valid_intent()
        t.assert_valid()  # should not raise

    def test_assert_valid_raises(self):
        t = self._valid_intent(pair="")
        with pytest.raises(ContractValidationError) as exc_info:
            t.assert_valid()
        assert len(exc_info.value.errors) >= 1

    def test_equality(self):
        t1 = self._valid_intent()
        t2 = self._valid_intent()
        assert t1 == t2

    def test_inequality(self):
        t1 = self._valid_intent(pair="EUR/USD")
        t2 = self._valid_intent(pair="GBP/USD")
        assert t1 != t2


# ---------------------------------------------------------------------------
# RiskDecision
# ---------------------------------------------------------------------------


class TestRiskDecision:
    def _approved_decision(self, **overrides) -> RiskDecision:
        defaults = dict(
            approved=True,
            reason="Within risk limits",
            risk_amount=20.0,
            lot_size=0.10,
            policy_version="1.0.0",
        )
        defaults.update(overrides)
        return RiskDecision(**defaults)

    def _rejected_decision(self, **overrides) -> RiskDecision:
        defaults = dict(
            approved=False,
            reason="Exceeds max drawdown",
            risk_amount=0.0,
            lot_size=0.0,
            policy_version="1.0.0",
        )
        defaults.update(overrides)
        return RiskDecision(**defaults)

    def test_valid_approved_construction(self):
        r = self._approved_decision()
        assert r.approved is True
        assert r.lot_size == 0.10
        assert r.risk_amount == 20.0

    def test_valid_rejected_construction(self):
        r = self._rejected_decision()
        assert r.approved is False
        assert r.reason == "Exceeds max drawdown"

    def test_frozen(self):
        r = self._approved_decision()
        with pytest.raises(AttributeError):
            r.approved = False

    def test_validation_negative_risk_amount(self):
        r = self._approved_decision(risk_amount=-1.0)
        errors = r.validate()
        assert any("risk_amount" in e for e in errors)

    def test_validation_negative_lot_size(self):
        r = self._approved_decision(lot_size=-0.1)
        errors = r.validate()
        assert any("lot_size" in e for e in errors)

    def test_validation_zero_risk_amount_ok(self):
        r = self._approved_decision(risk_amount=0.0)
        errors = r.validate()
        assert errors == []

    def test_validation_approved_zero_lot_rejected(self):
        r = self._approved_decision(lot_size=0)
        errors = r.validate()
        assert any("lot_size" in e for e in errors)

    def test_validation_rejected_empty_reason(self):
        r = self._rejected_decision(reason="")
        errors = r.validate()
        assert any("reason" in e for e in errors)

    def test_validation_rejected_whitespace_reason(self):
        r = self._rejected_decision(reason="   ")
        errors = r.validate()
        assert any("reason" in e for e in errors)

    def test_validation_approved_empty_reason_ok(self):
        r = self._approved_decision(reason="")
        errors = r.validate()
        assert errors == []

    def test_validation_approved_with_rejection_reason_rejected(self):
        """Approved decision must not contain rejection language."""
        r = self._approved_decision(reason="Exceeds max drawdown")
        errors = r.validate()
        assert any("rejection language" in e for e in errors)

    def test_validation_approved_with_reject_in_reason(self):
        r = self._approved_decision(reason="reject this trade")
        errors = r.validate()
        assert any("rejection language" in e for e in errors)

    def test_validation_approved_with_insufficient_in_reason(self):
        r = self._approved_decision(reason="Insufficient margin")
        errors = r.validate()
        assert any("rejection language" in e for e in errors)

    def test_validation_approved_with_limit_in_reason(self):
        r = self._approved_decision(reason="blocked by risk check")
        errors = r.validate()
        assert any("rejection language" in e for e in errors)

    def test_validation_approved_neutral_reason_ok(self):
        r = self._approved_decision(reason="Within risk limits")
        errors = r.validate()
        assert errors == []

    def test_validation_empty_policy_version(self):
        r = self._approved_decision(policy_version="")
        errors = r.validate()
        assert any("policy_version" in e for e in errors)

    def test_assert_valid_passes(self):
        r = self._approved_decision()
        r.assert_valid()

    def test_assert_valid_raises(self):
        r = self._rejected_decision(reason="")
        with pytest.raises(ContractValidationError):
            r.assert_valid()

    def test_equality(self):
        r1 = self._approved_decision()
        r2 = self._approved_decision()
        assert r1 == r2

    def test_inequality(self):
        r1 = self._approved_decision(lot_size=0.10)
        r2 = self._approved_decision(lot_size=0.20)
        assert r1 != r2


# ---------------------------------------------------------------------------
# OrderRequest
# ---------------------------------------------------------------------------


class TestOrderRequest:
    def _valid_request(self, **overrides) -> OrderRequest:
        defaults = dict(
            pair="EUR/USD",
            direction=Direction.BUY,
            lot_size=0.10,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            policy_version="1.0.0",
        )
        defaults.update(overrides)
        return OrderRequest(**defaults)

    def test_valid_construction(self):
        o = self._valid_request()
        assert o.pair == "EUR/USD"
        assert o.direction == Direction.BUY
        assert o.lot_size == 0.10

    def test_frozen(self):
        o = self._valid_request()
        with pytest.raises(AttributeError):
            o.lot_size = 0.50

    def test_valid_sell(self):
        o = self._valid_request(
            direction=Direction.SELL,
            stop_loss=1.1050,
            take_profit=1.0850,
        )
        assert o.validate() == []

    def test_validation_empty_pair(self):
        o = self._valid_request(pair="")
        errors = o.validate()
        assert any("pair" in e for e in errors)

    def test_validation_zero_lot(self):
        o = self._valid_request(lot_size=0)
        errors = o.validate()
        assert any("lot_size" in e for e in errors)

    def test_validation_negative_lot(self):
        o = self._valid_request(lot_size=-0.1)
        errors = o.validate()
        assert any("lot_size" in e for e in errors)

    def test_validation_negative_entry(self):
        o = self._valid_request(entry_price=-1.0)
        errors = o.validate()
        assert any("entry_price" in e for e in errors)

    def test_validation_negative_sl(self):
        o = self._valid_request(stop_loss=-1.0)
        errors = o.validate()
        assert any("stop_loss" in e for e in errors)

    def test_validation_negative_tp(self):
        o = self._valid_request(take_profit=-1.0)
        errors = o.validate()
        assert any("take_profit" in e for e in errors)

    def test_validation_empty_policy_version(self):
        o = self._valid_request(policy_version="")
        errors = o.validate()
        assert any("policy_version" in e for e in errors)

    def test_assert_valid_passes(self):
        o = self._valid_request()
        o.assert_valid()

    def test_assert_valid_raises(self):
        o = self._valid_request(lot_size=0)
        with pytest.raises(ContractValidationError):
            o.assert_valid()

    def test_equality(self):
        o1 = self._valid_request()
        o2 = self._valid_request()
        assert o1 == o2

    def test_inequality(self):
        o1 = self._valid_request(lot_size=0.10)
        o2 = self._valid_request(lot_size=0.20)
        assert o1 != o2

    def test_not_broker_coupled(self):
        """OrderRequest must not reference any broker-specific API."""
        o = self._valid_request()
        # Should not have any MT5/cTrader attributes
        assert not hasattr(o, "magic_number")
        assert not hasattr(o, "deviation")
        assert not hasattr(o, "comment")
        assert not hasattr(o, "type_filling")

    def test_asdict_roundtrip(self):
        """Frozen dataclass round-trips through dict."""
        o1 = self._valid_request()
        d = asdict(o1)
        o2 = OrderRequest(**d)
        assert o1 == o2


# ---------------------------------------------------------------------------
# Serialization / round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Verify frozen dataclasses survive dict round-trips."""

    def test_trade_intent_roundtrip(self):
        from dataclasses import asdict
        t1 = TradeIntent(
            pair="EUR/USD",
            direction=Direction.BUY,
            signal_strength=0.75,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            strategy="zscore",
            policy_version="1.0.0",
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        d = asdict(t1)
        t2 = TradeIntent(**d)
        assert t1 == t2
        assert t1 is not t2

    def test_risk_decision_roundtrip(self):
        from dataclasses import asdict
        r1 = RiskDecision(
            approved=True,
            reason="Within risk limits",
            risk_amount=20.0,
            lot_size=0.10,
            policy_version="1.0.0",
        )
        d = asdict(r1)
        r2 = RiskDecision(**d)
        assert r1 == r2

    def test_order_request_roundtrip(self):
        from dataclasses import asdict
        o1 = OrderRequest(
            pair="GBP/USD",
            direction=Direction.SELL,
            lot_size=0.05,
            entry_price=1.2700,
            stop_loss=1.2750,
            take_profit=1.2550,
            policy_version="2.0.0",
        )
        d = asdict(o1)
        o2 = OrderRequest(**d)
        assert o1 == o2

    def test_execution_result_roundtrip(self):
        from dataclasses import asdict
        r1 = ExecutionResult(
            status=ExecutionStatus.FILLED,
            order_id="ORD-99999",
            requested_price=1.1000,
            fill_price=1.1003,
            slippage_pips=0.3,
            rejection_reason=None,
        )
        d = asdict(r1)
        r2 = ExecutionResult(**d)
        assert r1 == r2

    def test_direction_preserved_in_roundtrip(self):
        from dataclasses import asdict
        t = TradeIntent(
            pair="USD/JPY",
            direction=Direction.SELL,
            signal_strength=0.5,
            entry_price=150.0,
            stop_loss=150.50,
            take_profit=149.0,
            strategy="mr",
            policy_version="1.0.0",
            timestamp=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        d = asdict(t)
        assert d["direction"] == "SELL"
        t2 = TradeIntent(**d)
        assert t2.direction is Direction.SELL


# ---------------------------------------------------------------------------
# Cross-contract: no forbidden imports
# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def _filled_result(self, **overrides) -> ExecutionResult:
        defaults = dict(
            status=ExecutionStatus.FILLED,
            order_id="ORD-12345",
            requested_price=1.1000,
            fill_price=1.1002,
            slippage_pips=0.2,
            rejection_reason=None,
        )
        defaults.update(overrides)
        return ExecutionResult(**defaults)

    def _rejected_result(self, **overrides) -> ExecutionResult:
        defaults = dict(
            status=ExecutionStatus.REJECTED,
            order_id=None,
            requested_price=1.1000,
            fill_price=None,
            slippage_pips=0.0,
            rejection_reason="Insufficient margin",
        )
        defaults.update(overrides)
        return ExecutionResult(**defaults)

    def _error_result(self, **overrides) -> ExecutionResult:
        defaults = dict(
            status=ExecutionStatus.ERROR,
            order_id=None,
            requested_price=1.1000,
            fill_price=None,
            slippage_pips=0.0,
            rejection_reason="Connection timeout",
        )
        defaults.update(overrides)
        return ExecutionResult(**defaults)

    def test_valid_filled_construction(self):
        r = self._filled_result()
        assert r.status == ExecutionStatus.FILLED
        assert r.order_id == "ORD-12345"
        assert r.fill_price == 1.1002
        assert r.is_filled is True
        assert r.is_rejected is False
        assert r.is_error is False

    def test_valid_rejected_construction(self):
        r = self._rejected_result()
        assert r.status == ExecutionStatus.REJECTED
        assert r.is_filled is False
        assert r.is_rejected is True
        assert r.is_error is False

    def test_valid_error_construction(self):
        r = self._error_result()
        assert r.status == ExecutionStatus.ERROR
        assert r.is_filled is False
        assert r.is_rejected is False
        assert r.is_error is True

    def test_frozen(self):
        r = self._filled_result()
        with pytest.raises(AttributeError):
            r.status = ExecutionStatus.REJECTED

    def test_validation_negative_slippage(self):
        r = self._filled_result(slippage_pips=-0.5)
        errors = r.validate()
        assert any("slippage_pips" in e for e in errors)

    def test_validation_zero_slippage_ok(self):
        r = self._filled_result(slippage_pips=0.0)
        assert r.validate() == []

    def test_validation_filled_no_fill_price(self):
        r = self._filled_result(fill_price=None)
        errors = r.validate()
        assert any("fill_price" in e for e in errors)

    def test_validation_filled_zero_fill_price(self):
        r = self._filled_result(fill_price=0)
        errors = r.validate()
        assert any("fill_price" in e for e in errors)

    def test_validation_filled_with_rejection_reason(self):
        r = self._filled_result(rejection_reason="oops")
        errors = r.validate()
        assert any("rejection_reason" in e for e in errors)

    def test_validation_rejected_no_reason(self):
        r = self._rejected_result(rejection_reason="")
        errors = r.validate()
        assert any("rejection_reason" in e for e in errors)

    def test_validation_rejected_with_fill_price(self):
        r = self._rejected_result(fill_price=1.1000)
        errors = r.validate()
        assert any("fill_price" in e for e in errors)

    def test_validation_error_no_reason(self):
        r = self._error_result(rejection_reason="")
        errors = r.validate()
        assert any("rejection_reason" in e for e in errors)

    def test_validation_negative_requested_price(self):
        r = self._filled_result(requested_price=-1.0)
        errors = r.validate()
        assert any("requested_price" in e for e in errors)

    def test_assert_valid_passes(self):
        r = self._filled_result()
        r.assert_valid()

    def test_assert_valid_raises(self):
        r = self._filled_result(fill_price=None)
        with pytest.raises(ContractValidationError):
            r.assert_valid()

    def test_equality(self):
        r1 = self._filled_result()
        r2 = self._filled_result()
        assert r1 == r2

    def test_inequality(self):
        r1 = self._filled_result(order_id="A")
        r2 = self._filled_result(order_id="B")
        assert r1 != r2


# ---------------------------------------------------------------------------
# Cross-contract: no forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    """Verify contracts do not import MT5, research, or strategy modules."""

    def test_no_mt5_import(self):
        import nestquant.core.contracts.execution_contracts as mod
        source = open(mod.__file__).read()
        assert "MetaTrader5" not in source
        assert "mt5" not in source.lower().split("#")[0]  # not in imports

    def test_no_research_import(self):
        import nestquant.core.contracts.execution_contracts as mod
        source = open(mod.__file__).read()
        assert "from nestquant.research" not in source
        assert "import nestquant.research" not in source

    def test_no_strategy_import(self):
        import nestquant.core.contracts.execution_contracts as mod
        source = open(mod.__file__).read()
        assert "from nestquant.zscore" not in source
        assert "import nestquant.zscore" not in source

    def test_no_logging(self):
        import nestquant.core.contracts.execution_contracts as mod
        source = open(mod.__file__).read()
        assert "import logging" not in source
        assert "logger" not in source

    def test_no_network_calls(self):
        import nestquant.core.contracts.execution_contracts as mod
        source = open(mod.__file__).read()
        assert "requests." not in source
        assert "urllib" not in source
        assert "httpx" not in source
