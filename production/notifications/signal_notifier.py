"""
NQTS Signal Notifier — Sends signal alerts to Telegram.

Called by the shadow runner when a new signal is generated.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Load from .env.telegram if env vars not set
_env_file = Path("/root/that/.env.telegram")
if not _env_file.exists():
    _env_file = Path("/root/nestquant/.env.telegram")
if _env_file.exists() and not BOT_TOKEN:
    for line in _env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == "TELEGRAM_BOT_TOKEN":
                BOT_TOKEN = v.strip()
            elif k.strip() == "TELEGRAM_CHAT_ID":
                CHAT_ID = v.strip()
    BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_signal_alert(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    atr: float,
    latency_ms: float,
    signal_id: str,
    broker_timestamp: str,
) -> bool:
    """Send a signal alert to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        return False

    emoji = "🟢" if direction == "BUY" else "🔴"
    text = (
        f"{emoji} <b>{direction} {symbol}</b>\n"
        f"Entry: {entry:.5f}\n"
        f"SL: {sl:.5f} | TP: {tp:.5f}\n"
        f"ATR: {atr:.6f} | Latency: {latency_ms:.1f}ms\n"
        f"Time: {broker_timestamp}\n"
        f"ID: {signal_id[:12]}..."
    )

    try:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"[SignalNotifier] Failed to send alert: {e}")
        return False


def send_risk_block_alert(reason: str) -> bool:
    """Send a risk block alert to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        return False

    text = (
        f"⚠️ <b>RISK BLOCK</b>\n"
        f"Reason: {reason}\n"
        f"Time: {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    try:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"[SignalNotifier] Failed to send risk block alert: {e}")
        return False


def send_circuit_breaker_alert(breaker: str, status: str, reason: str) -> bool:
    """Send a circuit breaker alert to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        return False

    emoji = "🔴" if status == "PAUSED" else "🟢"
    text = (
        f"{emoji} <b>CIRCUIT BREAKER</b>\n"
        f"Breaker: {breaker}\n"
        f"Status: {status}\n"
        f"Reason: {reason}\n"
        f"Time: {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    try:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"[SignalNotifier] Failed to send breaker alert: {e}")
        return False


def send_health_alert(status: str, reason: str) -> bool:
    """Send a system health alert to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        return False

    emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(status, "⚪")
    text = (
        f"{emoji} <b>SYSTEM HEALTH: {status}</b>\n"
        f"Reason: {reason}\n"
        f"Time: {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    try:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok", False)
    except Exception as e:
        print(f"[SignalNotifier] Failed to send health alert: {e}")
        return False
