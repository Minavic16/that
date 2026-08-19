"""NestQuant execution module."""

from nestquant.execution.adapter import (
    AdapterConnectionError,
    AdapterError,
    AdapterValidationError,
    BaseExecutionAdapter,
    FakeExecutionAdapter,
)
from nestquant.execution.base import BaseExecutor, OrderResult
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
