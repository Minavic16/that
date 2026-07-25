"""
Live Engine — MR + TF + Correlation Filter
Exact match to test_combined_corr.py backtest logic.

Regimes:
  MR: Price near 4H EMA200 → session close exit
  TF: Price far from 4H EMA200 → trailing stop exit

Risk management:
  - Correlation filter (skip if corr > 0.75 with open position)
  - Currency overlap filter (max 2 per currency)
  - Daily loss limit (5%)
  - Circuit breakers
"""
import asyncio
import json
import logging
import time
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from ctrader_connector_new import CTraderConnector, OrderResult
import position_sizing as ps

logger = logging.getLogger(__name__)

# =================== STRATEGY PARAMETERS (EXACT MATCH TO BACKTEST) ===================
PAIRS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'NZD/USD',
         'EUR/GBP', 'EUR/CHF', 'EUR/JPY', 'AUD/JPY', 'EUR/AUD', 'AUD/CAD']

DEFAULT_USD = {'USD': 1.0, 'EUR': 1.08, 'GBP': 1.26, 'JPY': 0.0067,
               'CHF': 0.88, 'AUD': 0.65, 'CAD': 0.74, 'NZD': 0.60}
SNAP = ps.QuoteSnapshot(usd_value=DEFAULT_USD)

COMMISSION = 3.50
LEV = 100
SESSIONS = {'london': (7, 16), 'new_york': (12, 21)}
SKIP_FRI = 20
SKIP_MON = 3
SPREAD = {
    'EUR/USD': 0.8, 'GBP/USD': 1.0, 'USD/JPY': 1.0, 'USD/CHF': 1.2,
    'AUD/USD': 0.9, 'NZD/USD': 1.2, 'EUR/GBP': 1.2, 'EUR/CHF': 1.5,
    'EUR/JPY': 2.0, 'AUD/JPY': 2.0, 'EUR/AUD': 2.0, 'AUD/CAD': 2.0
}

# MR params
MR_RISK = 0.035
MR_RR = 2.2

# TF params
TF_RISK = 0.022
BREAKOUT_ZONE = 0.005
TRAIL_ATR_MULT = 2.5
TF_MAX_HOLD = 100
TF_MIN_HOLD = 8

# Correlation filter
CORR_THRESHOLD = 0.75
MAX_SAME_CURRENCY = 2

# Session filter
SESSION_CLOSE_HOUR = 17  # UTC


def igs(ts):
    """In-session check."""
    h, d = ts.hour, ts.weekday()
    if d == 4 and h >= SKIP_FRI:
        return False
    if d == 0 and h < SKIP_MON:
        return False
    if d >= 5:
        return False
    for s, (s2, e) in SESSIONS.items():
        if s2 <= h < e:
            return True
    return False


def get_currencies(pair):
    """Extract base and quote currencies."""
    base, quote = pair.split('/')
    return base, quote


def check_currency_overlap(open_positions, new_pair):
    """Check if new pair shares too many currencies with open positions."""
    new_base, new_quote = get_currencies(new_pair)
    currency_count = {}
    for pos in open_positions:
        b, q = get_currencies(pos['pair'])
        currency_count[b] = currency_count.get(b, 0) + 1
        currency_count[q] = currency_count.get(q, 0) + 1
    if currency_count.get(new_base, 0) >= MAX_SAME_CURRENCY:
        return True
    if currency_count.get(new_quote, 0) >= MAX_SAME_CURRENCY:
        return True
    return False


@dataclass
class OpenPosition:
    pair: str
    trend: int  # 1=long, -1=short
    entry: float
    sl: float
    tp: float
    lot: float
    bar: int
    pip: float
    pv: float
    spread: float
    regime: str  # 'mr' or 'tf'
    ctrader_ticket: str = ""
    entry_time: datetime = None


class LiveEngine:
    """
    Live trading engine matching backtest exactly.
    Uses 4H EMA200 for regime detection, same entry/exit logic.
    """

    def __init__(self, connector: CTraderConnector, initial_balance: float = 2500.0):
        self.connector = connector
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.peak = initial_balance
        self.open_positions: List[OpenPosition] = []
        self.trade_log = []
        self.daily_pnl = 0.0
        self.current_date = None

        # Indicator caches (precomputed)
        self._indicators = {}
        self._corr_matrix = None
        self._status_file = '/root/logs/live_engine_status.json'

    async def start(self):
        """Start the live engine."""
        logger.info("Starting live engine...")

        # Connect
        if not await self.connector.connect():
            logger.error("Failed to connect to cTrader")
            return False

        # Load indicators
        await self._load_indicators()

        # Compute correlation matrix
        await self._compute_correlation_matrix()

        # Reconcile open positions from server
        self._reconcile_positions()

        logger.info("Live engine started")
        return True

    def _reconcile_positions(self):
        """Load open positions from the connector's reconciled state."""
        server_positions = self.connector.get_positions()
        for sp in server_positions:
            sym_name = None
            for name, sid in self.connector._symbol_names.items():
                if sid == sp.tradeData.symbolId:
                    sym_name = name
                    break
            if not sym_name:
                continue
            digits = self.connector._symbol_digits.get(sp.tradeData.symbolId, 5)
            scale = 10 ** digits
            sl_val = getattr(sp, 'stopLoss', 0)
            tp_val = getattr(sp, 'takeProfit', 0)
            pos = OpenPosition(
                pair=sym_name,
                ctrader_ticket=str(sp.positionId),
                trend=1 if sp.tradeData.tradeSide == 1 else -1,
                entry=sp.price,
                sl=sl_val if sl_val else 0,
                tp=tp_val if tp_val else 0,
                lot=sp.tradeData.volume / 10000000,
                bar=0,
                pip=ps.pip_size_for_pair(sym_name),
                pv=ps.pip_value_per_lot(sym_name, SNAP),
                spread=SPREAD.get(sym_name, 2.0),
                regime='mr',
                entry_time=datetime.now(timezone.utc),
            )
            self.open_positions.append(pos)
            logger.info(f"Reconciled position: {sym_name} {'LONG' if pos.trend==1 else 'SHORT'} @ {pos.entry}")

    async def _load_indicators(self):
        """Load precomputed indicators from data files."""
        import os

        for pair in PAIRS:
            pk = pair.replace('/', '_')
            fpath = os.path.join('/root/data', f'{pk}.pkl')
            if not os.path.exists(fpath):
                logger.warning(f"No data file for {pair}")
                continue

            try:
                with open(fpath, 'rb') as f:
                    raw = pickle.load(f)
                await asyncio.sleep(0)  # yield to event loop for heartbeats

                df = raw.get(pair)
                if df is None:
                    continue

                idx = pd.to_datetime(df.index)
                idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
                df.index = idx

                # Use last 2 years of data
                two_years_ago = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=730)
                df = df[df.index >= two_years_ago]

                # Resample to 30m
                if len(df) > 100000:
                    d30 = df[['open', 'high', 'low', 'close', 'volume']].resample('30min').agg({
                        'open': 'first', 'high': 'max', 'low': 'min',
                        'close': 'last', 'volume': 'sum'
                    }).dropna(subset=['close'])
                else:
                    d30 = df[['open', 'high', 'low', 'close', 'volume']].dropna(subset=['close'])

                # 4H data for EMA
                d4h = df[['open', 'high', 'low', 'close']].resample('4h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
                }).dropna(subset=['close'])

                e200 = d4h['close'].ewm(span=200, adjust=False).mean()
                e50 = d4h['close'].ewm(span=50, adjust=False).mean()

                # ATR
                tr1 = d4h['high'] - d4h['low']
                tr2 = abs(d4h['high'] - d4h['close'].shift(1))
                tr3 = abs(d4h['low'] - d4h['close'].shift(1))
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr_4h = tr.rolling(14).mean()

                pip = ps.pip_size_for_pair(pair)
                pv = ps.pip_value_per_lot(pair, SNAP)

                self._indicators[pair] = {
                    'c': d30['close'].values,
                    'h': d30['high'].values,
                    'lo': d30['low'].values,
                    'o': d30['open'].values,
                    'ts': d30.index,
                    'n': len(d30),
                    'e200': e200.reindex(d30.index, method='ffill').values,
                    'e50': e50.reindex(d30.index, method='ffill').values,
                    'atr': atr_4h.reindex(d30.index, method='ffill').values,
                    'pip': pip,
                    'pv': pv,
                    'spread': SPREAD.get(pair, 2.0),
                }

                logger.info(f"Loaded indicators for {pair}: {len(d30)} bars")

            except Exception as e:
                logger.error(f"Error loading indicators for {pair}: {e}")

    async def _compute_correlation_matrix(self):
        """Compute static correlation matrix from loaded data."""
        closes = {}
        for pair in PAIRS:
            if pair in self._indicators:
                closes[pair] = pd.Series(
                    self._indicators[pair]['c'],
                    index=self._indicators[pair]['ts']
                )
            await asyncio.sleep(0)  # yield to event loop

        if closes:
            price_df = pd.DataFrame(closes)
            returns = price_df.pct_change().dropna()
            self._corr_matrix = returns.corr()
            logger.info("Correlation matrix computed")

    def _get_latest_indicator(self, pair: str, indicator: str):
        """Get the latest value of an indicator."""
        if pair not in self._indicators:
            return None
        ind = self._indicators[pair]
        if ind['n'] == 0:
            return None
        return getattr(ind, indicator, None)

    def _check_entry(self, pair: str) -> Optional[Dict]:
        """
        Check if we should enter a trade.
        Returns entry details or None.
        Exact logic from backtest.
        """
        if pair not in self._indicators:
            return None

        ind = self._indicators[pair]
        i = ind['n'] - 1  # Latest bar

        if i < 50:
            return None

        c_val = ind['c'][i]
        ev = ind['e200'][i]
        e5 = ind['e50'][i]
        cur_atr = ind['atr'][i]

        if np.isnan(ev) or np.isnan(e5):
            return None

        pip = ind['pip']
        dist_from_ema = (c_val - ev) / ev

        # Correlation check
        active_pairs = [pos.pair for pos in self.open_positions]
        if active_pairs:
            for open_pair in active_pairs:
                if self._corr_matrix is not None:
                    if pair in self._corr_matrix.columns and open_pair in self._corr_matrix.columns:
                        corr_val = self._corr_matrix.loc[pair, open_pair]
                        if not np.isnan(corr_val) and abs(corr_val) > CORR_THRESHOLD:
                            return None

        # Currency overlap check
        if check_currency_overlap([{'pair': p.pair} for p in self.open_positions], pair):
            return None

        # MR REGIME
        if abs(dist_from_ema) < BREAKOUT_ZONE:
            tr = 1 if c_val > ev else -1
            if tr == 1 and c_val < e5 * 0.995:
                return None
            if tr == -1 and c_val > e5 * 1.005:
                return None
            if tr == 1:
                if max(ind['h'][max(0, i-20):i]) <= c_val * 1.002:
                    return None
            else:
                if min(ind['lo'][max(0, i-20):i]) >= c_val * 0.998:
                    return None

            sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
            sl_dist = abs(c_val - sl)
            if sl_dist < 2 * pip:
                return None
            tp = c_val + sl_dist * MR_RR if tr == 1 else c_val - sl_dist * MR_RR

            return {
                'pair': pair, 'trend': tr, 'entry': c_val,
                'sl': sl, 'tp': tp, 'regime': 'mr',
                'risk_pct': MR_RISK, 'pip': pip, 'pv': ind['pv']
            }

        # TF REGIME: LONG
        elif dist_from_ema > BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr > 0:
            if c_val <= e5:
                return None
            recent_high = max(ind['h'][max(0, i-20):i])
            if c_val <= recent_high * 1.002:
                return None

            entry_fill = c_val
            sl = entry_fill - TRAIL_ATR_MULT * cur_atr
            tp = entry_fill + 2.5 * TRAIL_ATR_MULT * cur_atr
            sl_dist = abs(entry_fill - sl)
            if sl_dist < 2 * pip:
                return None

            return {
                'pair': pair, 'trend': 1, 'entry': entry_fill,
                'sl': sl, 'tp': tp, 'regime': 'tf',
                'risk_pct': TF_RISK, 'pip': pip, 'pv': ind['pv']
            }

        # TF REGIME: SHORT
        elif dist_from_ema < -BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr > 0:
            if c_val >= e5:
                return None
            recent_low = min(ind['lo'][max(0, i-20):i])
            if c_val >= recent_low * 0.998:
                return None

            entry_fill = c_val
            sl = entry_fill + TRAIL_ATR_MULT * cur_atr
            tp = entry_fill - 2.5 * TRAIL_ATR_MULT * cur_atr
            sl_dist = abs(sl - entry_fill)
            if sl_dist < 2 * pip:
                return None

            return {
                'pair': pair, 'trend': -1, 'entry': entry_fill,
                'sl': sl, 'tp': tp, 'regime': 'tf',
                'risk_pct': TF_RISK, 'pip': pip, 'pv': ind['pv']
            }

        return None

    def _check_exit(self, pos: OpenPosition, current_price: float) -> Optional[str]:
        """
        Check if we should exit a position.
        Returns exit reason or None.
        """
        # Session close exit (MR only)
        now = datetime.now(timezone.utc)
        if pos.regime == 'mr' and now.hour == SESSION_CLOSE_HOUR:
            return 'session_close'

        # Stop loss
        if pos.trend == 1 and current_price <= pos.sl:
            return 'stop_loss'
        if pos.trend == -1 and current_price >= pos.sl:
            return 'stop_loss'

        # Take profit
        if pos.trend == 1 and current_price >= pos.tp:
            return 'take_profit'
        if pos.trend == -1 and current_price <= pos.tp:
            return 'take_profit'

        # Max hold (TF only)
        if pos.regime == 'tf':
            bars_held = (now - pos.entry_time).total_seconds() / 1800  # 30m bars
            if bars_held >= TF_MAX_HOLD:
                return 'max_hold'

        return None

    def _update_trailing_stop(self, pos: OpenPosition, current_price: float,
                               atr: float):
        """Update trailing stop for TF positions."""
        if pos.regime != 'tf':
            return
        if atr <= 0 or np.isnan(atr):
            return

        bars_held = (datetime.now(timezone.utc) - pos.entry_time).total_seconds() / 1800
        if bars_held < TF_MIN_HOLD:
            return

        if pos.trend == 1:
            new_sl = current_price - TRAIL_ATR_MULT * atr
            if new_sl > pos.sl:
                pos.sl = new_sl
                asyncio.create_task(
                    self.connector.modify_position(pos.ctrader_ticket, sl_price=new_sl, pair=pos.pair)
                )
        else:
            new_sl = current_price + TRAIL_ATR_MULT * atr
            if new_sl < pos.sl:
                pos.sl = new_sl
                asyncio.create_task(
                    self.connector.modify_position(pos.ctrader_ticket, sl_price=new_sl, pair=pos.pair)
                )

    async def _execute_entry(self, entry: Dict) -> bool:
        """Execute an entry trade."""
        pair = entry['pair']
        trend = entry['trend']
        entry_price = entry['entry']
        sl = entry['sl']
        tp = entry['tp']
        regime = entry['regime']
        risk_pct = entry['risk_pct']
        pip = entry['pip']
        pv = entry['pv']

        # Position sizing (exact match to backtest)
        sl_dist = abs(entry_price - sl)
        if sl_dist == 0:
            return False

        spread = SPREAD.get(pair, 2.0) * pip
        entry_fill = entry_price + spread / 2 if trend == 1 else entry_price - spread / 2

        sz = ps.compute_position_size(
            pair=pair,
            side='BUY' if trend == 1 else 'SELL',
            entry_price=entry_fill,
            sl_price=sl,
            account_balance_usd=self.balance,
            risk_pct=risk_pct,
            leverage=LEV,
            margin_safety=0.5,
            snap=SNAP,
            lot_step=0.01,
            min_lot=0.01,
            max_lot=10.0,
            existing_margin_used=0.0
        )

        if not sz.ok:
            logger.warning(f"Position sizing failed for {pair}: {sz}")
            return False

        # Place order
        result = await self.connector.place_market_order(
            symbol=pair,
            side='BUY' if trend == 1 else 'SELL',
            volume=sz.lot_size,
            sl_price=sl,
            tp_price=tp,
            comment=f"{'MR' if regime == 'mr' else 'TF'}_{trend}"
        )

        if result.success:
            pos = OpenPosition(
                pair=pair,
                trend=trend,
                entry=result.fill_price or entry_fill,
                sl=sl,
                tp=tp,
                lot=sz.lot_size,
                bar=0,
                pip=pip,
                pv=pv,
                spread=SPREAD.get(pair, 2.0),
                regime=regime,
                ctrader_ticket=result.position_id or result.order_id,
                entry_time=datetime.now(timezone.utc)
            )
            self.open_positions.append(pos)
            logger.info(f"Opened {regime.upper()} {'LONG' if trend==1 else 'SHORT'} "
                       f"{pair} @ {pos.entry:.5f} SL={sl:.5f} TP={tp:.5f} "
                       f"Lot={sz.lot_size:.2f}")
            return True
        else:
            logger.error(f"Order failed for {pair}: {result.error}")
            return False

    async def _execute_exit(self, pos: OpenPosition, reason: str,
                             current_price: float) -> bool:
        """Execute an exit trade. Returns True if close succeeded."""
        # Calculate P&L
        pip_size = pos.pip
        if pos.trend == 1:
            pnl_pips = (current_price - pos.entry) / pip_size
        else:
            pnl_pips = (pos.entry - current_price) / pip_size

        pnl_pips -= 1.4  # Commission
        pnl_dollars = pnl_pips * pos.pv * pos.lot

        # Close position
        result = await self.connector.close_position(pos.ctrader_ticket, volume=pos.lot)

        if result.success:
            self.balance += pnl_dollars
            self.trade_log.append({
                'time': datetime.now(timezone.utc),
                'pair': pos.pair,
                'regime': pos.regime,
                'direction': 'long' if pos.trend == 1 else 'short',
                'entry': pos.entry,
                'exit': current_price,
                'pnl_pips': pnl_pips,
                'pnl_dollars': pnl_dollars,
                'reason': reason,
            })
            logger.info(f"Closed {pos.pair} {reason}: P&L=${pnl_dollars:.2f} "
                       f"({pnl_pips:.1f} pips)")
            return True
        else:
            logger.error(f"Failed to close {pos.pair}: {result.error}")
            return False

    async def run_cycle(self):
        """Run one trading cycle."""
        now = datetime.now(timezone.utc)
        today = now.date()

        # Reset daily P&L
        if self.current_date != today:
            self.current_date = today
            self.daily_pnl = 0.0

        # Session check
        if not igs(now):
            return

        # Daily loss limit (5%)
        if self.daily_pnl < -(0.05 * self.balance):
            logger.warning("Daily loss limit reached")
            return

        # Get current prices
        prices = await self.connector.get_symbols_prices(PAIRS)

        # Validate spot prices for pairs with open positions
        for pos in self.open_positions:
            if pos.pair not in prices or prices[pos.pair] <= 0:
                logger.warning(f"No valid spot price for {pos.pair} (has open position), cannot check exits")
                return

        # Sync open_positions with server state
        server_positions = self.connector.get_positions()
        server_pos_ids = {str(p.positionId) for p in server_positions}
        logger.debug(f"Server positions: {len(server_positions)}, engine positions: {len(self.open_positions)}")
        synced = []
        for pos in self.open_positions:
            if pos.ctrader_ticket in server_pos_ids:
                synced.append(pos)
            else:
                logger.info(f"Position {pos.pair} {pos.ctrader_ticket} no longer on server, removing")
                self.trade_log.append({
                    'time': now,
                    'pair': pos.pair,
                    'regime': pos.regime,
                    'direction': 'long' if pos.trend == 1 else 'short',
                    'entry': pos.entry,
                    'exit': None,
                    'pnl_pips': 0,
                    'pnl_dollars': 0,
                    'reason': 'server_closed',
                })
        self.open_positions = synced

        # Check exits
        remaining = []
        for pos in self.open_positions:
            if pos.pair not in prices:
                remaining.append(pos)
                continue

            current_price = prices[pos.pair]

            # Sanity check: spot price must be within 20% of entry
            if pos.entry > 0:
                price_ratio = current_price / pos.entry
                if price_ratio < 0.8 or price_ratio > 1.2:
                    logger.warning(f"Skipping exit check for {pos.pair}: price={current_price:.5f} vs entry={pos.entry:.5f} (ratio={price_ratio:.4f})")
                    remaining.append(pos)
                    continue

            reason = self._check_exit(pos, current_price)

            if reason:
                closed = await self._execute_exit(pos, reason, current_price)
                if closed:
                    continue  # Position closed, don't add to remaining
                else:
                    remaining.append(pos)  # Close failed, keep position
            else:
                # Update trailing stop
                ind = self._indicators.get(pos.pair)
                if ind and ind['n'] > 0:
                    atr = ind['atr'][-1]
                    self._update_trailing_stop(pos, current_price, atr)
                remaining.append(pos)

        self.open_positions = remaining

        # Check entries
        # Refresh balance from server
        current_balance = await self.connector.get_account_balance()
        if current_balance > 0:
            self.balance = current_balance

        MIN_BALANCE = 5.0  # Don't trade if balance below this
        if self.balance < MIN_BALANCE:
            logger.warning(f"Balance ${self.balance:.2f} below minimum ${MIN_BALANCE}, skipping entries")
            return

        for pair in PAIRS:
            if len(self.open_positions) >= 10:
                break

            # Skip if already have position in this pair
            if any(p.pair == pair for p in self.open_positions):
                continue

            # Check for entry signal
            entry = self._check_entry(pair)
            if entry:
                success = await self._execute_entry(entry)
                if not success:
                    break  # Stop trying entries if one fails (likely margin issue)

        # Write status for dashboard
        self._write_status_file()

    async def run(self, interval_seconds: int = 30):
        """Run the live engine continuously."""
        logger.info("Live engine running...")

        while True:
            try:
                await self.run_cycle()
                await asyncio.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in run cycle: {e}")
                await asyncio.sleep(60)

        # Close all positions on shutdown
        await self.connector.close_all_positions()
        logger.info("Live engine stopped")

    def _write_status_file(self):
        """Write engine status to JSON for the dashboard."""
        now = datetime.now(timezone.utc)
        positions = []
        for pos in self.open_positions:
            positions.append({
                'pair': pos.pair,
                'direction': 'long' if pos.trend == 1 else 'short',
                'entry': pos.entry,
                'sl': pos.sl,
                'tp': pos.tp,
                'lot': pos.lot,
                'regime': pos.regime,
                'ctrader_ticket': pos.ctrader_ticket,
                'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
            })

        recent_trades = []
        for t in self.trade_log[-30:]:
            recent_trades.append({
                'time': t['time'].isoformat() if hasattr(t['time'], 'isoformat') else str(t['time']),
                'pair': t['pair'],
                'regime': t['regime'],
                'direction': t['direction'],
                'entry': t['entry'],
                'exit': t['exit'],
                'pnl_pips': round(t['pnl_pips'], 1),
                'pnl_dollars': round(t['pnl_dollars'], 2),
                'reason': t['reason'],
            })

        wins = sum(1 for t in self.trade_log if t['pnl_dollars'] > 0)
        losses = sum(1 for t in self.trade_log if t['pnl_dollars'] <= 0)
        total = wins + losses
        total_pnl = sum(t['pnl_dollars'] for t in self.trade_log)

        status = {
            'timestamp': now.isoformat(),
            'running': True,
            'balance': round(self.balance, 2),
            'equity': round(self.balance, 2),
            'daily_pnl': round(self.daily_pnl, 2),
            'open_positions': positions,
            'stats': {
                'total_trades': total,
                'wins': wins,
                'losses': losses,
                'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
                'total_pnl': round(total_pnl, 2),
                'avg_pnl': round(total_pnl / total, 2) if total > 0 else 0,
            },
            'recent_trades': recent_trades,
        }

        try:
            with open(self._status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write status file: {e}")

    def get_stats(self) -> Dict:
        """Get current statistics."""
        wins = sum(1 for t in self.trade_log if t['pnl_dollars'] > 0)
        losses = sum(1 for t in self.trade_log if t['pnl_dollars'] <= 0)
        total = wins + losses

        return {
            'balance': self.balance,
            'equity': self.balance,
            'open_positions': len(self.open_positions),
            'total_trades': total,
            'win_rate': wins / total * 100 if total > 0 else 0,
            'daily_pnl': self.daily_pnl,
        }
