"""
structured_engine.py — Full Auto Structured Entry Engine for cTrader
====================================================================
Reads signals from signal generator, validates, and executes via cTrader API.

Usage:
    python3 structured_engine.py --dry-run     # Validate signals, no orders
    python3 structured_engine.py --live        # Real trading
    python3 structured_engine.py --status      # Show current status
"""

import asyncio
import contextlib
import glob
import json
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    CTRADER_ACCESS_TOKEN,
    CTRADER_ACCOUNT_ID,
    CTRADER_USE_LIVE,
)
from circuit_breakers import BreakerSuite
from position_sizing import (
    compute_position_size,
    QuoteSnapshot,
    pip_value_per_lot,
    pip_size_for_pair,
)

logger = logging.getLogger("structured_engine")

# ── Strategy Config ───────────────────────────────────────────────────────────
PAIRS = [
    'EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY',
    'USD/JPY', 'AUD/USD', 'NZD/USD', 'EUR/GBP', 'CAD/JPY', 'AUD/CAD',
    'GBP/AUD', 'EUR/AUD', 'NZD/JPY', 'EUR/CAD', 'GBP/CAD', 'AUD/CHF',
    'NZD/CHF', 'CAD/CHF',
]
RISK_PER_ENTRY = 0.020     # 2.00% per entry (4.00% total for 2 entries)
ACCOUNT_SIZE = 2500
RR_TARGET = 2.7
MAX_HOLD_BARS = 50         # 25 hours on 30min
MAX_CONCURRENT_POSITIONS = 40  # portfolio heat cap (40 × 4% = 160% worst-case, but capped by margin)
SESSIONS = {'london': (7, 16), 'new_york': (12, 21)}
SKIP_FRIDAY_AFTER = 20
SKIP_MONDAY_BEFORE = 3

# ── Leverage / Margin ─────────────────────────────────────────────────────────
LEVERAGE = 100                # 1:100 (5ers standard)
MARGIN_SAFETY = 0.5           # Reject if required margin > 50% of available
CONTRACT_SIZE = 100000        # Standard lot = 100k base currency units
MIN_VOLUME = 1000             # cTrader minimum volume in units (0.01 lot)
VOLUME_STEP = 1000            # cTrader volume step (0.01 lot)

# ── File Paths ────────────────────────────────────────────────────────────────
SIGNAL_DIR = "/root"
TRADE_LOG = "/root/logs/structured_trades.jsonl"
STATUS_FILE = "/root/logs/structured_status.json"
ENGINE_LOG = "/root/logs/structured_engine.log"


def is_good_session(ts: datetime) -> bool:
    hour, day = ts.hour, ts.weekday()
    if day == 4 and hour >= SKIP_FRIDAY_AFTER:
        return False
    if day == 0 and hour < SKIP_MONDAY_BEFORE:
        return False
    if day >= 5:
        return False
    for start, end in SESSIONS.values():
        if start <= hour < end:
            return True
    return False


def load_latest_signal() -> dict | None:
    """Load the most recent signal file with actual signals."""
    signal_files = sorted(glob.glob(f"{SIGNAL_DIR}/signals_structured_*.json"))
    for sf in reversed(signal_files):
        try:
            with open(sf, 'r') as f:
                data = json.load(f)
            if data.get('signals'):
                return data
        except Exception:
            continue
    return None


def validate_signal(sig: dict) -> bool:
    """Validate a signal has all required fields."""
    required = ['pair', 'trend', 'entry1', 'sl_price', 'tp_price', 'avg_entry', 'units']
    return all(k in sig for k in required)


class StructuredEngine:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.client = None
        self.running = False
        self.symbol_map = {}
        self.active_positions = {}  # pair -> {positionId, entry, sl, tp, entry_time, ...}
        self.trade_log = []
        self.account_balance = ACCOUNT_SIZE
        self.daily_start_balance = ACCOUNT_SIZE
        self.daily_pnl = 0.0
        self.daily_reset_day = None
        DAILY_LOSS_LIMIT_PCT = 0.05  # 5ers High Stakes: 5% daily loss limit
        self.daily_loss_limit_pct = DAILY_LOSS_LIMIT_PCT
        self.breaker = BreakerSuite(
            dd_expected_pct=2.5,
            dd_drift_max_pct=7.0,
            breaker_overrides={
                'drawdown_pace': {
                    'soft_dd': 6.0,
                    'soft_trades': 15,
                    'hard_dd': 9.0,
                    'hard_trades': 25,
                }
            },
        )
        self.state = {
            'running': False,
            'dry_run': dry_run,
            'balance': ACCOUNT_SIZE,
            'peak': ACCOUNT_SIZE,
            'leverage': LEVERAGE,
            'dd_pct': 0.0,
            'trades_today': 0,
            'signals_processed': 0,
            'open_positions': 0,
            'margin_used': 0.0,
            'margin_available': ACCOUNT_SIZE * LEVERAGE,
        }
        # USD-per-unit map for popular currencies (refreshed periodically)
        self._ccy_snapshot = None
        self._ccy_snapshot_ts = 0.0

    async def start(self):
        global LEVERAGE
        try:
            from ctrader_connector import CTraderClient
        except ImportError:
            # Try importing from .pyc
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    'ctrader_connector',
                    '/root/__pycache__/ctrader_connector.cpython-312.pyc'
                )
                if spec:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    CTraderClient = mod.CTraderClient
                else:
                    raise ImportError("No spec")
            except Exception:
                logger.error("ctrader_connector not found. Running in offline mode.")
                logger.info("Signals will be logged but not executed.")
                await self._offline_loop()
                return

        logger.info("=" * 60)
        logger.info(f"  STRUCTURED ENGINE — dry_run={self.dry_run}")
        logger.info(f"  Strategy: RR={RR_TARGET}, Risk={RISK_PER_ENTRY*100:.2f}%/entry")
        logger.info(f"  Pairs: {', '.join(PAIRS)}")
        logger.info(f"  Account: ${ACCOUNT_SIZE}, Leverage: 1:{LEVERAGE}")
        logger.info(f"  Margin safety: {MARGIN_SAFETY*100:.0f}% of available")
        logger.info("=" * 60)

        # Connect to cTrader
        self.client = CTraderClient(
            access_token=CTRADER_ACCESS_TOKEN,
            account_id=int(CTRADER_ACCOUNT_ID) if CTRADER_ACCOUNT_ID else 0,
            use_live=False,  # Use demo server for paper testing
            auto_reconnect=True,
        )

        max_retries = 10
        for retry in range(max_retries):
            try:
                if not self.client._connected:
                    await self.client.connect()
                if not self.client._authenticated_app:
                    await self.client.authenticate_app()
                accounts = await self.client.get_accounts()
                account_ids = [a.ctidTraderAccountId for a in (accounts or [])]
                if not account_ids:
                    raise Exception("No accounts returned")

                # Find the 5ers account (ID 47697138) or use first available
                target_id = int(CTRADER_ACCOUNT_ID) if CTRADER_ACCOUNT_ID and CTRADER_ACCOUNT_ID != "0" else None
                if target_id and target_id in account_ids:
                    aid = target_id
                elif account_ids:
                    aid = account_ids[0]
                    logger.info(f"Target account not found, using: {aid}")
                else:
                    raise Exception("No valid account found")
                await self.client.authenticate_account(aid)
                self.client.account_id = aid

                info = await self.client.get_trader_info()
                self.account_balance = info.get("balance", ACCOUNT_SIZE)
                self.state['balance'] = self.account_balance
                self.state['peak'] = self.account_balance
                # Capture account-level leverage (info) and override config if present
                acct_lev = info.get('leverage')
                if isinstance(acct_lev, (int, float)) and acct_lev > 0:
                    LEVERAGE = int(acct_lev)
                    logger.info(f"Account leverage: 1:{LEVERAGE}")
                self.state['leverage'] = LEVERAGE
                self.state['currency_snapshot'] = None

                logger.info(f"Connected: account={aid}, balance=${self.account_balance:.2f}, lev=1:{LEVERAGE}")

                # Get symbols
                symbols = await self.client.get_symbols()
                self.symbol_map = {}
                for sid, sdata in (symbols or {}).items():
                    if isinstance(sdata, dict) and 'symbolName' in sdata:
                        name = sdata['symbolName']
                        # Convert "EURUSD" to "EUR/USD"
                        if len(name) == 6 and name.isalpha():
                            pair_name = f"{name[:3]}/{name[3:]}"
                            if pair_name in PAIRS:
                                self.symbol_map[pair_name] = sid
                    elif hasattr(sdata, 'name') and hasattr(sdata, 'id'):
                        name = sdata.name
                        if len(name) == 6 and name.isalpha():
                            pair_name = f"{name[:3]}/{name[3:]}"
                            if pair_name in PAIRS:
                                self.symbol_map[pair_name] = sdata.id

                logger.info(f"Loaded {len(self.symbol_map)} tradeable symbols: {list(self.symbol_map.keys())}")
                break

            except Exception as e:
                logger.error(f"Connection attempt {retry+1}/{max_retries} failed: {e}")
                if retry < max_retries - 1:
                    await asyncio.sleep(2 ** retry)
                else:
                    logger.error("Max retries reached. Exiting.")
                    return

        # Reconcile existing positions
        await self._reconcile_positions()

        self.running = True
        self.state['running'] = True
        logger.info("Main loop starting...")
        await self._main_loop()

    async def _reconcile_positions(self):
        """Check for existing open positions."""
        try:
            positions, _ = await self.client.reconcile()
            for pos in (positions or []):
                pair = None
                for name, sid in self.symbol_map.items():
                    if sid == pos.get('symbolId'):
                        pair = name
                        break
                if pair and pair in PAIRS:
                    # cTrader returns volume in UNITS (1 lot = 100,000 units)
                    vol_units = pos.get('volume', 0)
                    vol_lots = vol_units / CONTRACT_SIZE if vol_units > 100 else vol_units
                    self.active_positions[pair] = {
                        'positionId': pos['positionId'],
                        'entry': pos.get('price', 0),
                        'sl': pos.get('stopLoss', 0),
                        'tp': pos.get('takeProfit', 0),
                        'direction': pos.get('tradeSide', ''),
                        'volume': vol_lots,
                        'entry_time': datetime.now(UTC),
                    }
                    logger.info(f"Existing position: {pair} {pos.get('tradeSide')} @ {pos.get('price')} vol={vol_lots} lots")
            self.state['open_positions'] = len(self.active_positions)
        except Exception as e:
            logger.warning(f"Reconcile failed: {e}")

    async def _main_loop(self):
        """Main loop: check signals, place orders, manage positions."""
        last_signal_file = None

        while self.running:
            try:
                now = datetime.now(UTC)

                # 0. Always update status — even when markets closed
                self._update_status()

                # 1. Check session
                if not is_good_session(now):
                    # Close all positions at session end
                    if self.active_positions:
                        logger.info("Session ending — closing all positions")
                        await self._close_all_positions()
                    await asyncio.sleep(60)
                    continue

                # 2. Check for new signals
                signal_data = load_latest_signal()
                if signal_data and signal_data != last_signal_file:
                    last_signal_file = signal_data
                    await self._process_signals(signal_data)

                # 3. Monitor open positions
                await self._monitor_positions()

                # 4. Sleep 30 seconds before next check
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(10)

    async def _process_signals(self, signal_data: dict):
        """Process signals from the signal generator."""
        signals = signal_data.get('signals', [])
        if not signals:
            return

        # Refresh currency snapshot so sizing uses live conversion rates
        await self._refresh_currency_snapshot()

        for sig in signals:
            pair = sig.get('pair')
            if not pair or not validate_signal(sig):
                continue

            # Skip if already have position in this pair
            if pair in self.active_positions:
                continue

            # Concurrent position cap (portfolio heat limit)
            if len(self.active_positions) >= MAX_CONCURRENT_POSITIONS:
                logger.info(
                    f"Concurrent cap reached ({len(self.active_positions)}/"
                    f"{MAX_CONCURRENT_POSITIONS}) — skipping {pair}"
                )
                break

            # Check daily loss limit
            if not self._check_daily_risk():
                logger.warning("Daily loss limit reached — skipping signals")
                break

            logger.info(f"Processing signal: {pair} {sig['trend']}")
            await self._execute_signal(sig)

    async def _refresh_currency_snapshot(self):
        """Fetch latest spot quotes to build USD-per-unit currency conversion."""
        # Cache for 60s — no need to call cTrader every signal
        if time.time() - self._ccy_snapshot_ts < 60 and self._ccy_snapshot is not None:
            return
        try:
            # Subscribe to required currency pair symbols for spot data
            needed = ['EUR/USD', 'GBP/USD', 'AUD/USD', 'USD/CHF', 'USD/JPY',
                      'USD/CAD', 'NZD/USD']
            symbol_ids = [self.symbol_map[p] for p in needed if p in self.symbol_map]
            if not symbol_ids:
                return
            await self.client.subscribe_spots(symbol_ids=symbol_ids)
            # Give the broker up to 2 seconds to push spot data
            for _ in range(10):
                await asyncio.sleep(0.2)
                spots = getattr(self.client, 'spots', {}) or {}
                if len(spots) >= len(needed) - 1:
                    break

            # Spots are keyed by symbolId and use scaled int encoding.
            # Empirically cTrader scales all FX prices by 1e5 in the spot stream.
            SCALE = 100000.0
            spots = getattr(self.client, 'spots', {}) or {}
            prices = {}  # 'EURUSD' -> float
            for sid, spot in spots.items():
                if isinstance(spot, dict) and 'bid' in spot:
                    prices[self._pair_name_by_symbol_id(sid)] = spot['bid'] / SCALE

            # Build USD-per-unit map for currencies
            usd_value = {'USD': 1.0}
            if 'EURUSD' in prices:
                usd_value['EUR'] = prices['EURUSD']  # 1 EUR = X USD
            if 'GBPUSD' in prices:
                usd_value['GBP'] = prices['GBPUSD']
            if 'AUDUSD' in prices:
                usd_value['AUD'] = prices['AUDUSD']
            if 'USDCHF' in prices:
                usd_value['CHF'] = 1.0 / prices['USDCHF']
            if 'USDJPY' in prices:
                usd_value['JPY'] = 1.0 / prices['USDJPY']
            if 'USDCAD' in prices:
                usd_value['CAD'] = 1.0 / prices['USDCAD']
            if 'NZDUSD' in prices:
                usd_value['NZD'] = prices['NZDUSD']

            self._ccy_snapshot = QuoteSnapshot(usd_value=usd_value)
            self._ccy_snapshot_ts = time.time()
            self.state['currency_snapshot'] = usd_value
            logger.debug(f"Snapshot: {usd_value}")
        except Exception as e:
            logger.warning(f"Spot snapshot failed: {e}, using default")
            # Fall back to last known snapshot, or default module snapshot
            if self._ccy_snapshot is None:
                from position_sizing import DEFAULT_SNAPSHOT
                self._ccy_snapshot = DEFAULT_SNAPSHOT

    def _pair_name_by_symbol_id(self, symbol_id: int) -> str:
        """Reverse-lookup symbolId -> 'EURUSD' (cTrader format)."""
        for pair_name, sid in self.symbol_map.items():
            if sid == symbol_id:
                return pair_name.replace('/', '')
        return ''

    def _used_margin(self) -> float:
        """Estimate margin already used by open positions (USD)."""
        if not self.active_positions or self._ccy_snapshot is None:
            return 0.0
        usd = self._ccy_snapshot.usd_value
        total = 0.0
        for pair, pos in self.active_positions.items():
            base = pair.split('/')[0]
            lot = pos.get('volume', 0)
            usd_per_base = usd.get(base, 1.0)
            notional = lot * 100000 * usd_per_base
            total += notional / LEVERAGE
        return total

    async def _execute_signal(self, sig: dict):
        """Execute a trade signal using leverage-aware position sizing."""
        pair = sig['pair']
        trend = sig['trend']
        avg_entry = sig['avg_entry']
        sl_price = sig['sl_price']
        tp_price = sig['tp_price']

        if pair not in self.symbol_map:
            logger.warning(f"No symbol ID for {pair}")
            return

        symbol_id = self.symbol_map[pair]
        side = "BUY" if trend == "BULLISH" else "SELL"

        # Pip + pip distance for SL/TP order encoding
        pip = pip_size_for_pair(pair)
        sl_distance = abs(avg_entry - sl_price)
        sl_pips = sl_distance / pip
        if sl_pips <= 0:
            logger.warning(f"Invalid SL distance for {pair}")
            return

        # Leverage-aware sizing
        sizing = compute_position_size(
            pair=pair,
            side=side,
            entry_price=avg_entry,
            sl_price=sl_price,
            account_balance_usd=self.account_balance,
            risk_pct=RISK_PER_ENTRY,
            leverage=LEVERAGE,
            margin_safety=MARGIN_SAFETY,
            snap=self._ccy_snapshot,
            lot_step=0.01,
            min_lot=0.01,
            max_lot=10.0,
            existing_margin_used=self._used_margin(),
        )

        if not sizing.ok:
            logger.warning(
                f"Reject {pair} {side}: {sizing.reject_reason} | "
                f"lot={sizing.lot_size} margin=${sizing.required_margin_usd:.2f}/"
                f"{sizing.available_margin_usd:.2f} ({sizing.margin_pct*100:.1f}%)"
            )
            return

        lot_size = sizing.lot_size
        volume = sizing.volume_units
        pip_mult = 1000 if "JPY" in pair else 10

        logger.info(
            f"Order ready: {pair} {side} lot={lot_size} vol={volume} "
            f"SL={sl_price:.5f} TP={tp_price:.5f} | "
            f"risk=${sizing.risk_dollars:.2f} margin=${sizing.required_margin_usd:.2f} "
            f"({sizing.margin_pct*100:.2f}% of avlbl) notional=${sizing.notional_usd:,.0f}"
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would place: {pair} {side} {lot_size} lots @ {avg_entry:.5f}")
            self._log_trade(pair, side, avg_entry, sl_price, tp_price, lot_size, "DRY_RUN")
            return

        try:
            result = await self.client.place_market_order(
                symbol_id=symbol_id,
                trade_side=side,
                volume=volume,
                stop_loss_pips=int(sl_pips),
                take_profit_pips=int(abs(tp_price - avg_entry) / pip),
                label="structured_entry",
                comment=f"SE {pair} RR={RR_TARGET}",
                pip_multiplier=pip_mult,
                fill_timeout=30.0,
            )

            if result is None:
                logger.error(f"Order not filled: {pair} {side}")
                return

            position_id = result.get('positionId')
            entry_price = result.get('entryPrice', avg_entry)

            logger.info(f"Order filled: {pair} {side} posId={position_id} @ {entry_price}")

            self.active_positions[pair] = {
                'positionId': position_id,
                'entry': entry_price,
                'sl': sl_price,
                'tp': tp_price,
                'direction': side,
                'volume': lot_size,
                'entry_time': datetime.now(UTC),
                'margin_used': sizing.required_margin_usd,
                'notional': sizing.notional_usd,
            }
            self.state['open_positions'] = len(self.active_positions)
            self.state['margin_used'] = self._used_margin()
            self.state['signals_processed'] += 1

            self._log_trade(pair, side, entry_price, sl_price, tp_price, lot_size, "FILLED")

        except Exception as e:
            logger.error(f"Order failed {pair}: {e}")

    async def _monitor_positions(self):
        """Monitor open positions for exits (SL/TP via cTrader, max hold via engine)."""
        for pair, pos in list(self.active_positions.items()):
            try:
                if pair not in self.symbol_map:
                    continue

                positions, _ = await self.client.reconcile()
                current_pos = None
                for p in (positions or []):
                    if p.get('positionId') == pos['positionId']:
                        current_pos = p
                        break

                if current_pos is None:
                    # Position was closed (SL/TP hit externally)
                    logger.info(f"Position closed externally: {pair}")
                    self._log_trade(pair, pos['direction'], pos['entry'], pos['sl'], pos['tp'],
                                   pos['volume'], "CLOSED_EXTERNALLY")
                    del self.active_positions[pair]
                    # Refresh balance after external close
                    await self._refresh_balance()
                    continue

                # Check max hold time (25 hours) — engine-managed exit
                elapsed = (datetime.now(UTC) - pos['entry_time']).total_seconds() / 3600
                if elapsed > 25:
                    logger.info(f"Max hold reached for {pair} ({elapsed:.1f}h) — closing")
                    await self._close_position(pair)

            except Exception as e:
                logger.warning(f"Position monitor error for {pair}: {e}")

    async def _close_position(self, pair: str):
        """Close a specific position."""
        if pair not in self.active_positions:
            return

        pos = self.active_positions[pair]

        if self.dry_run:
            logger.info(f"[DRY RUN] Would close: {pair}")
            self._log_trade(pair, pos['direction'], pos['entry'], pos['sl'], pos['tp'],
                           pos['volume'], "DRY_RUN_CLOSE")
            del self.active_positions[pair]
            self.state['open_positions'] = len(self.active_positions)
            return

        try:
            await self.client.close_position(pos['positionId'], fill_timeout=30.0)
            logger.info(f"Position closed: {pair} posId={pos['positionId']}")
            self._log_trade(pair, pos['direction'], pos['entry'], pos['sl'], pos['tp'],
                           pos['volume'], "MANUAL_CLOSE")
            del self.active_positions[pair]
            self.state['open_positions'] = len(self.active_positions)

            # Refresh balance from cTrader after every close
            await self._refresh_balance()

        except Exception as e:
            logger.error(f"Close failed {pair}: {e}")

    async def _refresh_balance(self):
        """Fetch latest account balance from cTrader (critical for daily risk check)."""
        try:
            info = await self.client.get_trader_info()
            bal = info.get("balance", 0)
            if bal > 0:
                self.account_balance = bal
                self.state['balance'] = bal
                logger.info(f"Balance refreshed: ${bal:.2f}")
        except Exception as e:
            logger.warning(f"Balance refresh failed: {e}")

    async def _close_all_positions(self):
        """Close all open positions."""
        for pair in list(self.active_positions.keys()):
            await self._close_position(pair)

    def _check_daily_risk(self) -> bool:
        """Check if daily loss limit is breached (5ers High Stakes: 5%).
        Resets at the start of each new calendar day (UTC)."""
        today = datetime.now(UTC).date()
        if self.daily_reset_day != today:
            self.daily_reset_day = today
            self.daily_start_balance = self.account_balance
            self.daily_pnl = 0.0
            logger.info(f"Daily reset: start_balance=${self.daily_start_balance:.2f}")
        if self.daily_start_balance <= 0:
            return True
        daily_loss_pct = (self.daily_start_balance - self.account_balance) / self.daily_start_balance
        if daily_loss_pct >= self.daily_loss_limit_pct:
            logger.warning(
                f"Daily loss limit reached: {daily_loss_pct*100:.2f}% >= "
                f"{self.daily_loss_limit_pct*100:.1f}% — blocking new entries"
            )
            return False
        return True

    def _log_trade(self, pair, direction, entry, sl, tp, lot, reason):
        """Log a trade to file."""
        trade = {
            'timestamp': datetime.now(UTC).isoformat(),
            'pair': pair,
            'direction': direction,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'lot': lot,
            'reason': reason,
            'dry_run': self.dry_run,
        }
        self.trade_log.append(trade)

        try:
            os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
            with open(TRADE_LOG, 'a') as f:
                f.write(json.dumps(trade) + '\n')
        except Exception as e:
            logger.warning(f"Failed to write trade log: {e}")

    def _update_status(self):
        """Update status file for dashboard."""
        self.state['timestamp'] = datetime.now(UTC).isoformat()
        self.state['open_positions'] = len(self.active_positions)
        self.state['margin_used'] = round(self._used_margin(), 2)
        self.state['margin_available'] = round(
            self.account_balance * LEVERAGE - self.state['margin_used'], 2
        )

        spots = getattr(self.client, 'spots', {}) or {}
        SCALE = 100000
        total_unrealized = 0.0
        positions_data = {}
        for pair, pos in self.active_positions.items():
            symbol_id = self.symbol_map.get(pair)
            current_price = None
            if symbol_id and symbol_id in spots:
                spot = spots[symbol_id]
                if isinstance(spot, dict) and 'bid' in spot:
                    current_price = spot['bid'] / SCALE

            unrealized_pnl = 0.0
            if current_price is not None:
                entry = pos['entry']
                volume = pos.get('volume', 0)
                pip = pip_size_for_pair(pair)
                if pos['direction'] == 'BUY':
                    pnl_pips = (current_price - entry) / pip
                else:
                    pnl_pips = (entry - current_price) / pip
                unrealized_pnl = pnl_pips * volume * pip * 100000
                total_unrealized += unrealized_pnl

            positions_data[pair] = {
                'direction': pos['direction'],
                'entry': pos['entry'],
                'sl': pos['sl'],
                'tp': pos['tp'],
                'entry_time': pos['entry_time'].isoformat(),
                'volume': pos.get('volume', 0),
                'margin_used': round(pos.get('margin_used', 0), 2),
                'notional': round(pos.get('notional', 0), 2),
                'current_price': round(current_price, 5) if current_price else None,
                'unrealized_pnl': round(unrealized_pnl, 2),
            }

        self.state['positions'] = positions_data
        self.state['unrealized_pnl'] = round(total_unrealized, 2)
        self.state['equity'] = round(self.account_balance + total_unrealized, 2)
        self.state['balance'] = round(self.account_balance, 2)

        try:
            os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
            with open(STATUS_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    async def _offline_loop(self):
        """Offline mode: just monitor signals and log what would happen."""
        logger.info("Running in OFFLINE mode — no trades will be executed")
        last_signal_file = None

        while self.running:
            try:
                now = datetime.now(UTC)
                if not is_good_session(now):
                    await asyncio.sleep(60)
                    continue

                signal_data = load_latest_signal()
                if signal_data and signal_data != last_signal_file:
                    last_signal_file = signal_data
                    signals = signal_data.get('signals', [])
                    if signals:
                        for sig in signals:
                            if validate_signal(sig):
                                logger.info(f"[OFFLINE] Would trade: {sig['pair']} {sig['trend']}")
                                self._log_trade(sig['pair'], sig['trend'], sig.get('avg_entry', 0),
                                               sig.get('sl_price', 0), sig.get('tp_price', 0),
                                               0, "OFFLINE_SIGNAL")
                    else:
                        logger.info("[OFFLINE] No signals")

                self._update_status()
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Offline loop error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        """Gracefully stop the engine."""
        self.running = False
        if self.client:
            self.client.stop()
        logger.info("Engine stopped")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Structured Entry Engine")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--live", action="store_true", help="Live trading mode")
    parser.add_argument("--status", action="store_true", help="Show status")
    args = parser.parse_args()

    if args.status:
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
            print(json.dumps(status, indent=2))
        except FileNotFoundError:
            print("No status file found. Engine not running.")
        return

    dry_run = not args.live
    engine = StructuredEngine(dry_run=dry_run)

    # Handle shutdown signals
    def shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Setup logging
    os.makedirs(os.path.dirname(ENGINE_LOG), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(ENGINE_LOG),
        ]
    )

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
