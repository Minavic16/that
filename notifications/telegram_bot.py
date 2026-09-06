"""
NQTS Telegram Bot — Incoming Message Handler
=============================================

Polls for Telegram updates and handles user commands.

Commands:
  /start — Welcome message
  /status — System status
  /positions — Active positions
  /alerts — Recent alerts
  /help — Command list

Does NOT execute trades. Read-only operations only.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Track last update_id to avoid re-processing
_last_update_id: int = 0


def get_updates(offset: int = 0) -> list[dict]:
    """Poll Telegram for new messages."""
    params = {"offset": str(offset), "timeout": "5"}
    url = f"{BASE_URL}/getUpdates?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("result", [])
    except Exception:
        return []


def send_message(chat_id: str, text: str) -> bool:
    """Send a message to a Telegram chat."""
    url = f"{BASE_URL}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def handle_start(chat_id: str) -> None:
    """Handle /start command."""
    send_message(chat_id, (
        "🟢 <b>NQTS Bot Connected</b>\n\n"
        "Commands:\n"
        "/status — System status\n"
        "/positions — Active positions\n"
        "/alerts — Recent alerts\n"
        "/help — Command list\n\n"
        "You will receive CRITICAL and EMERGENCY alerts automatically."
    ))


def handle_status(chat_id: str) -> None:
    """Handle /status command — read-only system check."""
    try:
        import urllib.request as req
        resp = req.urlopen("http://127.0.0.1:8080/api/health", timeout=5)
        data = json.loads(resp.read())
        status = "🟢 Connected" if data.get("mt5_connected") else "🔴 Disconnected"
        send_message(chat_id, (
            f"📊 <b>System Status</b>\n\n"
            f"MT5: {status}\n"
            f"Uptime: {data.get('uptime_seconds', 0):.0f}s\n"
            f"Bars processed: {data.get('bars_processed', 0)}\n"
            f"Signals: {data.get('signals_emitted', 0)}\n"
            f"Kill switch: {'🔴 ACTIVE' if data.get('kill_switch_active') else '🟢 Off'}"
        ))
    except Exception:
        send_message(chat_id, "🔴 Dashboard unreachable")


def handle_positions(chat_id: str) -> None:
    """Handle /positions command — show active positions."""
    send_message(chat_id, "📋 <b>Active Positions</b>\n\n<i>Position data available when runtime is active.</i>")


def handle_alerts(chat_id: str) -> None:
    """Handle /alerts command — show recent alerts."""
    send_message(chat_id, "🔔 <b>Recent Alerts</b>\n\n<i>Alert history available when runtime is active.</i>")


def handle_help(chat_id: str) -> None:
    """Handle /help command."""
    send_message(chat_id, (
        "📖 <b>NQTS Bot Commands</b>\n\n"
        "/start — Welcome & setup\n"
        "/status — System health\n"
        "/positions — Active trades\n"
        "/alerts — Recent alerts\n"
        "/help — This message\n\n"
        "Alerts are sent automatically for:\n"
        "• CRITICAL — SL mismatches, circuit breaker\n"
        "• EMERGENCY — system failures\n"
        "• WARNING — risk limit warnings"
    ))


def handle_message(message: dict) -> None:
    """Route incoming message to appropriate handler."""
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    # Only respond to allowed chat
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    if text == "/start":
        handle_start(chat_id)
    elif text == "/status":
        handle_status(chat_id)
    elif text == "/positions":
        handle_positions(chat_id)
    elif text == "/alerts":
        handle_alerts(chat_id)
    elif text == "/help":
        handle_help(chat_id)
    elif text.startswith("/"):
        send_message(chat_id, "Unknown command. Use /help for available commands.")


def poll_loop() -> None:
    """Main polling loop."""
    global _last_update_id
    print(f"NQTS Telegram bot polling (token={BOT_TOKEN[:10]}...)")
    while True:
        updates = get_updates(offset=_last_update_id + 1)
        for update in updates:
            _last_update_id = update.get("update_id", _last_update_id)
            message = update.get("message")
            if message:
                handle_message(message)
        time.sleep(1)


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        exit(1)
    poll_loop()
