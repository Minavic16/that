"""
NestQuant Wine Flask Execution Adapter — Live Order Execution via REST
======================================================================
Sends real orders to MT5 through the Wine+Flask bridge container.

This adapter replaces the read-only stub when LIVE_MODE is enabled.
It uses the same REST interface as WineFlaskReadOnlyAdapter but adds
order execution endpoints.

CRITICAL: This adapter is NOT used unless:
  1. NESTQUANT_LIVE_MODE=1 is set
  2. The hard guard in safety.py is explicitly bypassed
  3. The user has consciously opted into live execution
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from nestquant.production.execution.adapter import (
    AdapterConnectionError,
    AdapterError,
    BaseExecutionAdapter,
)
from nestquant.core.contracts.execution_contracts import (
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
)

logger = logging.getLogger(__name__)

# MT5 symbol mapping: "EUR/USD" → "EURUSD"
PAIR_TO_SYMBOL = {
    "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY",
    "USD/CHF": "USDCHF", "USD/CAD": "USDCAD", "AUD/USD": "AUDUSD",
    "NZD/USD": "NZDUSD", "EUR/GBP": "EURGBP", "EUR/JPY": "EURJPY",
    "EUR/CHF": "EURCHF", "EUR/CAD": "EURCAD", "EUR/AUD": "EURAUD",
    "EUR/NZD": "EURNZD", "GBP/JPY": "GBPJPY", "GBP/CHF": "GBPCHF",
    "GBP/CAD": "GBPCAD", "GBP/AUD": "GBPAUD", "GBP/NZD": "GBPNZD",
    "CHF/JPY": "CHFJPY", "CAD/JPY": "CADJPY",
    "AUD/JPY": "AUDJPY", "NZD/JPY": "NZDJPY",
    "AUD/CAD": "AUDCAD", "AUD/CHF": "AUDCHF", "AUD/NZD": "AUDNZD",
    "NZD/CAD": "NZDCAD", "NZD/CHF": "NZDCHF", "CAD/CHF": "CADCHF",
}

SYMBOL_TO_PAIR = {v: k for k, v in PAIR_TO_SYMBOL.items()}


def _pair_to_mt5(pair: str) -> str:
    return PAIR_TO_SYMBOL.get(pair, pair.replace("/", ""))


class WineFlaskExecutionAdapter(BaseExecutionAdapter):
    """Live execution adapter that sends orders through the Wine+Flask MT5 bridge.

    Uses REST API at the configured base URL (default: http://127.0.0.1:5001).
    All order operations are logged for audit trail.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5001",
        timeout: float = 10.0,
        magic: int = 0,
        deviation: int = 20,
    ) -> None:
        super().__init__(name="wine-flask-execution")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._magic = magic
        self._deviation = deviation
        self._connected = False

    def connect(self) -> bool:
        try:
            r = requests.get(f"{self._base_url}/health", timeout=5)
            data = r.json()
            self._connected = data.get("mt5_connected", False)
            return self._connected
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self._base_url}{endpoint}"
        try:
            r = requests.post(url, json=payload, timeout=self._timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            raise AdapterConnectionError(f"Cannot reach {url}")
        except Exception as e:
            raise AdapterError(f"POST {endpoint} failed: {e}")

    def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        url = f"{self._base_url}{endpoint}"
        try:
            r = requests.get(url, params=params, timeout=self._timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            raise AdapterConnectionError(f"Cannot reach {url}")
        except Exception as e:
            raise AdapterError(f"GET {endpoint} failed: {e}")

    def _execute_impl(self, request: OrderRequest) -> ExecutionResult:
        """Send a market order through the MT5 bridge."""
        symbol = _pair_to_mt5(request.pair)
        direction_str = request.direction.value  # "BUY" or "SELL"

        # Get current tick for price reference
        try:
            tick = self._get(f"/symbol_info_tick/{symbol}")
            entry_price = tick.get("ask") if direction_str == "BUY" else tick.get("bid")
        except Exception:
            entry_price = request.entry_price

        payload = {
            "symbol": symbol,
            "volume": request.lot_size,
            "type": direction_str,
            "sl": round(request.stop_loss, request.pair.count("/") and 5 or 3),
            "tp": round(request.take_profit, request.pair.count("/") and 5 or 3),
            "deviation": self._deviation,
            "magic": self._magic,
            "comment": f"NQ-{request.policy_version}",
        }

        logger.info(f"EXECUTING: {direction_str} {request.pair} {request.lot_size} "
                     f"SL={request.stop_loss:.5f} TP={request.take_profit:.5f}")

        result = self._post("/order", payload)

        # Parse MT5 result
        retcode = result.get("retcode", -1)
        if retcode == 10009:  # TRADE_RETCODE_DONE
            fill_price = result.get("price", entry_price)
            slippage = abs(fill_price - entry_price) if entry_price else 0.0
            # Convert slippage to pips
            if "JPY" in symbol:
                slippage_pips = slippage * 100
            else:
                slippage_pips = slippage * 10000

            logger.info(f"FILLED: {request.pair} @ {fill_price:.5f} "
                        f"slippage={slippage_pips:.1f}pips "
                        f"order={result.get('order', 'N/A')}")

            return ExecutionResult(
                status=ExecutionStatus.FILLED,
                order_id=str(result.get("order", "")),
                requested_price=entry_price or request.entry_price,
                fill_price=fill_price,
                slippage_pips=slippage_pips,
                rejection_reason=None,
            )
        else:
            comment = result.get("comment", f"MT5 error code {retcode}")
            logger.warning(f"REJECTED: {request.pair} retcode={retcode} {comment}")
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                order_id=None,
                requested_price=entry_price or request.entry_price,
                fill_price=None,
                slippage_pips=0.0,
                rejection_reason=f"MT5 retcode {retcode}: {comment}",
            )

    def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> dict:
        """Modify SL/TP for an open position."""
        payload = {"position": ticket}
        if sl is not None:
            payload["sl"] = round(sl, 5)
        if tp is not None:
            payload["tp"] = round(tp, 5)

        logger.info(f"MODIFY: ticket={ticket} SL={sl} TP={tp}")
        result = self._post("/modify_sl_tp", payload)
        retcode = result.get("retcode", -1)
        if retcode == 10009:
            logger.info(f"MODIFIED: ticket={ticket} OK")
        else:
            logger.warning(f"MODIFY FAILED: ticket={ticket} retcode={retcode}")
        return result

    def close_position(self, ticket: int, symbol: str, volume: float, direction: int) -> dict:
        """Close a specific position."""
        payload = {
            "position": {
                "ticket": ticket,
                "symbol": _pair_to_mt5(symbol),
                "volume": volume,
                "type": direction,  # 0=BUY, 1=SELL
            }
        }
        logger.info(f"CLOSE: ticket={ticket} {symbol} vol={volume}")
        result = self._post("/close_position", payload)
        return result

    def close_all_positions(self, magic: int | None = None) -> list:
        """Close all open positions, optionally filtered by magic number."""
        payload: dict = {"order_type": "all"}
        if magic is not None:
            payload["magic"] = magic
        logger.info(f"CLOSE ALL: magic={magic}")
        return self._post("/close_all_positions", payload)

    def get_positions(self, magic: int | None = None) -> list:
        """Get all open positions."""
        params = {}
        if magic is not None:
            params["magic"] = magic
        return self._get("/get_positions", params)

    def get_positions_total(self) -> int:
        """Get total number of open positions."""
        result = self._get("/positions_total")
        return result.get("total", 0)

    def get_account_info(self) -> dict:
        """Get account balance, equity, margin info."""
        # Use symbol_info_tick as a proxy — real account info needs a new endpoint
        return {"balance": 0, "equity": 0, "margin": 0}
