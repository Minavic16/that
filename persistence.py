"""
Persistence Layer — SQLite-based state for MR+TF Engine
=======================================================
Handles: trades, positions, daily state, account state, config.
All writes are atomic (temp + rename). Dedup via broker_order_id.
"""
import os
import json
import sqlite3
import tempfile
import shutil
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

DB_PATH = '/root/logs/engine.db'
POS_JSON = '/root/logs/open_positions.json'
STATUS_JSON = '/root/logs/live_engine_status.json'


def _now():
    return datetime.now(timezone.utc)


@contextmanager
def get_conn():
    """Thread-safe context manager for DB connections."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_order_id TEXT UNIQUE,
                pair TEXT NOT NULL,
                regime TEXT,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                entry_time TEXT,
                exit_time TEXT,
                exit_reason TEXT,
                pnl_pips REAL,
                pnl_dollars REAL,
                commission REAL DEFAULT 3.50,
                lot_size REAL,
                spread REAL,
                bars_held INTEGER,
                sl_price REAL,
                tp_price REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL,
                tp_price REAL,
                lot_size REAL NOT NULL,
                regime TEXT,
                entry_time TEXT,
                broker_order_id TEXT,
                is_open INTEGER NOT NULL DEFAULT 1,
                close_time TEXT,
                close_price REAL,
                close_reason TEXT,
                pnl_dollars REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(pair, entry_time)
            );

            CREATE TABLE IF NOT EXISTS daily_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                daily_pnl REAL DEFAULT 0.0,
                session_close_times TEXT,
                daily_losses TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(trade_date)
            );

            CREATE TABLE IF NOT EXISTS account_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance REAL NOT NULL DEFAULT 2500.0,
                equity REAL NOT NULL DEFAULT 2500.0,
                peak REAL NOT NULL DEFAULT 2500.0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair);
            CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades(exit_time);
            CREATE INDEX IF NOT EXISTS idx_positions_pair ON positions(pair);
            CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
            CREATE INDEX IF NOT EXISTS idx_daily_state_date ON daily_state(trade_date);
        """)
    return True


# ── Trade Operations ──────────────────────────────────────────────────────────

def save_trade(trade: Dict) -> bool:
    """Persist a closed trade. Dedup by broker_order_id if provided."""
    broker_id = trade.get('broker_order_id')
    if broker_id:
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM trades WHERE broker_order_id=?", (broker_id,)
            ).fetchone()
            if existing:
                return False  # already recorded

    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trades
            (broker_order_id, pair, regime, direction, entry_price, exit_price,
             entry_time, exit_time, exit_reason, pnl_pips, pnl_dollars,
             commission, lot_size, spread, bars_held, sl_price, tp_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            broker_id,
            trade.get('pair'),
            trade.get('regime'),
            trade.get('direction'),
            trade.get('entry'),
            trade.get('exit'),
            str(trade.get('entry_time', '')),
            str(trade.get('exit_time', _now().isoformat())),
            trade.get('exit_reason') or trade.get('reason'),
            trade.get('pnl_pips'),
            trade.get('pnl_dollars'),
            trade.get('commission', 3.50),
            trade.get('lot'),
            trade.get('spread'),
            trade.get('bars_held'),
            trade.get('sl'),
            trade.get('tp'),
        ))
    return True


def load_trades(since: str = None, pair: str = None, limit: int = None) -> List[Dict]:
    """Load trade history from DB."""
    query = "SELECT * FROM trades WHERE 1=1"
    params = []
    if since:
        query += " AND exit_time >= ?"
        params.append(since)
    if pair:
        query += " AND pair = ?"
        params.append(pair)
    query += " ORDER BY exit_time DESC"
    if limit:
        query += f" LIMIT {limit}"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_trade_stats() -> Dict:
    """Compute stats from DB trade history."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM trades WHERE pnl_dollars > 0").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM trades WHERE pnl_dollars <= 0").fetchone()[0]
        total_pnl = conn.execute("SELECT COALESCE(SUM(pnl_dollars), 0) FROM trades").fetchone()[0]
        avg_win = conn.execute("SELECT COALESCE(AVG(pnl_dollars), 0) FROM trades WHERE pnl_dollars > 0").fetchone()[0]
        avg_loss = conn.execute("SELECT COALESCE(AVG(pnl_dollars), 0) FROM trades WHERE pnl_dollars <= 0").fetchone()[0]

    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(total_pnl / total, 2) if total > 0 else 0,
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
    }


# ── Position Operations ───────────────────────────────────────────────────────

def save_position(pos: Dict) -> bool:
    """Persist an open position."""
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO positions
            (pair, direction, entry_price, sl_price, tp_price, lot_size,
             regime, entry_time, broker_order_id, is_open)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            pos.get('pair'),
            pos.get('direction'),
            pos.get('entry'),
            pos.get('sl'),
            pos.get('tp'),
            pos.get('lot'),
            pos.get('regime'),
            str(pos.get('entry_time', '')),
            pos.get('broker_order_id'),
        ))
    return True


def close_position(pair: str, entry_time: str, exit_price: float,
                   close_reason: str, pnl_dollars: float) -> bool:
    """Mark a position as closed."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE positions SET is_open=0, close_time=?, close_price=?,
                   close_reason=?, pnl_dollars=?
            WHERE pair=? AND entry_time=? AND is_open=1
        """, (str(_now().isoformat()), exit_price, close_reason, pnl_dollars, pair, entry_time))
    return True


def load_open_positions() -> List[Dict]:
    """Load all open positions from DB."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE is_open=1 ORDER BY entry_time"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Daily State ───────────────────────────────────────────────────────────────

def save_daily_state(trade_date: str, daily_pnl: float = 0.0,
                     session_close_times: Dict = None,
                     daily_losses: Dict = None):
    """Persist daily state (P&L, session closes, losses per pair)."""
    sct = json.dumps({k: str(v) for k, v in (session_close_times or {}).items()})
    dl = json.dumps({k: str(v) for k, v in (daily_losses or {}).items()})
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO daily_state
            (trade_date, daily_pnl, session_close_times, daily_losses, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (trade_date, daily_pnl, sct, dl, str(_now().isoformat())))


def load_daily_state(trade_date: str = None) -> Optional[Dict]:
    """Load daily state. Defaults to today."""
    if trade_date is None:
        trade_date = str(date.today())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM daily_state WHERE trade_date=?", (trade_date,)
        ).fetchone()
    if row:
        d = dict(row)
        d['session_close_times'] = json.loads(d.get('session_close_times', '{}'))
        d['daily_losses'] = json.loads(d.get('daily_losses', '{}'))
        return d
    return None


# ── Account State ─────────────────────────────────────────────────────────────

def save_account_state(balance: float, equity: float = None, peak: float = None):
    """Persist account state (single row)."""
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO account_state (id, balance, equity, peak, updated_at)
            VALUES (1, ?, ?, ?, ?)
        """, (balance, equity or balance, peak or balance, str(_now().isoformat())))


def load_account_state() -> Dict:
    """Load account state."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM account_state WHERE id=1").fetchone()
    if row:
        return dict(row)
    return {'balance': 2500.0, 'equity': 2500.0, 'peak': 2500.0}


# ── Config ────────────────────────────────────────────────────────────────────

def save_config(key: str, value: Any):
    """Save a config key-value pair."""
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO config (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(value), str(_now().isoformat())))


def load_config(key: str = None) -> Any:
    """Load config. If key is None, return all config as dict."""
    with get_conn() as conn:
        if key:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return json.loads(row['value']) if row else None
        else:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {r['key']: json.loads(r['value']) for r in rows}


# ── Atomic File Operations ────────────────────────────────────────────────────

def atomic_write(filepath: str, data: Any):
    """Write JSON atomically: temp file + rename."""
    dir_name = os.path.dirname(filepath)
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_positions_json(balance: float, daily_pnl: float, positions: List[Dict]):
    """Atomic write of open_positions.json for backward compat."""
    data = {
        'balance': round(balance, 2),
        'daily_pnl': round(daily_pnl, 2),
        'open_positions': positions,
    }
    atomic_write(POS_JSON, data)


def save_status_json(status: Dict):
    """Atomic write of live_engine_status.json for dashboard."""
    atomic_write(STATUS_JSON, status)


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate_json_to_db():
    """One-time migration: load existing open_positions.json into DB."""
    if not os.path.exists(POS_JSON):
        return False

    with open(POS_JSON, 'r') as f:
        data = json.load(f)

    balance = data.get('balance', 2500.0)
    daily_pnl = data.get('daily_pnl', 0.0)
    positions = data.get('open_positions', [])

    save_account_state(balance)
    for pos in positions:
        save_position(pos)

    print(f"Migrated {len(positions)} positions, balance=${balance:.2f}")
    return True
