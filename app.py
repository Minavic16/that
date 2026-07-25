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
from datetime import datetime, UTC

from flask import Flask, jsonify, send_file, request
import requests as http_requests

app = Flask(__name__)

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
    'correlation_threshold': 0.75,
    'max_per_currency': 2,
    'sessions': {
        'london': '07:00-16:00 UTC',
        'new_york': '12:00-21:00 UTC',
        'overlap': '12:00-16:00 UTC (BEST)',
    },
    'friday_close': '20:00 UTC',
    'monday_open': '03:00 UTC',
}

EXPECTED_METRICS = {
    'total_trades': 1840,
    'win_rate': 59.6,
    'profit_factor': 1.7,
    'p5': 'N/A',
    'max_drawdown': 8.8,
    'monthly_ev': '12.2% monthly (full), 29.5% (OOS 2025-2026)',
    'trades_per_month': 46,
    'ev_per_trade': '$493',
    'screen_time': 'Continuous (30min bars)',
}

MRTF_VALIDATION = [
    {'name': 'Full Period Backtest', 'detail': '46 trades/mo, 59.6% WR, 1.7 PF, 8.8% MDD', 'pass': True},
    {'name': 'OOS (2025-2026)', 'detail': '45 trades/mo, 70.2% WR, 4.2 PF, 6.6% MDD', 'pass': True},
    {'name': 'MR Regime', 'detail': 'Near EMA200 (<0.5%) → session close exit, 2.2 RR', 'pass': True},
    {'name': 'TF Regime', 'detail': 'Breakaway from EMA200 (>0.5%) → trailing stop, 2.5x ATR', 'pass': True},
    {'name': 'Correlation Filter', 'detail': '0.75 threshold, max 2 per currency', 'pass': True},
    {'name': 'Leverage-aware Sizing', 'detail': '1:100, per-pair pip-value, 3.5% MR / 2.2% TF risk', 'pass': True},
]


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
    elif 16 <= hour < 21:
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
    for path in ('/root/logs/structured_status.json', 'logs/structured_status.json'):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file('templates/index.html')


@app.route('/api/state')
def api_state():
    session_active, session_status = check_session()
    signals_data = load_latest_signals()
    engine = load_engine_status()
    now = _utcnow()

    return jsonify({
        'timestamp': now.isoformat(),
        'session': {
            'active': session_active,
            'status': session_status,
        },
        'engine': engine,
        'signals': signals_data,
        'config': STRATEGY_CONFIG,
        'metrics': EXPECTED_METRICS,
        'validation': MRTF_VALIDATION,
    })


def load_live_status():
    for path in ('/root/logs/live_engine_status.json', 'logs/live_engine_status.json'):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                # Normalize structured_status format to match live_engine_status
                if 'positions' in data and 'open_positions' not in data:
                    positions = data.get('positions', {})
                    open_positions = []
                    for pair, pos_data in positions.items():
                        if isinstance(pos_data, dict):
                            open_positions.append({
                                'pair': pair,
                                'direction': pos_data.get('direction', 'long'),
                                'entry': pos_data.get('entry', 0),
                                'sl': pos_data.get('sl', 0),
                                'tp': pos_data.get('tp', 0),
                                'lot': pos_data.get('lot', 0),
                                'regime': pos_data.get('regime', ''),
                                'entry_time': pos_data.get('entry_time'),
                                'current_price': pos_data.get('current_price'),
                                'unrealized_pnl': pos_data.get('unrealized_pnl', 0),
                            })
                    data['open_positions'] = open_positions
                if 'balance' not in data and 'peak' in data:
                    data['balance'] = data.get('peak', 1000)
                if 'equity' not in data:
                    data['equity'] = data.get('balance', 0)
                if 'daily_pnl' not in data:
                    data['daily_pnl'] = 0
                if 'stats' not in data:
                    data['stats'] = {
                        'total_trades': data.get('trades_today', 0),
                        'wins': 0, 'losses': 0,
                        'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0,
                    }
                if 'recent_trades' not in data:
                    data['recent_trades'] = []
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return None


@app.route('/api/live')
def api_live():
    status = load_live_status()
    if status is None:
        return jsonify({'running': False, 'error': 'No live engine status found'})
    return jsonify(status)


@app.route('/api/signals')
def api_signals():
    return jsonify(load_latest_signals())


@app.route('/api/config')
def api_config():
    return jsonify(STRATEGY_CONFIG)


# ── Admin API ────────────────────────────────────────────────────────────────

def _run_shell(cmd):
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, 'Command timed out'
    except Exception as e:
        return False, str(e)


def _find_engine_pid():
    """Find the PID of structured_engine.py."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'structured_engine.py'],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split('\n')
        return [int(p) for p in pids if p.strip()]
    except Exception:
        return []


@app.route('/api/admin/status')
def admin_status():
    """Get detailed admin status."""
    engine_pids = _find_engine_pid()
    dash_running = True  # we're serving this request, so dashboard is up
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
def admin_engine_start():
    """Start engine in dry-run or live mode."""
    mode = request.json.get('mode', 'dry-run') if request.json else 'dry-run'
    if mode not in ('dry-run', 'live'):
        return jsonify({'ok': False, 'error': 'Invalid mode'}), 400
    ok, out = _run_shell(f'cd /root && ./start_structured.sh {mode}')
    return jsonify({'ok': ok, 'output': out})


@app.route('/api/admin/engine/stop', methods=['POST'])
def admin_engine_stop():
    """Stop the engine."""
    pids = _find_engine_pid()
    for pid in pids:
        try:
            os.kill(pid, sig_module.SIGTERM)
        except ProcessLookupError:
            pass
    return jsonify({'ok': True, 'stopped_pids': pids})


@app.route('/api/admin/engine/restart', methods=['POST'])
def admin_engine_restart():
    """Restart the engine."""
    mode = request.json.get('mode', 'dry-run') if request.json else 'dry-run'
    if mode not in ('dry-run', 'live'):
        return jsonify({'ok': False, 'error': 'Invalid mode'}), 400
    # Stop
    pids = _find_engine_pid()
    for pid in pids:
        try:
            os.kill(pid, sig_module.SIGTERM)
        except ProcessLookupError:
            pass
    import time
    time.sleep(2)
    # Start
    ok, out = _run_shell(f'cd /root && ./start_structured.sh {mode}')
    return jsonify({'ok': ok, 'output': out, 'stopped_pids': pids})


@app.route('/api/admin/signals/run', methods=['POST'])
def admin_signals_run():
    """Force run the signal generator."""
    ok, out = _run_shell('cd /root && python3 signal_generator_structured.py --run 2>&1')
    return jsonify({'ok': ok, 'output': out})


@app.route('/api/admin/config/update', methods=['POST'])
def admin_config_update():
    """Update strategy config (risk_per_entry, rr_target, etc.)."""
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
def admin_logs():
    """Get recent log lines."""
    lines = request.args.get('lines', 50, type=int)
    log_file = '/root/logs/structured_engine.log'
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
        return f'<h1 style="color:green">Tokens Saved!</h1><p>Access token: {data["accessToken"][:30]}...</p><p>You can close this tab.</p>'
    
    return f'<h1>Error</h1><pre>{resp.text}</pre>'


if __name__ == '__main__':
    print('=' * 60)
    print('  MR+TF LIVE ENGINE DASHBOARD')
    print('  http://localhost:5000')
    print('=' * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
