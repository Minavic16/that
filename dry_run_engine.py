"""
Dry-Run Engine — MR + TF + Correlation Filter
Uses yfinance for free real-time data. No broker connection needed.

Same strategy logic as live_engine.py / test_combined_corr.py.
Logs all trades to /root/logs/live_engine_status.json for the dashboard.
"""
import asyncio
import json
import logging
import os
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import position_sizing as ps

logger = logging.getLogger(__name__)

# =================== STRATEGY PARAMETERS (EXACT MATCH TO BACKTEST) ===================
PAIRS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'NZD/USD',
         'EUR/GBP', 'EUR/CHF', 'EUR/JPY', 'AUD/JPY', 'EUR/AUD', 'AUD/CAD']

YF_MAP = {
    'EUR/USD': 'EURUSD=X', 'GBP/USD': 'GBPUSD=X', 'USD/JPY': 'JPY=X',
    'USD/CHF': 'CHF=X', 'AUD/USD': 'AUDUSD=X', 'NZD/USD': 'NZDUSD=X',
    'EUR/GBP': 'EURGBP=X', 'EUR/CHF': 'EURCHF=X', 'EUR/JPY': 'EURJPY=X',
    'AUD/JPY': 'AUDJPY=X', 'EUR/AUD': 'EURAUD=X', 'AUD/CAD': 'AUDCAD=X',
}

DEFAULT_USD = {'USD': 1.0, 'EUR': 1.08, 'GBP': 1.26, 'JPY': 0.0067,
               'CHF': 1.12, 'AUD': 0.66, 'NZD': 0.60, 'CAD': 0.74}

SPREAD = {
    'EUR/USD': 1.0, 'GBP/USD': 1.2, 'USD/JPY': 1.0, 'USD/CHF': 1.5,
    'AUD/USD': 1.2, 'NZD/USD': 1.8, 'EUR/GBP': 1.2, 'EUR/CHF': 1.5,
    'EUR/JPY': 1.5, 'AUD/JPY': 1.5, 'EUR/AUD': 2.0, 'AUD/CAD': 2.0,
}

SNAP = ps.QuoteSnapshot(usd_value=DEFAULT_USD)

# Session filter
SESSIONS = {'london': (7, 16), 'new_york': (12, 20)}
SKIP_FRI = 20
SKIP_MON = 3

# MR params
MR_RISK = 0.035
MR_RR = 2.2

# TF params
TF_RISK = 0.022
BREAKOUT_ZONE = 0.005
TRAIL_ATR_MULT = 2.5
TF_MAX_HOLD = 100
TF_MIN_HOLD = 8
TF_TIME_STOP = 30  # bars — force-close TF trades that haven't hit TP/SL

# Correlation filter
CORR_THRESHOLD = 0.75
MAX_SAME_CURRENCY = 2

# Session filter
SESSION_CLOSE_HOUR = 20  # UTC — MR positions close near end of NY session
SESSION_REENTRY_COOLDOWN = 3600  # seconds — don't re-enter same pair after session_close

STATUS_FILE = '/root/logs/live_engine_status.json'
LEV = 100
MIN_BALANCE = 5.0


def igs(ts):
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
    base, quote = pair.split('/')
    return base, quote


def check_currency_overlap(open_positions, new_pair):
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
    trend: int
    entry: float
    sl: float
    tp: float
    lot: float
    pip: float
    pv: float
    spread: float
    regime: str
    entry_time: datetime = None


class DryRunEngine:
    POSITIONS_FILE = '/root/logs/open_positions.json'

    def __init__(self, initial_balance: float = 2500.0):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.open_positions: List[OpenPosition] = []
        self.trade_log = []
        self.daily_pnl = 0.0
        self.current_date = None
        self._indicators = {}
        self._corr_matrix = None
        self._status_file = STATUS_FILE
        self._last_prices = {}
        self._session_close_times = {}  # {pair: datetime} — when last session_close happened
        self._load_positions()

    def _load_positions(self):
        """Load open positions from disk."""
        try:
            with open(self.POSITIONS_FILE, 'r') as f:
                data = json.load(f)
            self.balance = data.get('balance', self.initial_balance)
            self.daily_pnl = data.get('daily_pnl', 0.0)
            for p in data.get('open_positions', []):
                pair = p['pair']
                self.open_positions.append(OpenPosition(
                    pair=pair, trend=1 if p['direction'] == 'long' else -1,
                    entry=p['entry'], sl=p['sl'], tp=p['tp'],
                    lot=p['lot'], regime=p['regime'],
                    entry_time=datetime.fromisoformat(p['entry_time']) if p.get('entry_time') else None,
                    pip=ps.pip_size_for_pair(pair),
                    pv=ps.pip_value_per_lot(pair, SNAP),
                    spread=SPREAD.get(pair, 2.0),
                ))
            logger.info(f"Loaded {len(self.open_positions)} open positions, balance=${self.balance:.2f}")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_positions(self):
        """Persist open positions to disk."""
        data = {
            'balance': round(self.balance, 2),
            'daily_pnl': round(self.daily_pnl, 2),
            'open_positions': [{
                'pair': p.pair, 'direction': 'long' if p.trend == 1 else 'short',
                'entry': p.entry, 'sl': p.sl, 'tp': p.tp,
                'lot': p.lot, 'regime': p.regime,
                'entry_time': p.entry_time.isoformat() if p.entry_time else None,
            } for p in self.open_positions],
        }
        try:
            os.makedirs(os.path.dirname(self.POSITIONS_FILE), exist_ok=True)
            with open(self.POSITIONS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save positions: {e}")

    async def start(self):
        logger.info("Starting dry-run engine...")
        await self._load_data()
        await self._compute_correlation_matrix()
        logger.info("Dry-run engine started")
        return True

    async def _load_data(self):
        """Load 30m and 4H data from yfinance for all pairs."""
        for pair in PAIRS:
            yf_sym = YF_MAP.get(pair)
            if not yf_sym:
                continue
            try:
                await asyncio.sleep(0.1)
                ticker = yf.Ticker(yf_sym)
                df = ticker.history(period='60d', interval='30m')
                if df.empty or len(df) < 200:
                    logger.warning(f"Not enough data for {pair}: {len(df)} rows")
                    continue

                df.index = df.index.tz_convert('UTC')

                # 4H data for EMA
                d4h = df[['Open', 'High', 'Low', 'Close']].resample('4h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
                }).dropna(subset=['Close'])

                e200 = d4h['Close'].ewm(span=200, adjust=False).mean()
                e50 = d4h['Close'].ewm(span=50, adjust=False).mean()

                # ATR
                tr1 = d4h['High'] - d4h['Low']
                tr2 = abs(d4h['High'] - d4h['Close'].shift(1))
                tr3 = abs(d4h['Low'] - d4h['Close'].shift(1))
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr_4h = tr.rolling(14).mean()

                pip = ps.pip_size_for_pair(pair)
                pv = ps.pip_value_per_lot(pair, SNAP)

                self._indicators[pair] = {
                    'c': df['Close'].values,
                    'h': df['High'].values,
                    'lo': df['Low'].values,
                    'o': df['Open'].values,
                    'ts': df.index,
                    'n': len(df),
                    'e200': e200.reindex(df.index, method='ffill').values,
                    'e50': e50.reindex(df.index, method='ffill').values,
                    'atr': atr_4h.reindex(df.index, method='ffill').values,
                    'pip': pip,
                    'pv': pv,
                    'spread': SPREAD.get(pair, 2.0),
                }
                logger.info(f"Loaded {pair}: {len(df)} bars")
            except Exception as e:
                logger.error(f"Error loading {pair}: {e}")

    async def _compute_correlation_matrix(self):
        closes = {}
        for pair in PAIRS:
            if pair in self._indicators:
                closes[pair] = pd.Series(
                    self._indicators[pair]['c'],
                    index=self._indicators[pair]['ts']
                )
        if closes:
            price_df = pd.DataFrame(closes)
            returns = price_df.pct_change().dropna()
            self._corr_matrix = returns.corr()
            logger.info("Correlation matrix computed")

    def _get_current_price(self, pair: str) -> Optional[float]:
        """Get latest price from the 30m data."""
        if pair not in self._indicators:
            return None
        ind = self._indicators[pair]
        if ind['n'] == 0:
            return None
        return float(ind['c'][-1])

    def _check_entry(self, pair: str) -> Optional[Dict]:
        if pair not in self._indicators:
            return None
        ind = self._indicators[pair]
        i = ind['n'] - 1
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
        now = datetime.now(timezone.utc)
        if pos.regime == 'mr' and now.hour >= SESSION_CLOSE_HOUR:
            self._session_close_times[pos.pair] = now
            return 'session_close'

        if pos.trend == 1 and current_price <= pos.sl:
            return 'stop_loss'
        if pos.trend == -1 and current_price >= pos.sl:
            return 'stop_loss'

        if pos.trend == 1 and current_price >= pos.tp:
            return 'take_profit'
        if pos.trend == -1 and current_price <= pos.tp:
            return 'take_profit'

        if pos.regime == 'tf':
            bars_held = (now - pos.entry_time).total_seconds() / 1800
            if bars_held >= TF_TIME_STOP and bars_held < TF_MAX_HOLD:
                return 'time_stop'
            if bars_held >= TF_MAX_HOLD:
                return 'max_hold'

        return None

    def _execute_entry(self, entry: Dict) -> bool:
        pair = entry['pair']
        trend = entry['trend']
        entry_price = entry['entry']
        sl = entry['sl']
        tp = entry['tp']
        regime = entry['regime']
        risk_pct = entry['risk_pct']
        pip = entry['pip']
        pv = entry['pv']

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
            return False

        pos = OpenPosition(
            pair=pair,
            trend=trend,
            entry=entry_fill,
            sl=sl,
            tp=tp,
            lot=sz.lot_size,
            pip=pip,
            pv=pv,
            spread=SPREAD.get(pair, 2.0),
            regime=regime,
            entry_time=datetime.now(timezone.utc)
        )
        self.open_positions.append(pos)
        self._save_positions()
        logger.info(f"DRY-RUN OPEN {regime.upper()} {'LONG' if trend==1 else 'SHORT'} "
                   f"{pair} @ {entry_fill:.5f} SL={sl:.5f} TP={tp:.5f} Lot={sz.lot_size:.2f}")
        return True

    def _execute_exit(self, pos: OpenPosition, reason: str, current_price: float) -> bool:
        pip_size = pos.pip
        if pos.trend == 1:
            pnl_pips = (current_price - pos.entry) / pip_size
        else:
            pnl_pips = (pos.entry - current_price) / pip_size

        pnl_pips -= 1.4
        pnl_dollars = pnl_pips * pos.pv * pos.lot

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
        logger.info(f"DRY-RUN CLOSE {pos.pair} {reason}: P&L=${pnl_dollars:.2f} ({pnl_pips:.1f} pips)")
        return True

    def _write_status_file(self):
        now = datetime.now(timezone.utc)
        positions = []
        unrealized_pnl = 0.0
        for pos in self.open_positions:
            current_price = self._get_current_price(pos.pair)
            if current_price is not None:
                pip_size = pos.pip
                if pos.trend == 1:  # long
                    pos_pnl_pips = (current_price - pos.entry) / pip_size
                else:  # short
                    pos_pnl_pips = (pos.entry - current_price) / pip_size
                pos_pnl_dollars = pos_pnl_pips * pos.lot * pip_size * 100000
                unrealized_pnl += pos_pnl_dollars
            else:
                pos_pnl_dollars = 0.0

            positions.append({
                'pair': pos.pair,
                'direction': 'long' if pos.trend == 1 else 'short',
                'entry': pos.entry,
                'sl': pos.sl,
                'tp': pos.tp,
                'lot': pos.lot,
                'regime': pos.regime,
                'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                'current_price': round(current_price, 5) if current_price else None,
                'unrealized_pnl': round(pos_pnl_dollars, 2),
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
            'mode': 'DRY-RUN',
            'balance': round(self.balance, 2),
            'equity': round(self.balance + unrealized_pnl, 2),
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
            logger.error(f"Failed to write status: {e}")

    async def run_cycle(self):
        now = datetime.now(timezone.utc)
        today = now.date()

        if self.current_date != today:
            self.current_date = today
            self.daily_pnl = 0.0

        if not igs(now):
            return

        # Refresh data from yfinance periodically
        for pair in PAIRS:
            if pair in self._indicators:
                yf_sym = YF_MAP.get(pair)
                if yf_sym:
                    try:
                        ticker = yf.Ticker(yf_sym)
                        df = ticker.history(period='5d', interval='30m')
                        if not df.empty:
                            df.index = df.index.tz_convert('UTC')
                            self._indicators[pair]['c'] = df['Close'].values
                            self._indicators[pair]['h'] = df['High'].values
                            self._indicators[pair]['lo'] = df['Low'].values
                            self._indicators[pair]['o'] = df['Open'].values
                            self._indicators[pair]['ts'] = df.index
                            self._indicators[pair]['n'] = len(df)
                            await asyncio.sleep(0)
                    except Exception:
                        pass

        # Check exits
        remaining = []
        for pos in self.open_positions:
            current_price = self._get_current_price(pos.pair)
            if current_price is None:
                remaining.append(pos)
                continue

            reason = self._check_exit(pos, current_price)
            if reason:
                self._execute_exit(pos, reason, current_price)
            else:
                remaining.append(pos)

        self.open_positions = remaining
        self._save_positions()

        # Check entries
        if self.balance < MIN_BALANCE:
            return

        now = datetime.now(timezone.utc)
        for pair in PAIRS:
            if len(self.open_positions) >= 10:
                break
            if any(p.pair == pair for p in self.open_positions):
                continue
            # Check session_close cooldown
            last_close = self._session_close_times.get(pair)
            if last_close and (now - last_close).total_seconds() < SESSION_REENTRY_COOLDOWN:
                continue
            entry = self._check_entry(pair)
            if entry:
                self._execute_entry(entry)

        self._write_status_file()

    async def run(self, interval_seconds: int = 60):
        logger.info("Dry-run engine running...")
        while True:
            try:
                await self.run_cycle()
                await asyncio.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in run cycle: {e}")
                await asyncio.sleep(30)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('/root/logs/dry_run.log'),
            logging.StreamHandler()
        ]
    )
    engine = DryRunEngine(initial_balance=2500.0)
    asyncio.run(engine.start())
    asyncio.run(engine.run(interval_seconds=60))
