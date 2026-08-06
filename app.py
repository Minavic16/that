"""
MR+TF Live Engine — Dashboard
==============================
JSON API + static HTML/JS frontend.
Run: python3 app.py
Access: http://localhost:5000
"""

import os
import json
import glob
import subprocess
import signal as sig_module
import hashlib
from datetime import datetime, UTC
from functools import wraps

from flask import Flask, jsonify, send_file, request, session, redirect, url_for, render_template
import requests as http_requests

import persistence as db

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()

# ── Auth ──────────────────────────────────────────────────────────────────────
USERS = {
    'Noble': {'pw': hashlib.sha256('10billion'.encode()).hexdigest(), 'admin': True},
    'Dominion': {'pw': hashlib.sha256('deadpool90z'.encode()).hexdigest(), 'admin': False},
    'LordDN': {'pw': hashlib.sha256('Desire23$'.encode()).hexdigest(), 'admin': False},
    'GREENSTREET': {'pw': hashlib.sha256('1kingdombillioniare'.encode()).hexdigest(), 'admin': False},
    'Mindavic': {'pw': hashlib.sha256('4050609da'.encode()).hexdigest(), 'admin': True},
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login_page'))
        user = session.get('user')
        if not user or not USERS.get(user, {}).get('admin'):
            return jsonify({'error': 'admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.form
        user = data.get('username', '')
        pw = data.get('password', '')
        if user in USERS and hashlib.sha256(pw.encode()).hexdigest() == USERS[user]['pw']:
            session['logged_in'] = True
            session['user'] = user
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid username or password'), 401
    if 'logged_in' in session:
        return redirect(url_for('index'))
    return render_template('login.html', error=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ── Config ────────────────────────────────────────────────────────────────────

STRATEGY_CONFIG = {
    'version': 'MR+TF Correlation Filter',
    'account_size': 2500,
    'leverage': 100,
    'pairs': [
        'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'NZD/USD',
        'EUR/GBP', 'EUR/CHF', 'EUR/JPY', 'AUD/JPY', 'EUR/AUD', 'AUD/CAD',
    ],
    'timeframe': '30min',
    'ema': 200,
    'mr_threshold': 0.5,
    'tf_threshold': 0.5,
    'mr_risk': 3.5,
    'mr_rr': 2.2,
    'tf_risk': 2.2,
    'breakout_zone': 0.5,
    'trail_atr_mult': 2.5,
    'correlation_threshold': 0.85,
    'max_per_currency': 2,
    'sessions': {
        'london': '07:00-16:00 UTC',
        'new_york': '12:00-20:00 UTC',
        'overlap': '12:00-16:00 UTC (BEST)',
    },
    'friday_close': '20:00 UTC',
    'monday_open': '03:00 UTC',
    'costs': {
        'commission': '$3.50/lot/trade',
        'entry_slippage': '0.3 pips',
        'spreads': 'EUR/USD 0.8, GBP/USD 1.0, USD/JPY 1.0, USD/CHF 1.2, AUD/USD 0.9, NZD/USD 1.2, EUR/GBP 1.2, EUR/CHF 1.5, EUR/JPY 2.0, AUD/JPY 2.0, EUR/AUD 2.0, AUD/CAD 2.0',
    },
}

EXPECTED_METRICS = {
    'full': {
        'total_trades': 2652,
        'trades_per_month': 49,
        'win_rate': 61.2,
        'profit_factor': 2.3,
        'max_drawdown': 2.8,
        'monthly_ev': '$491/mo (fixed $2,500)',
        'ev_per_trade': '$10.69',
    },
    'oos': {
        'total_trades': 864,
        'trades_per_month': 48,
        'win_rate': 70.7,
        'profit_factor': 4.4,
        'max_drawdown': 3.7,
        'monthly_ev': '$764/mo (30.6%)',
        'ev_per_trade': '$15.92',
    },
}

MRTF_VALIDATION = [
    {'name': 'Full Period (2022-2026)', 'detail': '49 trades/mo, 61.2% WR, 2.3 PF, 2.8% MDD', 'pass': True},
    {'name': 'OOS (2025-2026)', 'detail': '48 trades/mo, 70.7% WR, 4.4 PF, 3.7% MDD', 'pass': True},
    {'name': 'Fixed $2,500 Sizing', 'detail': 'All sizes computed on $2,500 balance, not compounding', 'pass': True},
    {'name': 'MR Regime', 'detail': 'Near EMA200 (<0.5%) → session close exit, 74.2% WR OOS', 'pass': True},
    {'name': 'TF Regime', 'detail': 'Breakaway from EMA200 (>0.5%) → trailing stop, 2.5x ATR', 'pass': True},
    {'name': 'Correlation Filter', 'detail': '0.85 threshold, max 2 per currency, overlap filter', 'pass': True},
    {'name': 'Costs Baked In', 'detail': '$3.50 commission, 0.3 pip slippage, fixed spreads per pair', 'pass': True},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow():
    return datetime.now(UTC)


def check_session():
    now = _utcnow()
    hour = now.hour
    day = now.weekday()

    if day == 4 and hour >= 20:
        return False, 'Friday — markets closing'
    if day == 0 and hour < 3:
        return False, 'Monday — markets not open yet'
    if day >= 5:
        return False, 'Weekend — markets closed'

    if 12 <= hour < 16:
        return True, 'London/NY Overlap (BEST)'
    elif 7 <= hour < 12:
        return True, 'London Session'
    elif 16 <= hour < 20:
        return True, 'New York Session'
    else:
        return False, 'Outside trading hours'


def load_latest_signals():
    signal_files = sorted(glob.glob('signals_structured_*.json'))
    if not signal_files:
        return {'signals': [], 'file': None, 'timestamp': None}
    latest = signal_files[-1]
    try:
        with open(latest, 'r') as f:
            data = json.load(f)
        data.setdefault('signals', [])
        data['file'] = os.path.basename(latest)
        return data
    except (json.JSONDecodeError, IOError):
        return {'signals': [], 'file': None, 'timestamp': None}


def load_engine_status():
    """Read the dry_run_engine status file, enhanced with DB stats."""
    for path in ('/root/logs/live_engine_status.json', 'logs/live_engine_status.json'):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                # Ensure open_positions list exists
                if 'open_positions' not in data:
                    data['open_positions'] = []
                if 'balance' not in data:
                    data['balance'] = 2500.0
                if 'equity' not in data:
                    data['equity'] = data['balance']
                if 'stats' not in data:
                    data['stats'] = {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0}
                if 'recent_trades' not in data:
                    data['recent_trades'] = []

                # Override stats from DB (survives restart)
                try:
                    db_stats = db.get_trade_stats()
                    if db_stats['total_trades'] > 0:
                        data['stats'] = db_stats
                except Exception:
                    pass

                return data
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return None


# ── Public API ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return send_file('templates/index.html')


@app.route('/backtest')
@login_required
def backtest_page():
    return send_file('templates/backtest.html')


@app.route('/api/state')
@login_required
def api_state():
    session_active, session_status = check_session()
    engine = load_engine_status()
    now = _utcnow()

    return jsonify({
        'timestamp': now.isoformat(),
        'session': {
            'active': session_active,
            'status': session_status,
        },
        'engine': engine,
        'config': STRATEGY_CONFIG,
        'metrics': EXPECTED_METRICS,
        'validation': MRTF_VALIDATION,
    })


@app.route('/api/live')
@login_required
def api_live():
    status = load_engine_status()
    if status is None:
        return jsonify({'running': False, 'error': 'No engine status found'})
    return jsonify(status)


@app.route('/api/signals')
@login_required
def api_signals():
    return jsonify(load_latest_signals())


@app.route('/api/trades')
@login_required
def api_trades():
    """Return full trade history from DB."""
    pair = request.args.get('pair')
    limit = request.args.get('limit', 100, type=int)
    trades = db.load_trades(pair=pair, limit=limit)
    stats = db.get_trade_stats()
    return jsonify({'trades': trades, 'stats': stats})


@app.route('/api/config')
@login_required
def api_config():
    return jsonify(STRATEGY_CONFIG)


@app.route('/api/backtest')
@login_required
def api_backtest():
    return jsonify({
        'metrics': EXPECTED_METRICS,
        'validation': MRTF_VALIDATION,
        'config': STRATEGY_CONFIG,
    })


# ── Admin API (auth required) ────────────────────────────────────────────────

def _run_shell(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, 'Command timed out'
    except Exception as e:
        return False, str(e)


def _find_engine_pid():
    try:
        result = subprocess.run(['pgrep', '-f', 'dry_run_engine.py'], capture_output=True, text=True, timeout=5)
        pids = result.stdout.strip().split('\n')
        return [int(p) for p in pids if p.strip()]
    except Exception:
        return []


@app.route('/api/admin/status')
@admin_required
def admin_status():
    engine_pids = _find_engine_pid()
    dash_running = True
    ngrok_ok = False
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:4040/api/tunnels', timeout=2)
        ngrok_ok = True
    except Exception:
        pass
    return jsonify({
        'engine_pids': engine_pids,
        'engine_running': len(engine_pids) > 0,
        'dashboard_running': dash_running,
        'ngrok_running': ngrok_ok,
    })


@app.route('/api/admin/engine/start', methods=['POST'])
@admin_required
def admin_engine_start():
    mode = request.json.get('mode', 'dry-run') if request.json else 'dry-run'
    if mode not in ('dry-run', 'live'):
        return jsonify({'ok': False, 'error': 'Invalid mode'}), 400
    ok, out = _run_shell(f'cd /root && screen -dmS dryrun bash -c "python3 dry_run_engine.py > logs/dryrun.log 2>&1"')
    return jsonify({'ok': ok, 'output': out})


@app.route('/api/admin/engine/stop', methods=['POST'])
@admin_required
def admin_engine_stop():
    ok, out = _run_shell('screen -S dryrun -X quit 2>/dev/null; pkill -f dry_run_engine.py 2>/dev/null; echo done')
    return jsonify({'ok': True, 'output': out})


@app.route('/api/admin/engine/restart', methods=['POST'])
@admin_required
def admin_engine_restart():
    _run_shell('screen -S dryrun -X quit 2>/dev/null; pkill -f dry_run_engine.py 2>/dev/null')
    import time
    time.sleep(2)
    mode = request.json.get('mode', 'dry-run') if request.json else 'dry-run'
    ok, out = _run_shell(f'cd /root && screen -dmS dryrun bash -c "python3 dry_run_engine.py > logs/dryrun.log 2>&1"')
    return jsonify({'ok': ok, 'output': out})


@app.route('/api/admin/config/update', methods=['POST'])
@admin_required
def admin_config_update():
    global STRATEGY_CONFIG
    updates = request.json or {}
    allowed = {'mr_risk', 'mr_rr', 'tf_risk', 'breakout_zone', 'trail_atr_mult', 'correlation_threshold', 'account_size', 'leverage'}
    changed = {}
    for key, val in updates.items():
        if key in allowed:
            STRATEGY_CONFIG[key] = val
            changed[key] = val
    if not changed:
        return jsonify({'ok': False, 'error': 'No valid fields to update'}), 400
    return jsonify({'ok': True, 'changed': changed, 'config': STRATEGY_CONFIG})


@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def admin_logs():
    lines = request.args.get('lines', 50, type=int)
    log_file = '/root/logs/dryrun.log'
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
        recent = all_lines[-lines:]
        return jsonify({'ok': True, 'lines': [l.strip() for l in recent]})
    except FileNotFoundError:
        return jsonify({'ok': False, 'error': 'Log file not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/ctradercallback')
def ctrader_callback():
    code = request.args.get('code', '')
    if not code:
        return '<h1>No code provided</h1>'
    env = {}
    with open('/root/.env', 'r') as f:
        for line in f:
            if '=' in line:
                k, v = line.strip().split('=', 1)
                env[k] = v
    params = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'https://panama-crowbar-effort.ngrok-free.dev/ctradercallback',
        'client_id': env['CTRADER_CLIENT_ID'],
        'client_secret': env['CTRADER_CLIENT_SECRET'],
    }
    resp = http_requests.post('https://openapi.ctrader.com/apps/token', params=params,
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
    data = resp.json()
    if 'accessToken' in data:
        with open('/root/.env', 'r') as f:
            content = f.read()
        content = content.replace(env['CTRADER_ACCESS_TOKEN'], data['accessToken'])
        content = content.replace(env['CTRADER_REFRESH_TOKEN'], data['refreshToken'])
        with open('/root/.env', 'w') as f:
            f.write(content)
        return f'<h1 style="color:green">Tokens Saved!</h1><p>Access token: {data["accessToken"][:30]}...</p>'
    return f'<h1>Error</h1><pre>{resp.text}</pre>'


if __name__ == '__main__':
    print('=' * 60)
    print('  MR+TF LIVE ENGINE DASHBOARD')
    print('  http://localhost:5000')
    print('  Users: Noble, Dominion, LordDN, GREENSTREET, Mindavic')
    print('  Admins: Noble, Mindavic')
    print('=' * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
