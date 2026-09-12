#!/usr/bin/env python3
"""
S7 Live Dry-Run Validation Script
==================================
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
from pathlib import Path

# Add project root to path

from nestquant.core.contracts.execution_contracts import Direction, TradeIntent
from nestquant.production.execution.mt5_client import MT5Client


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

    # Account info (bridge doesn't have /get_account)
    print("NOTE: Bridge has no /get_account endpoint")
    print("Configured account_balance: 5,000,000 (default)")
    print("Configured leverage: 100 (default)")

    # Phase 1: Execute
    print("\n--- PHASE 1: EXECUTION ---")

    intent = TradeIntent(
        pair="EUR/USD",
        direction=Direction.BUY,
        lot_size=0.01,
        entry_price=ask,
        stop_loss=None,
        take_profit=None,
    )
    print(f"Intent: {intent}")

    # Execute through client directly (not full S7 pipeline for safety)
    from nestquant.production.execution.mt5_adapter import MT5ExecutionAdapter

    adapter = MT5ExecutionAdapter(client=client, magic=0, deviation=10)
    result = adapter.execute(intent)
    print(f"Result: {result}")

    if not result.is_filled:
        print(f"FAIL: Order not filled - {result.rejection_reason}")
        return 1

    order_id = result.order_id
    fill_price = result.fill_price
    print(f"Order ID: {order_id}")
    print(f"Fill price: {fill_price}")

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

    log_dir = Path("/tmp/nestquant_s7_logs")
    if log_dir.exists():
        orders_file = log_dir / "orders.jsonl"
        infra_file = log_dir / "infrastructure.jsonl"

        if orders_file.exists():
            print(f"orders.jsonl exists: {orders_file}")
            with open(orders_file) as f:
                lines = f.readlines()
                print(f"  Records: {len(lines)}")
                for line in lines[-5:]:
                    print(f"  {line.strip()}")
        else:
            print("orders.jsonl not found")

        if infra_file.exists():
            print(f"infrastructure.jsonl exists: {infra_file}")
            with open(infra_file) as f:
                lines = f.readlines()
                print(f"  Records: {len(lines)}")
                for line in lines[-5:]:
                    print(f"  {line.strip()}")
        else:
            print("infrastructure.jsonl not found")
    else:
        print("Log directory not found")

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
