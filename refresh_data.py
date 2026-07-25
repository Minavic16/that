"""
refresh_data.py — Fetch fresh M30/H1 bars from cTrader for all 20 pairs.
Updates pickle files so signal generator has live data.

Usage:
    python3 refresh_data.py            # Fetch 1000 bars per pair
    python3 refresh_data.py --count 500 # Fetch 500 bars per pair
"""

import asyncio
import os
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID

PAIRS = [
    'EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY',
    'USD/JPY', 'AUD/USD', 'NZD/USD', 'EUR/GBP', 'CAD/JPY', 'AUD/CAD',
    'GBP/AUD', 'EUR/AUD', 'NZD/JPY', 'EUR/CAD', 'GBP/CAD', 'AUD/CHF',
    'NZD/CHF', 'CAD/CHF',
]

# cTrader ProtoOATrendbarPeriod values
M30 = 8
H1 = 9

DATA_DIR = Path("/root/data")


async def refresh_all_pairs(count=1000, period=H1):
    """Fetch trendbars for all pairs and update pickle files."""
    try:
        from ctrader_connector import CTraderClient
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'ctrader_connector',
            '/root/__pycache__/ctrader_connector.cpython-312.pyc'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        CTraderClient = mod.CTraderClient

    client = CTraderClient(
        access_token=CTRADER_ACCESS_TOKEN,
        account_id=int(CTRADER_ACCOUNT_ID) if CTRADER_ACCOUNT_ID else 0,
        use_live=False,
        auto_reconnect=True,
    )

    print("Connecting to cTrader...")
    await client.connect()
    await client.authenticate_app()

    accounts = await client.get_accounts()
    account_ids = [a.ctidTraderAccountId for a in (accounts or [])]
    if not account_ids:
        print("ERROR: No accounts found")
        return

    target_id = int(CTRADER_ACCOUNT_ID) if CTRADER_ACCOUNT_ID and CTRADER_ACCOUNT_ID != "0" else account_ids[0]
    await client.authenticate_account(target_id)
    client.account_id = target_id
    print(f"Authenticated: account={target_id}")

    # Get symbols
    symbols = await client.get_symbols()
    symbol_map = {}
    for sid, sdata in (symbols or {}).items():
        if isinstance(sdata, dict) and 'symbolName' in sdata:
            name = sdata['symbolName']
            if len(name) == 6 and name.isalpha():
                pair_name = f"{name[:3]}/{name[3:]}"
                if pair_name in PAIRS:
                    symbol_map[pair_name] = sid
        elif hasattr(sdata, 'name') and hasattr(sdata, 'id'):
            name = sdata.name
            if len(name) == 6 and name.isalpha():
                pair_name = f"{name[:3]}/{name[3:]}"
                if pair_name in PAIRS:
                    symbol_map[pair_name] = sdata.id

    print(f"Found {len(symbol_map)} symbols: {list(symbol_map.keys())}")

    SCALE = 100000.0
    updated = 0

    for pair in PAIRS:
        if pair not in symbol_map:
            print(f"  SKIP {pair}: no symbol ID")
            continue

        sid = symbol_map[pair]
        print(f"  Fetching {pair} (id={sid})...")

        try:
            bars = await client.get_trendbars(
                symbol_id=sid,
                period=period,
                count=count,
            )
        except Exception as e:
            print(f"  ERROR {pair}: {e}")
            continue

        if not bars:
            print(f"  NO DATA for {pair}")
            continue

        # Convert to DataFrame
        rows = []
        for b in bars:
            ts = b.get('timestamp', 0)
            if ts > 1e12:
                ts = ts / 1000.0
            rows.append({
                'timestamp': pd.Timestamp(ts, unit='s', tz='UTC'),
                'open': b.get('open', 0) / SCALE,
                'high': b.get('high', 0) / SCALE,
                'low': b.get('low', 0) / SCALE,
                'close': b.get('close', 0) / SCALE,
                'volume': b.get('volume', 0),
            })

        df = pd.DataFrame(rows)
        df = df.set_index('timestamp').sort_index()
        df = df[~df.index.duplicated(keep='last')]

        # Load existing pickle and merge
        pk = pair.replace("/", "_")
        pkl_path = DATA_DIR / f"{pk}.pkl"

        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                existing = pickle.load(f)

            if pair in existing:
                old_df = existing[pair]
                # Merge: append new bars, keep old ones
                combined = pd.concat([old_df, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                existing[pair] = combined
                print(f"  UPDATED {pair}: {len(old_df)} -> {len(combined)} bars (last={combined.index[-1]})")
            else:
                existing[pair] = df
                print(f"  ADDED {pair}: {len(df)} bars")
        else:
            existing = {pair: df}
            print(f"  NEW {pair}: {len(df)} bars")

        with open(pkl_path, 'wb') as f:
            pickle.dump(existing, f)

        updated += 1
        await asyncio.sleep(0.2)  # Rate limit

    print(f"\nDone: {updated}/{len(PAIRS)} pairs updated")
    await client.disconnect()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--period", type=int, default=H1, help="8=M30, 9=H1")
    args = parser.parse_args()
    asyncio.run(refresh_all_pairs(count=args.count, period=args.period))
