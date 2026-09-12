"""NestQuant execution module."""

from nestquant.production.execution.adapter import (
    AdapterConnectionError,
    AdapterError,
    AdapterValidationError,
    BaseExecutionAdapter,
    FakeExecutionAdapter,
)
from nestquant.production.execution.base import BaseExecutor, OrderResult
from nestquant.core.contracts.execution_contracts import (
    ContractValidationError,
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
    RiskDecision,
    TradeIntent,
)
from nestquant.production.execution.orchestration import (
    ExecutionAdapter,
    ExecutionCoordinator,
    OrchestrationError,
    RiskEvaluator,
)

__all__ = [
    # Base
    "BaseExecutor",
    "OrderResult",
    # Contracts
    "Direction",
    "TradeIntent",
    "RiskDecision",
    "OrderRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "ContractValidationError",
    # Orchestration
    "RiskEvaluator",
    "ExecutionAdapter",
    "ExecutionCoordinator",
    "OrchestrationError",
    # Adapter boundary
    "AdapterError",
    "AdapterValidationError",
    "AdapterConnectionError",
    "BaseExecutionAdapter",
    "FakeExecutionAdapter",
]
