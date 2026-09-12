#!/usr/bin/env python3
"""
S7 Live Dry-Run Validation Script (Standalone)
================================================
Controlled first live execution test of the S7 infrastructure.

Safety rules:
- MetaQuotes DEMO account only
- EURUSD only
- Maximum 0.01 lot
- Immediately close after confirming open
- Stop on any unexpected condition
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Minimal MT5Client (inline for standalone execution)
# ---------------------------------------------------------------------------

class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class TradeIntent:
    pair: str
    direction: Direction
    lot_size: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass(frozen=True)
class MT5Response:
    ok: bool
    data: dict[str, Any]
    error: Optional[str] = None
    status_code: int = 0


class MT5Client:
    def __init__(self, base_url: str = "http://127.0.0.1:5001", timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> MT5Response:
        import json as _json
        url = f"{self._base_url}{path}"
        body = _json.dumps(data).encode("utf-8") if data else None
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
                parsed = _json.loads(raw) if raw else {}
                if status == 200:
                    is_ok = parsed.get("status") != "error"
                    return MT5Response(ok=is_ok, data=parsed, status_code=status)
                else:
                    return MT5Response(ok=False, data=parsed, error=parsed.get("error", f"HTTP {status}"), status_code=status)
        except Exception as e:
            return MT5Response(ok=False, data={}, error=str(e), status_code=0)

    def health(self) -> MT5Response:
        return self._request("GET", "/health")

    def get_positions(self) -> MT5Response:
        resp = self._request("GET", "/get_positions")
        if resp.ok and isinstance(resp.data, list):
            return MT5Response(ok=True, data={"positions": resp.data}, status_code=resp.status_code)
        return resp

    def send_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        magic: int = 0,
        comment: str = "",
        deviation: int = 10,
    ) -> MT5Response:
        # Map direction to MT5 integer type
        direction_upper = direction.upper()
        if direction_upper not in ("BUY", "SELL"):
            return MT5Response(ok=False, data={}, error=f"Invalid direction: {direction}", status_code=0)
        mt5_type = 0 if direction_upper == "BUY" else 1

        payload = {
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
        return self._request("POST", "/close_position", {
            "position": {
                "type": position_type,
                "ticket": ticket,
                "symbol": symbol,
                "volume": volume,
            }
        })


def main() -> int:
    print("=" * 60)
    print("S7 LIVE DRY-RUN VALIDATION")
    print("=" * 60)

    # Phase 0: Preflight
    print("\n--- PHASE 0: PREFLIGHT ---")

    client = MT5Client(base_url="http://127.0.0.1:5001", timeout=10.0)

    # Health check
    health = client.health()
    print(f"Health: {health.data}")
    if not health.ok:
        print("FAIL: Bridge not healthy")
        return 1

    mt5_connected = health.data.get("mt5_connected", False)
    mt5_initialized = health.data.get("mt5_initialized", False)
    print(f"MT5 connected: {mt5_connected}, initialized: {mt5_initialized}")
    if not (mt5_connected and mt5_initialized):
        print("FAIL: MT5 not ready")
        return 1

    # Check positions
    positions_resp = client.get_positions()
    positions = positions_resp.data.get("positions", [])
    print(f"Open positions before: {len(positions)}")
    if len(positions) > 0:
        print("WARNING: Existing positions found")
        for p in positions:
            print(f"  - {p.get('symbol')} ticket={p.get('ticket')} vol={p.get('volume')}")

    # Get EURUSD tick
    tick_resp = client._request("GET", "/symbol_info_tick/EURUSD")
    if tick_resp.ok:
        bid = tick_resp.data.get("bid")
        ask = tick_resp.data.get("ask")
        print(f"EURUSD bid={bid}, ask={ask}")
    else:
        print("FAIL: Cannot get EURUSD tick")
        return 1

    # Account info
    print("NOTE: Bridge has no /get_account endpoint")
    print("Configured account_balance: 5,000,000 (default)")
    print("Configured leverage: 100 (default)")

    # Phase 1: Execute
    print("\n--- PHASE 1: EXECUTION ---")

    print(f"Intent: BUY 0.01 EURUSD @ market")

    result = client.send_order(
        symbol="EURUSD",
        direction="BUY",
        volume=0.01,
        deviation=10,
    )
    print(f"Raw response: {result}")

    if not result.ok:
        print(f"FAIL: Order failed - {result.error}")
        return 1

    # Parse response
    data = result.data
    if "result" in data and isinstance(data["result"], dict):
        data = data["result"]

    retcode = data.get("retcode", -1)
    fill_price = data.get("price")
    order_id = data.get("order")

    print(f"Retcode: {retcode}")
    print(f"Order ID: {order_id}")
    print(f"Fill price: {fill_price}")

    if retcode != 10009:
        print(f"FAIL: Unexpected retcode {retcode}")
        return 1

    # Phase 2: Verify position
    print("\n--- PHASE 2: VERIFY POSITION ---")

    time.sleep(1)  # Wait for position to appear

    positions_resp = client.get_positions()
    positions = positions_resp.data.get("positions", [])
    print(f"Open positions after order: {len(positions)}")

    eurusd_positions = [p for p in positions if p.get("symbol") == "EURUSD"]
    print(f"EURUSD positions: {len(eurusd_positions)}")

    if len(eurusd_positions) != 1:
        print(f"FAIL: Expected 1 EURUSD position, got {len(eurusd_positions)}")
        return 1

    position = eurusd_positions[0]
    ticket = position.get("ticket")
    pos_type = position.get("type")
    volume = position.get("volume")
    print(f"Ticket: {ticket}")
    print(f"Type: {pos_type} (0=BUY)")
    print(f"Volume: {volume}")

    if volume != 0.01:
        print(f"FAIL: Expected volume 0.01, got {volume}")
        return 1

    # Phase 3: Close position
    print("\n--- PHASE 3: CLOSE POSITION ---")

    close_result = client.close_position(
        ticket=ticket,
        position_type=pos_type,
        symbol="EURUSD",
        volume=volume,
    )
    print(f"Close result: {close_result}")

    if not close_result.ok:
        print(f"FAIL: Close failed - {close_result.error}")
        return 1

    # Phase 4: Verify cleanup
    print("\n--- PHASE 4: VERIFY CLEANUP ---")

    time.sleep(1)  # Wait for position to disappear

    positions_resp = client.get_positions()
    positions = positions_resp.data.get("positions", [])
    print(f"Open positions after close: {len(positions)}")

    eurusd_positions = [p for p in positions if p.get("symbol") == "EURUSD"]
    print(f"EURUSD positions: {len(eurusd_positions)}")

    if len(eurusd_positions) != 0:
        print("FAIL: EURUSD position still exists")
        return 1

    # Phase 5: Audit trail
    print("\n--- PHASE 5: AUDIT TRAIL ---")
    print("Audit trail not available in standalone mode")

    # Final summary
    print("\n" + "=" * 60)
    print("DRY-RUN COMPLETE")
    print("=" * 60)
    print(f"Order ID: {order_id}")
    print(f"Fill price: {fill_price}")
    print(f"Position opened: YES")
    print(f"Position closed: YES")
    print(f"Cleanup verified: YES")

    if fill_price and ask:
        slippage = abs(fill_price - ask)
        print(f"Slippage: {slippage:.5f}")

    print("\nS7 PASSES FIRST LIVE EXECUTION GATE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
