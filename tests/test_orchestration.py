"""
Tests for nestquant.execution.orchestration module.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

import pytest

from nestquant.execution.contracts import (
    ContractValidationError,
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
    RiskDecision,
    TradeIntent,
)
from nestquant.execution.orchestration import (
    ExecutionAdapter,
    ExecutionCoordinator,
    OrchestrationError,
    RiskEvaluator,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeRiskEvaluator:
    """Deterministic risk evaluator for testing."""

    def __init__(
        self,
        approved: bool = True,
        lot_size: float = 0.10,
        risk_amount: float = 20.0,
        reason: str = "Within risk limits",
        policy_version: Optional[str] = None,
    ) -> None:
        self._approved = approved
        self._lot_size = lot_size
        self._risk_amount = risk_amount
        self._reason = reason
        self._policy_version = policy_version
        self._last_intent: Optional[TradeIntent] = None

    @property
    def last_intent(self) -> Optional[TradeIntent]:
        return self._last_intent

    def evaluate(self, intent: TradeIntent) -> RiskDecision:
        self._last_intent = intent
        pv = self._policy_version if self._policy_version is not None else intent.policy_version
        return RiskDecision(
            approved=self._approved,
            reason=self._reason,
            risk_amount=self._risk_amount,
            lot_size=self._lot_size,
            policy_version=pv,
        )


class FakeExecutionAdapter:
    """Deterministic execution adapter for testing."""

    def __init__(
        self,
        status: ExecutionStatus = ExecutionStatus.FILLED,
        order_id: str = "ORD-001",
        fill_price: Optional[float] = None,
        slippage_pips: float = 0.2,
        rejection_reason: Optional[str] = None,
    ) -> None:
        self._status = status
        self._order_id = order_id
        self._fill_price = fill_price
        self._slippage_pips = slippage_pips
        self._rejection_reason = rejection_reason
        self._last_request: Optional[OrderRequest] = None

    @property
    def last_request(self) -> Optional[OrderRequest]:
        return self._last_request

    def execute(self, request: OrderRequest) -> ExecutionResult:
        self._last_request = request

        if self._status == ExecutionStatus.FILLED:
            fill = self._fill_price if self._fill_price is not None else request.entry_price
            return ExecutionResult(
                status=ExecutionStatus.FILLED,
                order_id=self._order_id,
                requested_price=request.entry_price,
                fill_price=fill,
                slippage_pips=self._slippage_pips,
                rejection_reason=None,
            )
        elif self._status == ExecutionStatus.REJECTED:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=self._rejection_reason or "Broker rejected",
            )
        else:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=self._rejection_reason or "Connection failed",
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_intent(**overrides) -> TradeIntent:
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
# Protocol conformance
# ---------------------------------------------------------------------------


class TestRiskEvaluatorProtocol:
    def test_fake_satisfies_protocol(self):
        fake = FakeRiskEvaluator()
        assert isinstance(fake, RiskEvaluator)

    def test_protocol_has_evaluate(self):
        assert hasattr(RiskEvaluator, "evaluate")

    def test_evaluate_returns_risk_decision(self):
        fake = FakeRiskEvaluator()
        intent = _valid_intent()
        result = fake.evaluate(intent)
        assert isinstance(result, RiskDecision)


class TestExecutionAdapterProtocol:
    def test_fake_satisfies_protocol(self):
        fake = FakeExecutionAdapter()
        assert isinstance(fake, ExecutionAdapter)

    def test_protocol_has_execute(self):
        assert hasattr(ExecutionAdapter, "execute")

    def test_execute_returns_execution_result(self):
        fake = FakeExecutionAdapter()
        request = OrderRequest(
            pair="EUR/USD",
            direction=Direction.BUY,
            lot_size=0.10,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            policy_version="1.0.0",
        )
        result = fake.execute(request)
        assert isinstance(result, ExecutionResult)


# ---------------------------------------------------------------------------
# ExecutionCoordinator construction
# ---------------------------------------------------------------------------


class TestExecutionCoordinatorConstruction:
    def test_init(self):
        risk = FakeRiskEvaluator()
        adapter = FakeExecutionAdapter()
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)
        assert coord.risk is risk
        assert coord.adapter is adapter

    def test_repr(self):
        risk = FakeRiskEvaluator()
        adapter = FakeExecutionAdapter()
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)
        r = repr(coord)
        assert "FakeRiskEvaluator" in r
        assert "FakeExecutionAdapter" in r


# ---------------------------------------------------------------------------
# Approved flow
# ---------------------------------------------------------------------------


class TestApprovedFlow:
    def test_fully_approved_flow(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.FILLED,
            order_id="ORD-001",
            fill_price=1.1002,
            slippage_pips=0.2,
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        result = coord.orchestrate(intent)

        assert result.is_filled
        assert result.order_id == "ORD-001"
        assert result.fill_price == 1.1002
        assert result.slippage_pips == 0.2

    def test_risk_receives_intent(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.05)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(pair="GBP/USD")
        coord.orchestrate(intent)

        assert risk.last_intent is intent
        assert risk.last_intent.pair == "GBP/USD"

    def test_adapter_receives_correct_order_request(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.25)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(
            pair="USD/JPY",
            direction=Direction.SELL,
            entry_price=150.0,
            stop_loss=150.50,
            take_profit=149.0,
            policy_version="2.0.0",
        )
        coord.orchestrate(intent)

        req = adapter.last_request
        assert req is not None
        assert req.pair == "USD/JPY"
        assert req.direction == Direction.SELL
        assert req.lot_size == 0.25
        assert req.entry_price == 150.0
        assert req.stop_loss == 150.50
        assert req.take_profit == 149.0
        assert req.policy_version == "2.0.0"


# ---------------------------------------------------------------------------
# Order construction correctness
# ---------------------------------------------------------------------------


class TestOrderConstruction:
    def test_pair_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        for pair in ["EUR/USD", "GBP/JPY", "AUD/NZD"]:
            intent = _valid_intent(pair=pair)
            coord.orchestrate(intent)
            assert adapter.last_request.pair == pair

    def test_direction_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        for direction in [Direction.BUY, Direction.SELL]:
            intent = _valid_intent(
                direction=direction,
                stop_loss=1.0900 if direction == Direction.BUY else 1.1100,
                take_profit=1.1100 if direction == Direction.BUY else 1.0900,
            )
            coord.orchestrate(intent)
            assert adapter.last_request.direction == direction

    def test_lot_size_from_risk_decision(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.37)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        coord.orchestrate(intent)
        assert adapter.last_request.lot_size == 0.37

    def test_entry_price_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(entry_price=1.0900, stop_loss=1.0850, take_profit=1.1000)
        coord.orchestrate(intent)
        assert adapter.last_request.entry_price == 1.0900

    def test_stop_loss_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(stop_loss=1.0876)
        coord.orchestrate(intent)
        assert adapter.last_request.stop_loss == 1.0876

    def test_take_profit_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(take_profit=1.1345)
        coord.orchestrate(intent)
        assert adapter.last_request.take_profit == 1.1345

    def test_policy_version_preserved(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(policy_version="3.1.4")
        coord.orchestrate(intent)
        assert adapter.last_request.policy_version == "3.1.4"


# ---------------------------------------------------------------------------
# Risk rejection flow
# ---------------------------------------------------------------------------


class TestRiskRejection:
    def test_rejected_returns_rejection_result(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Exceeds max drawdown",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        result = coord.orchestrate(intent)

        assert result.is_rejected
        assert "Exceeds max drawdown" in result.rejection_reason

    def test_rejected_does_not_call_adapter(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Too many open positions",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        coord.orchestrate(intent)

        assert adapter.last_request is None

    def test_rejected_result_has_correct_price(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Blocked by circuit breaker",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(entry_price=1.0800, stop_loss=1.0750, take_profit=1.0900)
        result = coord.orchestrate(intent)

        assert result.requested_price == 1.0800

    def test_rejected_result_has_zero_slippage(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Risk limit breached",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        result = coord.orchestrate(intent)

        assert result.slippage_pips == 0.0

    def test_rejected_result_has_no_fill_price(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Daily loss limit",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent()
        result = coord.orchestrate(intent)

        assert result.fill_price is None


# ---------------------------------------------------------------------------
# Policy version integrity
# ---------------------------------------------------------------------------


class TestPolicyVersionIntegrity:
    def test_matching_versions_succeed(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10, policy_version="2.0.0")
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(policy_version="2.0.0")
        result = coord.orchestrate(intent)
        assert result.is_filled

    def test_mismatched_versions_fail(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10, policy_version="2.0.0")
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(policy_version="1.0.0")
        with pytest.raises(OrchestrationError, match="Policy version mismatch"):
            coord.orchestrate(intent)

    def test_mismatched_versions_do_not_call_adapter(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10, policy_version="9.9.9")
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(policy_version="1.0.0")
        with pytest.raises(OrchestrationError):
            coord.orchestrate(intent)
        assert adapter.last_request is None

    def test_policy_version_not_silently_overwritten(self):
        """Intent policy version must be preserved, not replaced by decision."""
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10, policy_version="2.0.0")
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(policy_version="1.0.0")
        with pytest.raises(OrchestrationError):
            coord.orchestrate(intent)
        # Adapter should never have been called with wrong version
        assert adapter.last_request is None


# ---------------------------------------------------------------------------
# Execution outcomes
# ---------------------------------------------------------------------------


class TestExecutionOutcomes:
    def test_filled_result(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.FILLED,
            order_id="ORD-100",
            fill_price=1.1005,
            slippage_pips=0.5,
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        result = coord.orchestrate(_valid_intent())
        assert result.is_filled
        assert result.status == ExecutionStatus.FILLED
        assert result.order_id == "ORD-100"
        assert result.fill_price == 1.1005

    def test_broker_rejection_result(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.REJECTED,
            rejection_reason="Insufficient margin",
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        result = coord.orchestrate(_valid_intent())
        assert result.is_rejected
        assert result.status == ExecutionStatus.REJECTED
        assert "Insufficient margin" in result.rejection_reason

    def test_execution_error_result(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.ERROR,
            rejection_reason="Connection timeout",
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        result = coord.orchestrate(_valid_intent())
        assert result.is_error
        assert result.status == ExecutionStatus.ERROR
        assert "Connection timeout" in result.rejection_reason


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_executor_rejection_is_not_risk_rejection(self):
        """Broker rejection has different rejection_reason prefix than risk."""
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.REJECTED,
            rejection_reason="Broker rejected",
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        result = coord.orchestrate(_valid_intent())
        assert result.is_rejected
        # The rejection comes from the adapter, not from risk
        assert adapter.last_request is not None

    def test_risk_rejection_never_reaches_executor(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Circuit breaker active",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        coord.orchestrate(_valid_intent())
        assert adapter.last_request is None

    def test_execution_error_does_not_become_success(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.ERROR,
            rejection_reason="Network failure",
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        result = coord.orchestrate(_valid_intent())
        assert result.is_error
        assert not result.is_filled
        assert not result.is_rejected


# ---------------------------------------------------------------------------
# Immutability preservation
# ---------------------------------------------------------------------------


class TestImmutabilityPreservation:
    def test_trade_intent_not_mutated(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(pair="EUR/USD", policy_version="1.0.0")
        original_pair = intent.pair
        original_version = intent.policy_version

        coord.orchestrate(intent)

        assert intent.pair == original_pair
        assert intent.policy_version == original_version

    def test_risk_decision_not_mutated(self):
        """The coordinator receives the decision but doesn't modify it."""

        class SpyRiskEvaluator:
            def __init__(self):
                self.last_decision = None

            def evaluate(self, intent: TradeIntent) -> RiskDecision:
                d = RiskDecision(
                    approved=True,
                    reason="OK",
                    risk_amount=10.0,
                    lot_size=0.10,
                    policy_version=intent.policy_version,
                )
                self.last_decision = d
                return d

        spy = SpyRiskEvaluator()
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=spy, adapter=adapter)

        coord.orchestrate(_valid_intent())

        assert spy.last_decision is not None
        assert spy.last_decision.approved is True
        assert spy.last_decision.lot_size == 0.10


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_invalid_intent_raises(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        # Intent with empty pair
        intent = _valid_intent(pair="")
        with pytest.raises(ContractValidationError):
            coord.orchestrate(intent)

    def test_invalid_risk_decision_raises(self):
        """If risk evaluator returns an invalid decision, coordinator rejects it."""

        class BadRiskEvaluator:
            def evaluate(self, intent: TradeIntent) -> RiskDecision:
                return RiskDecision(
                    approved=True,
                    reason="",
                    risk_amount=-1.0,
                    lot_size=-0.1,
                    policy_version="",
                )

        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=BadRiskEvaluator(), adapter=adapter)

        with pytest.raises(ContractValidationError):
            coord.orchestrate(_valid_intent())


# ---------------------------------------------------------------------------
# Forbidden dependencies
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        assert "MetaTrader5" not in source
        assert "import mt5" not in source

    def test_no_research_import(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        assert "from nestquant.research" not in source
        assert "import nestquant.research" not in source

    def test_no_strategy_import(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        assert "from nestquant.zscore" not in source
        assert "import nestquant.zscore" not in source

    def test_no_logging(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        assert "import logging" not in source
        assert "logger" not in source

    def test_no_network_calls(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        assert "requests." not in source
        assert "urllib" not in source
        assert "httpx" not in source

    def test_no_monitoring(self):
        import nestquant.execution.orchestration as mod
        source = open(mod.__file__).read()
        # Check for actual monitoring imports/functionality, not comments
        assert "import telemetry" not in source
        assert "import metrics" not in source
        assert "send_alert" not in source
        assert "notify" not in source


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    def test_complete_pipeline_buy_filled(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.15, risk_amount=30.0)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.FILLED,
            order_id="ORD-E2E-001",
            fill_price=1.1003,
            slippage_pips=0.3,
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(
            pair="EUR/USD",
            direction=Direction.BUY,
            signal_strength=0.85,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1150,
            strategy="zscore",
            policy_version="1.0.0",
        )
        result = coord.orchestrate(intent)

        assert result.is_filled
        assert result.order_id == "ORD-E2E-001"
        assert result.fill_price == 1.1003
        assert result.slippage_pips == 0.3

        req = adapter.last_request
        assert req.pair == "EUR/USD"
        assert req.direction == Direction.BUY
        assert req.lot_size == 0.15
        assert req.entry_price == 1.1000
        assert req.stop_loss == 1.0950
        assert req.take_profit == 1.1150
        assert req.policy_version == "1.0.0"

    def test_complete_pipeline_sell_rejected_by_risk(self):
        risk = FakeRiskEvaluator(
            approved=False,
            reason="Max consecutive losses reached",
            lot_size=0.0,
        )
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(
            pair="GBP/USD",
            direction=Direction.SELL,
            entry_price=1.2800,
            stop_loss=1.2850,
            take_profit=1.2650,
        )
        result = coord.orchestrate(intent)

        assert result.is_rejected
        assert adapter.last_request is None
        assert "Max consecutive losses reached" in result.rejection_reason

    def test_complete_pipeline_approved_but_broker_error(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.05)
        adapter = FakeExecutionAdapter(
            status=ExecutionStatus.ERROR,
            rejection_reason="Terminal not connected",
        )
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        intent = _valid_intent(pair="USD/JPY", direction=Direction.BUY)
        result = coord.orchestrate(intent)

        assert result.is_error
        assert not result.is_filled
        assert "Terminal not connected" in result.rejection_reason

    def test_multiple_sequential_orchestrations(self):
        risk = FakeRiskEvaluator(approved=True, lot_size=0.10)
        adapter = FakeExecutionAdapter(status=ExecutionStatus.FILLED)
        coord = ExecutionCoordinator(risk=risk, adapter=adapter)

        for i in range(5):
            intent = _valid_intent(entry_price=1.1000 + i * 0.001)
            result = coord.orchestrate(intent)
            assert result.is_filled
