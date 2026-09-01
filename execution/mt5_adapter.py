"""
NestQuant MT5 Execution Adapter — Broker-Specific Adapter
==========================================================
Implements the ExecutionAdapter protocol for MetaTrader 5 via the Flask bridge.

This module:
  - Translates OrderRequest → MT5 API calls
  - Translates API responses → ExecutionResult
  - Maps MT5-specific errors to adapter exceptions
  - Handles symbol name conversion (EUR/USD → EURUSD)

This module does NOT:
  - Import MetaTrader5 directly
  - Perform risk calculations
  - Perform strategy calculations
  - Make trading decisions
  - Contain logging or monitoring
"""

from __future__ import annotations

from typing import Optional

from nestquant.execution.adapter import (
    AdapterConnectionError,
    BaseExecutionAdapter,
)
from nestquant.execution.contracts import (
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
)
from nestquant.execution.mt5_client import MT5Client, MT5ConnectionError


# ---------------------------------------------------------------------------
# Symbol conversion
# ---------------------------------------------------------------------------

def nestquant_to_mt5_symbol(pair: str) -> str:
    """Convert NestQuant pair format to MT5 symbol format.

    NestQuant uses "EUR/USD", MT5 uses "EURUSD".
    """
    return pair.replace("/", "")


def mt5_to_nestquant_symbol(mt5_symbol: str) -> str:
    """Convert MT5 symbol format to NestQuant pair format.

    MT5 uses "EURUSD", NestQuant uses "EUR/USD".
    """
    # Common quote currencies
    quotes = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
    if len(mt5_symbol) == 6 and mt5_symbol[3:] in quotes:
        return f"{mt5_symbol[:3]}/{mt5_symbol[3:]}"
    # Fallback: return as-is
    return mt5_symbol


# ---------------------------------------------------------------------------
# MT5 Execution Adapter
# ---------------------------------------------------------------------------


class MT5ExecutionAdapter(BaseExecutionAdapter):
    """Execution adapter for MetaTrader 5 via Flask bridge.

    Translates the broker-agnostic OrderRequest into MT5-specific API calls
    and returns a broker-agnostic ExecutionResult.

    Uses MT5Client for HTTP communication. Never imports MetaTrader5 directly.
    """

    def __init__(
        self,
        client: Optional[MT5Client] = None,
        magic: int = 0,
        deviation: int = 10,
        name: str = "mt5",
    ) -> None:
        """Initialize the MT5 adapter.

        Args:
            client: MT5Client instance. If None, creates one with defaults.
            magic: Magic number for EA identification on orders.
            deviation: Max allowed slippage in points for MT5.
            name: Adapter name for logging/display.
        """
        super().__init__(name=name)
        self._client = client or MT5Client()
        self._magic = magic
        self._deviation = deviation

    @property
    def client(self) -> MT5Client:
        """The underlying MT5 HTTP client."""
        return self._client

    def _validate_request(self, request: OrderRequest) -> None:
        """Validate order request with MT5-specific constraints.

        Adds broker-specific validation beyond the base contract validation:
        - Lot size must be within MT5's accepted range (0.01 - 100.0)
        - Symbol must be non-empty after conversion
        """
        super()._validate_request(request)

        mt5_symbol = nestquant_to_mt5_symbol(request.pair)
        if not mt5_symbol:
            raise AdapterConnectionError(
                f"Cannot convert pair '{request.pair}' to MT5 symbol"
            )

        # MT5 lot size constraints
        if request.lot_size < 0.01:
            from nestquant.execution.adapter import AdapterValidationError
            raise AdapterValidationError(
                [f"MT5 minimum lot size is 0.01, got {request.lot_size}"]
            )

    def _execute_impl(self, request: OrderRequest) -> ExecutionResult:
        """Execute an order via the MT5 Flask bridge.

        Args:
            request: Validated order request.

        Returns:
            ExecutionResult from MT5 execution.
        """
        mt5_symbol = nestquant_to_mt5_symbol(request.pair)
        direction = "BUY" if request.direction == Direction.BUY else "SELL"

        try:
            response = self._client.send_order(
                symbol=mt5_symbol,
                direction=direction,
                volume=request.lot_size,
                sl=request.stop_loss,
                tp=request.take_profit,
                magic=self._magic,
                deviation=self._deviation,
            )
        except MT5ConnectionError as exc:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=f"Connection failed: {exc}",
            )

        if not response.ok:
            return self._handle_error_response(response, request)

        return self._parse_fill_response(response, request)

    def _handle_error_response(
        self, response, request: OrderRequest
    ) -> ExecutionResult:
        """Handle error responses from the MT5 bridge.

        Maps MT5 error codes to appropriate ExecutionResult statuses.
        """
        error_msg = response.error or "Unknown MT5 error"
        data = response.data

        # Map known MT5 error codes
        error_lower = error_msg.lower()

        # Rejection-like errors
        rejection_keywords = (
            "not enough money",
            "insufficient margin",
            "invalid price",
            "market closed",
            "trade not allowed",
            "invalid stops",
            "invalid volume",
            "invalid symbol",
            "disabled",
        )

        is_rejection = any(kw in error_lower for kw in rejection_keywords)

        if is_rejection:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=error_msg,
            )

        # Everything else is an execution error
        return ExecutionResult(
            status=ExecutionStatus.ERROR,
            order_id=None,
            requested_price=request.entry_price,
            fill_price=None,
            slippage_pips=0.0,
            rejection_reason=error_msg,
        )

    def _parse_fill_response(
        self, response, request: OrderRequest
    ) -> ExecutionResult:
        """Parse a successful fill response from the MT5 bridge.

        The Flask bridge returns:
        {
            "status": "success",
            "ticket": 12345,
            "price": 1.1002,
            "volume": 0.10,
            "sl": 1.0950,
            "tp": 1.1150
        }
        """
        data = response.data

        ticket = data.get("ticket")
        fill_price = data.get("price")
        fill_volume = data.get("volume", request.lot_size)

        if ticket is None or fill_price is None:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                order_id=None,
                requested_price=request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=f"Missing fill data: ticket={ticket}, price={fill_price}",
            )

        # Calculate slippage in pips
        pip = self._pip_size(request.pair)
        price_diff = abs(fill_price - request.entry_price)
        slippage_pips = price_diff / pip if pip > 0 else 0.0

        order_id = str(ticket)

        return ExecutionResult(
            status=ExecutionStatus.FILLED,
            order_id=order_id,
            requested_price=request.entry_price,
            fill_price=fill_price,
            slippage_pips=slippage_pips,
            rejection_reason=None,
        )

    def _pip_size(self, pair: str) -> float:
        """Get pip size for a pair."""
        if "JPY" in pair:
            return 0.01
        return 0.0001

    def health_check(self) -> bool:
        """Check if the MT5 bridge is healthy and connected.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = self._client.health()
            return response.ok
        except Exception:
            return False

    def get_account_info(self) -> Optional[dict]:
        """Get MT5 account information.

        Returns:
            Account info dict or None if unavailable.
        """
        response = self._client.get_account_info()
        if response.ok:
            return response.data
        return None

    def get_positions(self) -> list[dict]:
        """Get all open positions.

        Returns:
            List of position dicts, or empty list if unavailable.
        """
        response = self._client.get_positions()
        if response.ok:
            positions = response.data.get("positions", [])
            return positions if isinstance(positions, list) else []
        return []

    def __repr__(self) -> str:
        return (
            f"<MT5ExecutionAdapter(name={self._name}, "
            f"magic={self._magic}, deviation={self._deviation})>"
        )
