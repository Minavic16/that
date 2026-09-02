"""
NestQuant MT5 Client — HTTP Transport Layer
=============================================
Thin HTTP client for the MT5 Flask bridge API.

This module handles ONLY:
  - HTTP request/response serialization
  - Connection management
  - Timeout handling
  - Basic retry logic

This module does NOT:
  - Import MetaTrader5
  - Perform risk calculations
  - Perform strategy calculations
  - Make trading decisions
  - Contain logging or monitoring
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:5001"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0


# ---------------------------------------------------------------------------
# MT5 Order Type Constants
# ---------------------------------------------------------------------------
# The Flask bridge requires integer order-type values matching MT5 constants.
# These are NOT imported from MetaTrader5 to keep this module broker-agnostic.

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1

# Direction string → MT5 integer type mapping
# Keys are stored uppercase; lookup is done after .upper()
DIRECTION_TO_MT5_TYPE: dict[str, int] = {
    "BUY": MT5_ORDER_TYPE_BUY,
    "SELL": MT5_ORDER_TYPE_SELL,
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MT5Response:
    """Raw response from the MT5 Flask bridge."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    status_code: int = 0


# ---------------------------------------------------------------------------
# Client exceptions
# ---------------------------------------------------------------------------


class MT5ClientError(Exception):
    """Base exception for MT5 client errors."""


class MT5ConnectionError(MT5ClientError):
    """Cannot reach the Flask bridge."""


class MT5APIError(MT5ClientError):
    """Flask bridge returned an error."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# MT5 Client
# ---------------------------------------------------------------------------


class MT5Client:
    """HTTP client for the MT5 Flask bridge.

    The Flask bridge runs at 127.0.0.1:5001 and exposes:
      - GET  /health              → connection status
      - GET  /get_positions       → open positions (bare list)
      - GET  /last_error          → last MT5 error
      - POST /order               → submit a market order
      - POST /close_position      → close a position (nested payload)
      - POST /close_all_positions → close all positions
      - GET  /get_account         → account info

    This client translates these into typed Python calls.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    @property
    def base_url(self) -> str:
        return self._base_url

    # ------------------------------------------------------------------
    # Core HTTP
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
    ) -> MT5Response:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST).
            path: API path (e.g., "/health").
            data: Optional JSON body for POST requests.

        Returns:
            MT5Response with parsed data or error.
        """
        url = f"{self._base_url}{path}"
        body = json.dumps(data).encode("utf-8") if data else None

        last_error: Optional[Exception] = None

        for attempt in range(1 + self._max_retries):
            try:
                req = Request(
                    url,
                    data=body,
                    method=method,
                    headers={"Content-Type": "application/json"} if body else {},
                )
                with urlopen(req, timeout=self._timeout) as resp:
                    status = resp.status
                    raw = resp.read().decode("utf-8")
                    parsed = json.loads(raw) if raw else {}

                    # Flask bridge returns {"status": "success", ...} or {"status": "error", ...}
                    if status == 200:
                        is_ok = parsed.get("status") != "error"
                        return MT5Response(
                            ok=is_ok,
                            data=parsed,
                            error=parsed.get("error") if not is_ok else None,
                            status_code=status,
                        )
                    else:
                        return MT5Response(
                            ok=False,
                            data=parsed,
                            error=parsed.get("error", f"HTTP {status}"),
                            status_code=status,
                        )

            except HTTPError as exc:
                status_code = exc.code
                try:
                    raw = exc.read().decode("utf-8")
                    parsed = json.loads(raw) if raw else {}
                    error_msg = parsed.get("error", str(exc))
                except Exception:
                    error_msg = str(exc)
                    parsed = {}

                if status_code >= 500 and attempt < self._max_retries:
                    last_error = MT5APIError(error_msg, status_code)
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue

                return MT5Response(
                    ok=False,
                    data=parsed,
                    error=error_msg,
                    status_code=status_code,
                )

            except (URLError, OSError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue

                return MT5Response(
                    ok=False,
                    error=f"Connection failed: {exc}",
                    status_code=0,
                )

        # Should not reach here, but safety net
        return MT5Response(
            ok=False,
            error=f"Failed after {1 + self._max_retries} attempts: {last_error}",
            status_code=0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health(self) -> MT5Response:
        """Check if the MT5 Flask bridge is healthy.

        Returns:
            MT5Response with ok=True if bridge is reachable and MT5 is connected.
        """
        return self._request("GET", "/health")

    def get_positions(self) -> MT5Response:
        """Get all open positions from MT5.

        Returns:
            MT5Response with data containing list of positions.
            Bridge returns bare list when positions exist, or
            {"positions":[]} when empty.
        """
        resp = self._request("GET", "/get_positions")
        if resp.ok and isinstance(resp.data, list):
            return MT5Response(ok=True, data={"positions": resp.data}, status_code=resp.status_code)
        return resp

    def get_account_info(self) -> MT5Response:
        """Get MT5 account information.

        Returns:
            MT5Response with account balance, equity, margin info.
        """
        return self._request("GET", "/get_account")

    def get_last_error(self) -> MT5Response:
        """Get the last error from MT5.

        Returns:
            MT5Response with error info.
        """
        return self._request("GET", "/last_error")

    def send_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        magic: int = 0,
        comment: str = "",
        deviation: int = 10,
        order_type: str = "MARKET",
    ) -> MT5Response:
        """Send a market order to MT5 via the Flask bridge.

        Args:
            symbol: MT5 symbol name (e.g., "EURUSD").
            direction: "BUY" or "SELL".
            volume: Lot size (e.g., 0.01).
            price: Limit price (None for market orders, ignored).
            sl: Stop loss price.
            tp: Take profit price.
            magic: Magic number for EA identification.
            comment: Order comment.
            deviation: Max allowed slippage in points.
            order_type: Ignored (bridge only supports market orders).

        Returns:
            MT5Response with order result.
        """
        # Map direction string to MT5 integer order type
        direction_upper = direction.upper()
        if direction_upper not in DIRECTION_TO_MT5_TYPE:
            return MT5Response(
                ok=False,
                data={},
                error=f"Invalid direction '{direction}'. Must be 'BUY' or 'SELL'.",
                status_code=0,
            )
        mt5_type = DIRECTION_TO_MT5_TYPE[direction_upper]

        payload: dict[str, Any] = {
            "symbol": symbol,
            "type": mt5_type,
            "volume": volume,
            "deviation": deviation,
        }
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        if magic:
            payload["magic"] = magic
        if comment:
            payload["comment"] = comment

        return self._request("POST", "/order", payload)

    def close_position(
        self,
        ticket: int,
        position_type: int,
        symbol: str,
        volume: float,
    ) -> MT5Response:
        """Close a position by ticket number.

        Args:
            ticket: MT5 position ticket number.
            position_type: MT5 position type (0=BUY, 1=SELL).
            symbol: MT5 symbol name (e.g., "EURUSD").
            volume: Lot size of the position.

        Returns:
            MT5Response with close result.
        """
        return self._request("POST", "/close_position", {
            "position": {
                "type": position_type,
                "ticket": ticket,
                "symbol": symbol,
                "volume": volume,
            }
        })

    def close_all_positions(self, symbol: Optional[str] = None) -> MT5Response:
        """Close all positions, optionally filtered by symbol.

        Args:
            symbol: If provided, only close positions for this symbol (ignored by bridge).

        Returns:
            MT5Response with close result.
        """
        payload: dict[str, Any] = {"order_type": "all"}
        return self._request("POST", "/close_all_positions", payload)

    def __repr__(self) -> str:
        return f"<MT5Client(base_url={self._base_url})>"
