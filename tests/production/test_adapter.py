"""
Tests for nestquant.execution.adapter module.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nestquant.production.execution.adapter import (
    AdapterConnectionError,
    AdapterError,
    AdapterValidationError,
    BaseExecutionAdapter,
    FakeExecutionAdapter,
)
from nestquant.core.contracts.execution_contracts import (
    ContractValidationError,
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
)
from nestquant.production.execution.orchestration import (
    ExecutionCoordinator,
    RiskEvaluator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_request(**overrides) -> OrderRequest:
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


def _valid_intent(**overrides):
    from nestquant.core.contracts.execution_contracts import TradeIntent
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


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_adapter_error_is_base_exception(self):
        assert issubclass(AdapterError, Exception)

    def test_adapter_validation_error_inherits_adapter_error(self):
        assert issubclass(AdapterValidationError, AdapterError)

    def test_adapter_connection_error_inherits_adapter_error(self):
        assert issubclass(AdapterConnectionError, AdapterError)

    def test_adapter_validation_error_has_errors(self):
        exc = AdapterValidationError(["err1", "err2"])
        assert exc.errors == ["err1", "err2"]
        assert "err1" in str(exc)
        assert "err2" in str(exc)

    def test_adapter_connection_error_has_message(self):
        exc = AdapterConnectionError("broker offline")
        assert "broker offline" in str(exc)

    def test_adapter_connection_error_default_message(self):
        exc = AdapterConnectionError()
        assert "not connected" in str(exc).lower()


# ---------------------------------------------------------------------------
# BaseExecutionAdapter
# ---------------------------------------------------------------------------


class TestBaseExecutionAdapter:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseExecutionAdapter()

    def test_subclass_must_implement_execute_impl(self):
        class IncompleteAdapter(BaseExecutionAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_valid_request_passes_validation(self):
        class OKAdapter(BaseExecutionAdapter):
            def _execute_impl(self, request):
                return ExecutionResult(
                    status=ExecutionStatus.FILLED,
                    order_id="X",
                    requested_price=request.entry_price,
                    fill_price=request.entry_price,
                    slippage_pips=0.0,
                    rejection_reason=None,
                )

        adapter = OKAdapter(name="test")
        result = adapter.execute(_valid_request())
        assert result.is_filled

    def test_invalid_request_raises_adapter_validation_error(self):
        class StrictAdapter(BaseExecutionAdapter):
            def _execute_impl(self, request):
                return ExecutionResult(
                    status=ExecutionStatus.FILLED,
                    order_id="X",
                    requested_price=request.entry_price,
                    fill_price=request.entry_price,
                    slippage_pips=0.0,
                    rejection_reason=None,
                )

        adapter = StrictAdapter()
        bad_request = _valid_request(pair="")
        with pytest.raises(AdapterValidationError) as exc_info:
            adapter.execute(bad_request)
        assert len(exc_info.value.errors) >= 1

    def test_name_property(self):
        class MyAdapter(BaseExecutionAdapter):
            def _execute_impl(self, request):
                pass

        adapter = MyAdapter(name="my-broker")
        assert adapter.name == "my-broker"

    def test_repr(self):
        class MyAdapter(BaseExecutionAdapter):
            def _execute_impl(self, request):
                pass

        adapter = MyAdapter(name="x")
        assert "MyAdapter" in repr(adapter)
        assert "x" in repr(adapter)


# ---------------------------------------------------------------------------
# FakeExecutionAdapter
# ---------------------------------------------------------------------------


class TestFakeExecutionAdapter:
    def test_default_fills(self):
        adapter = FakeExecutionAdapter()
        result = adapter.execute(_valid_request())
        assert result.is_filled
        assert result.order_id == "TEST-001"

    def test_fills_with_default_price(self):
        adapter = FakeExecutionAdapter()
        req = _valid_request(entry_price=1.2345)
        result = adapter.execute(req)
        assert result.fill_price == 1.2345

    def test_fills_with_custom_price(self):
        adapter = FakeExecutionAdapter(fill_price=1.2400)
        req = _valid_request(entry_price=1.2345)
        result = adapter.execute(req)
        assert result.fill_price == 1.2400

    def test_fills_with_slippage(self):
        adapter = FakeExecutionAdapter(slippage_pips=0.5)
        result = adapter.execute(_valid_request())
        assert result.slippage_pips == 0.5

    def test_rejected_result(self):
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.REJECTED,
            rejection_reason="Insufficient margin",
        )
        result = adapter.execute(_valid_request())
        assert result.is_rejected
        assert "Insufficient margin" in result.rejection_reason

    def test_rejected_default_reason(self):
        adapter = FakeExecutionAdapter(status=ExecutionStatus.REJECTED)
        result = adapter.execute(_valid_request())
        assert result.is_rejected
        assert result.rejection_reason is not None

    def test_error_result(self):
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.ERROR,
            rejection_reason="Connection timeout",
        )
        result = adapter.execute(_valid_request())
        assert result.is_error
        assert "Connection timeout" in result.rejection_reason

    def test_error_default_reason(self):
        adapter = FakeExecutionAdapter(status=ExecutionStatus.ERROR)
        result = adapter.execute(_valid_request())
        assert result.is_error
        assert result.rejection_reason is not None

    def test_execution_count(self):
        adapter = FakeExecutionAdapter()
        assert adapter.execution_count == 0
        adapter.execute(_valid_request())
        assert adapter.execution_count == 1
        adapter.execute(_valid_request())
        assert adapter.execution_count == 2

    def test_last_request(self):
        adapter = FakeExecutionAdapter()
        assert adapter.last_request is None
        req = _valid_request(pair="GBP/USD")
        adapter.execute(req)
        assert adapter.last_request is req
        assert adapter.last_request.pair == "GBP/USD"

    def test_satisfies_protocol(self):
        from nestquant.production.execution.orchestration import ExecutionAdapter
        adapter = FakeExecutionAdapter()
        assert isinstance(adapter, ExecutionAdapter)

    def test_satisfies_base_adapter(self):
        adapter = FakeExecutionAdapter()
        assert isinstance(adapter, BaseExecutionAdapter)


# ---------------------------------------------------------------------------
# Adapter validation boundary
# ---------------------------------------------------------------------------


class TestAdapterValidationBoundary:
    def test_empty_pair_rejected(self):
        adapter = FakeExecutionAdapter()
        with pytest.raises(AdapterValidationError):
            adapter.execute(_valid_request(pair=""))

    def test_zero_lot_rejected(self):
        adapter = FakeExecutionAdapter()
        with pytest.raises(AdapterValidationError):
            adapter.execute(_valid_request(lot_size=0))

    def test_negative_entry_rejected(self):
        adapter = FakeExecutionAdapter()
        with pytest.raises(AdapterValidationError):
            adapter.execute(_valid_request(entry_price=-1.0))

    def test_empty_policy_version_rejected(self):
        adapter = FakeExecutionAdapter()
        with pytest.raises(AdapterValidationError):
            adapter.execute(_valid_request(policy_version=""))

    def test_valid_request_accepted(self):
        adapter = FakeExecutionAdapter()
        result = adapter.execute(_valid_request())
        assert result.is_filled

    def test_custom_validation_in_subclass(self):
        """Subclass can add broker-specific validation."""

        class BrokerAdapter(BaseExecutionAdapter):
            MAX_LOT = 1.0

            def _validate_request(self, request):
                super()._validate_request(request)
                if request.lot_size > self.MAX_LOT:
                    raise AdapterValidationError(
                        [f"lot_size {request.lot_size} exceeds broker max {self.MAX_LOT}"]
                    )

            def _execute_impl(self, request):
                return ExecutionResult(
                    status=ExecutionStatus.FILLED,
                    order_id="X",
                    requested_price=request.entry_price,
                    fill_price=request.entry_price,
                    slippage_pips=0.0,
                    rejection_reason=None,
                )

        adapter = BrokerAdapter()
        # Within limit
        result = adapter.execute(_valid_request(lot_size=0.50))
        assert result.is_filled
        # Exceeds limit
        with pytest.raises(AdapterValidationError) as exc_info:
            adapter.execute(_valid_request(lot_size=1.50))
        assert "exceeds broker max" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Coordinator → Adapter integration
# ---------------------------------------------------------------------------


class TestCoordinatorAdapterIntegration:
    def _make_coordinator(self, **adapter_kwargs):
        class ApproveAllRisk:
            def evaluate(self, intent):
                from nestquant.core.contracts.execution_contracts import RiskDecision
                return RiskDecision(
                    approved=True,
                    reason="OK",
                    risk_amount=10.0,
                    lot_size=0.10,
                    policy_version=intent.policy_version,
                )

        adapter = FakeExecutionAdapter(**adapter_kwargs)
        return ExecutionCoordinator(risk=ApproveAllRisk(), adapter=adapter), adapter

    def test_coordinator_calls_adapter(self):
        coord, adapter = self._make_coordinator()
        result = coord.orchestrate(_valid_intent())
        assert result.is_filled
        assert adapter.execution_count == 1

    def test_adapter_receives_correct_request(self):
        coord, adapter = self._make_coordinator()
        intent = _valid_intent(pair="USD/JPY", policy_version="2.0.0")
        coord.orchestrate(intent)
        req = adapter.last_request
        assert req.pair == "USD/JPY"
        assert req.policy_version == "2.0.0"

    def test_broker_rejection_through_coordinator(self):
        coord, adapter = self._make_coordinator(
            status=ExecutionStatus.REJECTED,
            rejection_reason="No liquidity",
        )
        result = coord.orchestrate(_valid_intent())
        assert result.is_rejected
        assert "No liquidity" in result.rejection_reason

    def test_broker_error_through_coordinator(self):
        coord, adapter = self._make_coordinator(
            status=ExecutionStatus.ERROR,
            rejection_reason="Timeout",
        )
        result = coord.orchestrate(_valid_intent())
        assert result.is_error
        assert "Timeout" in result.rejection_reason

    def test_sequential_executions_independent(self):
        coord, adapter = self._make_coordinator()
        for i in range(5):
            result = coord.orchestrate(_valid_intent(entry_price=1.1000 + i * 0.001))
            assert result.is_filled
        assert adapter.execution_count == 5


# ---------------------------------------------------------------------------
# Result propagation without mutation
# ---------------------------------------------------------------------------


class TestResultPropagation:
    def test_result_not_mutated_after_return(self):
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.FILLED,
            order_id="ORD-100",
            fill_price=1.1005,
            slippage_pips=0.3,
        )
        result = adapter.execute(_valid_request())

        # Capture values
        orig_status = result.status
        orig_order_id = result.order_id
        orig_fill = result.fill_price
        orig_slip = result.slippage_pips

        # Execute again
        adapter.execute(_valid_request())

        # Original result unchanged (frozen dataclass)
        assert result.status == orig_status
        assert result.order_id == orig_order_id
        assert result.fill_price == orig_fill
        assert result.slippage_pips == orig_slip


# ---------------------------------------------------------------------------
# No broker-specific objects
# ---------------------------------------------------------------------------


class TestNoBrokerCoupling:
    def test_no_mt5_attributes(self):
        adapter = FakeExecutionAdapter()
        req = _valid_request()
        assert not hasattr(req, "magic_number")
        assert not hasattr(req, "deviation")
        assert not hasattr(req, "comment")
        assert not hasattr(req, "type_filling")

    def test_adapter_returns_contracts_only(self):
        adapter = FakeExecutionAdapter()
        result = adapter.execute(_valid_request())
        assert isinstance(result, ExecutionResult)


# ---------------------------------------------------------------------------
# Forbidden dependencies
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "MetaTrader5" not in source
        assert "import mt5" not in source

    def test_no_research_import(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "from nestquant.research" not in source
        assert "import nestquant.research" not in source

    def test_no_strategy_import(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "from nestquant.zscore" not in source
        assert "import nestquant.zscore" not in source

    def test_no_logging(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "import logging" not in source
        assert "logger" not in source

    def test_no_network_calls(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "requests." not in source
        assert "urllib" not in source
        assert "httpx" not in source

    def test_no_monitoring(self):
        import nestquant.production.execution.adapter as mod
        source = open(mod.__file__).read()
        assert "import telemetry" not in source
        assert "send_alert" not in source
        assert "notify" not in source
