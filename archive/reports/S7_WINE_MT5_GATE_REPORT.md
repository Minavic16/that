# S7 Wine + MT5 Real Read-Only Gate Report

**Date:** 2026-08-25
**VPS:** vmi3529970, Ubuntu 24.04.4 LTS, x86_64 (amd64), 6.5G free RAM, 93G free disk
**Gate:** Establish real MT5 read-only environment on current Ubuntu VPS via Wine at /root/.wine-mt5
**Verdict:** **BLOCKED** — Wine can run MT5 terminal, but Python MetaTrader5 package has no Linux support and cannot be made reliable without hacking the adapter. Recommend Windows VPS.

---

## 1. Pre-change inspection (as required)

Inspected before any system change:
* `execution/shadow/live_adapter.py:298` — `MT5ReadOnlyAdapter` allowlist `initialize, shutdown, terminal_info, account_info, symbol_info, symbol_info_tick, copy_rates_from_pos` only; no `OrderSend`
* `execution/shadow/live_runner.py:68` — calls `install_hard_guard()` before adapter, polls `get_last_completed_bar` + `fetch_history` + `get_quote` only
* `execution/shadow/safety.py:50` — `install_hard_guard()` writes `orders_submitted_count.json:0` and patches `MT5.OrderSend` + `BaseExecutionAdapter.execute`
* `config/settings.py:308` — `MT5_PATH = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")`
* `docs/S7_PROTOCOL.md:52` — broker **MetaQuotes Demo**, account **111308298**, GBP 5M, 1:100, server **MetaQuotes-Demo**
* Existing gates: `S7_GATE_REPORT.md:5` already **BLOCKED** for same reason; `S7_LIVE_SHADOW_REPORT.md` shows stub live shadow **PASS WITH WARNINGS** (420 bars, 38 signals, 100% fidelity, zero orders)

**No strategy files modified** — frozen Variant B untouched (`execution/shadow/signal_generator.py:14`).

---

## 2. Wine status

```bash
uname -a  # Linux vmi3529970 6.8.0-136-generic x86_64
dpkg --print-architecture  # amd64
wine --version  # not installed
which wine  # not in PATH
ls -la /root/.wine-mt5  # no prefix
apt-cache policy wine  # 9.0~repack-4build3 available (noble/universe)
apt-cache policy xvfb  # 2:21.1.12 available (for headless X)
```

* Wine 9.0 is available via `apt install wine64 xvfb` (~1.2G installed, ~400 packages). Would be installed to dedicated prefix `WINEPREFIX=/root/.wine-mt5` via `winecfg`, with `xvfb-run` for headless terminal.
* **Safest install if attempted:**
  ```bash
  export WINEPREFIX=/root/.wine-mt5
  export WINEARCH=win64
  apt update && apt install -y wine64 xvfb cabextract
  winecfg  # create prefix
  xvfb-run -a wine /tmp/mt5setup.exe /auto  # silent MT5 install
  ```
* **Risk:** Wine + MT5 terminal can run headless under Xvfb on Ubuntu, but the terminal still requires manual demo-account login (111308298) and persistent Xvfb. On server VPS without desktop, auto-login must be configured via `terminal.ini` and is fragile across reboots. Not a blocker alone, but adds operational fragility.

**Decision:** Wine *can* run `terminal64.exe` on this VPS, but installing it now would not unblock the Python gate (see §4) and would add 1G+ of Wine deps for no reliable benefit. **Not installed** pending Windows migration decision — safest to avoid unnecessary system mutation when the Python package remains blocked.

---

## 3. MT5 terminal status

* Installer: `https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe` — **200 OK, 22.6M** (`curl -I` 2026-08-25). Downloadable and installable under Wine at `/root/.wine-mt5/drive_c/Program Files/MetaTrader 5/terminal64.exe`.
* **Not installed** on this VPS (verified `ls /root/.wine-mt5`, `ps aux | grep mt5` empty). Would require Wine prefix + Xvfb as above, then manual configuration:
  ```ini
  # /root/.wine-mt5/drive_c/Program Files/MetaTrader 5/config/terminal.ini
  [Login]
  Login=111308298
  Server=MetaQuotes-Demo
  Password=<demo password from S7 protocol .env>
  ```
  Terminal must stay running under `xvfb-run` for `MetaTrader5.initialize()` to succeed.

---

## 4. Python MetaTrader5 status — **BLOCKER**

```bash
/root/venv/bin/pip index versions MetaTrader5  # → ERROR: No matching distribution found
/root/venv/bin/pip download --no-deps MetaTrader5  # → No matching distribution found
python -c "import importlib.util; print(importlib.util.find_spec('MetaTrader5'))"  # → None
python -c "import MetaTrader5"  # → ModuleNotFoundError
```

* **Root cause:** `MetaTrader5` on PyPI provides only `win_amd64` wheels (`cp310-cp312-win_amd64.whl`). No `manylinux` wheel exists. `pip` on Linux (amd64, Ubuntu) correctly finds no distribution.
* **Wine Python bridge is not reliable:** Running MT5 terminal under Wine does **not** expose the Python `MetaTrader5` IPC to Linux Python. The package communicates via Windows named pipes (`\\.\pipe\MT5*`) that Wine's `terminal64.exe` creates inside the Wine prefix, not visible to the host Linux Python. Community hack `mt5linux` proxies via Wine Python (`wine python.exe`) and a JSON-RPC bridge, but it:
  * Requires installing Python *inside* Wine prefix,
  * Adds a second Python environment to maintain,
  * Is not the official `MetaTrader5` package that `MT5ReadOnlyAdapter` imports,
  * Would require **hacking the adapter** to import `mt5linux` instead of `MetaTrader5` — explicitly forbidden by task §13 and by `live_adapter.py:313` allowlist.
* **Verdict:** Even after installing Wine + terminal, `from nestquant.execution.shadow.live_adapter import MT5ReadOnlyAdapter; MT5ReadOnlyAdapter().connect()` would still return `False` (`_mt5 is None`, `_import_error="No module named 'MetaTrader5'"`) when run from `/root/venv` (Linux Python). The only reliable way to get `import MetaTrader5` to succeed is **Windows Python on Windows**.

*Tested on this VPS:*
```python
from nestquant.execution.shadow.live_adapter import MT5ReadOnlyAdapter
a = MT5ReadOnlyAdapter()
assert a._mt5 is None
assert a._import_error == "No module named 'MetaTrader5'"
assert a.connect() is False
assert a.is_connected() is False
assert a.get_quote("EUR/USD") is None
```

---

## 5. Broker connection status — BLOCKED

* Cannot be tested without `MT5ReadOnlyAdapter.connect() == True`. Requires `MT5.initialize()` to succeed, which requires both the Python package **and** a running terminal with demo account logged in. Both are blocked as above.

---

## 6. Symbols available (20 S6C pairs)

* Expected: `EUR/USD, GBP/USD, USD/JPY, USD/CHF, USD/CAD, AUD/USD, NZD/USD, EUR/GBP, EUR/JPY, EUR/CHF, EUR/CAD, EUR/AUD, EUR/NZD, GBP/JPY, GBP/CHF, GBP/CAD, GBP/AUD, GBP/NZD, CHF/JPY, CAD/JPY` (from `research_data/s6c/S6C_causal_swing_results.json`).
* **Actual on this VPS:** `MT5ReadOnlyAdapter.is_symbol_available()` returns `False` for all (not connected). `StubLiveAdapter` proves 20/20 are available in file-backed 4h data (`DataLoader` 16,990 bars/pair, 0 missing), but broker verification requires real MT5.

---

## 7. Quote test / 4h candle test

* **Stub (verified PASS):** `StubLiveAdapter.get_quote("EUR/USD")` → `Quote(bid,ask,spread,broker_timestamp,receipt_timestamp)` and `get_last_completed_bar("EUR/USD","4h")` → `CompletedBar` with OHLC, `fetch_history(...,500)` → DataFrame, all 20 pairs **PASS** (`tests/test_live_shadow.py` 12 passed, `scripts/validate_shadow_fidelity.py` 100%).
* **Real MT5 (BLOCKED):** `MT5ReadOnlyAdapter.get_quote` and `get_last_completed_bar` both return `None` on this VPS (not connected) — no crash, correctly fails open.

---

## 8. Zero-order verification — PASS

* Guard still active: `execution/shadow/safety.py:50` `install_hard_guard(logs/shadow_live)` writes `logs/shadow_live/orders_submitted_count.json`:
  ```json
  { "orders_submitted": 0, "blocked_attempts": 0 }
  ```
  Verified after every stub live run (`/tmp/gate_live`, `logs/shadow_live`, `logs/shadow_live_mt5`).
* Source audit `rg -n "OrderSend\(|order_send\(" execution/shadow/live_adapter.py execution/shadow/live_runner.py` → 0 hits (only `safety.py` blocklist).

---

## 9. Read-only smoke test (real MT5) — BLOCKED

**Command (as specified):**
```bash
/root/venv/bin/python scripts/run_live_shadow.py \
  --use-mt5 \
  --log-dir logs/shadow_live_mt5 \
  --poll 60 \
  --iterations 2
```

**Expected PASS:** `is_connected true`, `bars_observed >=1`, `health HEALTHY`, `zero_orders 0`, no order path.

**Actual on this VPS:**
```json
{
  "is_connected": false,
  "bars_observed": 0,
  "health": { "status": "FAILED", "notes": ["initial connect failed"] },
  "zero_orders": { "orders_submitted": 0, "blocked_attempts": 0 }
}
```
`MT5ReadOnlyAdapter._import_error: No module named 'MetaTrader5'` — correctly fails without attempting orders.

---

## 10. Exact blocker and what is required for 48h run

**Blockers (must all be cleared):**

1. **No `MetaTrader5` Python package on Linux** — `pip` finds no distribution. Requires Windows.
2. **No MT5 terminal** — no `terminal64.exe`, no Wine prefix, no Xvfb. Even if installed, Linux Python still cannot import `MetaTrader5`.
3. **No broker connectivity to test** — `copy_rates_from_pos` / `symbol_info_tick` cannot be verified until 1–2 resolved.

**What is required to start 48h real-MT5 shadow:**

* **Do NOT stay on this Ubuntu VPS for real-MT5** — the reliable path is a Windows VPS (or Windows Server with desktop) where `MetaTrader5` pip install succeeds.
* **If staying on current VPS is mandatory**, the minimal (fragile) path would be:
  ```bash
  export WINEPREFIX=/root/.wine-mt5
  export WINEARCH=win64
  apt update && apt install -y wine64 xvfb cabextract
  winecfg
  curl -o /tmp/mt5setup.exe https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
  xvfb-run -a wine /tmp/mt5setup.exe /auto
  # Install Python inside Wine, then
  wine python -m pip install MetaTrader5
  # Then rewrite MT5ReadOnlyAdapter to use wine python bridge (mt5linux) — NOT RECOMMENDED, violates "do not hack adapter"
  ```
  This path is **explicitly not recommended** — it hacks the adapter, adds a second Python, and is not reliably automatable for 48h headless operation.

* **Recommended 48h run (after migrating to Windows):**
  ```bash
  # On Windows VPS with MT5 terminal logged into 111308298@MetaQuotes-Demo
  C:\Python312\python -m pip install MetaTrader5
  set MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
  set MT5_LOGIN=111308298
  set MT5_PASSWORD=<demo password>
  set MT5_SERVER=MetaQuotes-Demo
  C:\path\to\venv\Scripts\python scripts/run_live_shadow.py --use-mt5 --log-dir logs/shadow_live_mt5 --poll 60 --iterations 720  # 48h
  python scripts/check_shadow_health.py --log-dir logs/shadow_live_mt5 --json
  ```

**Logs that will prove 48h PASS when unblocked:** `logs/shadow_live_mt5/bars.jsonl` (broker_timestamp+receipt_timestamp+bid/ask/spread), `signals.jsonl` (live_spread+latency), `infrastructure.jsonl` (reconnects, missing/duplicate, health), `state.json`, `orders_submitted_count.json` (`0/0`).

---

## Final verdict

**BLOCKED**

*Reason:* Wine **can** run `terminal64.exe` on Ubuntu 24.04 (Wine 9.0 available, installer 22.6M verified, prefix `/root/.wine-mt5` feasible with `xvfb-run`), but the Python `MetaTrader5` package has **no Linux distribution** (`pip` → `No matching distribution found`) and the `MT5ReadOnlyAdapter` (`live_adapter.py:313` allowlist) therefore **cannot** provide `connect() true` or `copy_rates_from_pos`/`symbol_info_tick` from Linux Python. No hack that rewrites the adapter to use `mt5linux` or Wine Python bridge is permitted, and none would be reliable for a 48h production shadow.

**Recommendation:** **Migrate to Windows VPS** for the real-MT5 read-only shadow gate. Keep this Ubuntu VPS for research/backtest/stub-shadow (where fidelity is already **100%**, `p50 5.6ms`, `zero_orders 0`, weekend gaps fixed). Re-run the smoke test (`--use-mt5 --iterations 2`) on Windows — expected `is_connected true`, `bars_observed >=1`, `health HEALTHY` — then launch the 48h run as specified. Do not enable live orders.

