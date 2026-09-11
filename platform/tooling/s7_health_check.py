#!/usr/bin/env python3
"""
NestQuant S7 — Health Check Script
====================================
CLI tool to check MT5 bridge health.

Usage:
    python scripts/s7_health_check.py
    python scripts/s7_health_check.py --json
"""

from __future__ import annotations

import argparse
import json
import sys

from execution.mt5_client import MT5Client
from execution.mt5_adapter import MT5ExecutionAdapter
from execution.health_monitor import HealthMonitor


def main() -> int:
    parser = argparse.ArgumentParser(description="Check MT5 bridge health")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--url", default="http://127.0.0.1:5001", help="MT5 bridge URL")
    args = parser.parse_args()

    client = MT5Client(base_url=args.url)
    monitor = HealthMonitor(client=client)
    status = monitor.check()

    if args.json:
        print(json.dumps(status.to_dict(), indent=2))
    else:
        if status.is_connected:
            print(f"OK: MT5 connected (checks={status.total_checks})")
        else:
            print(f"FAIL: MT5 disconnected (failures={status.consecutive_failures})")
            if status.last_error:
                print(f"  Error: {status.last_error}")

    return 0 if status.is_connected else 1


if __name__ == "__main__":
    sys.exit(main())
