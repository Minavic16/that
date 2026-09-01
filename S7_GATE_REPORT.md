# S7 NEXT GATE — Real-MT5 Read-Only Shadow Readiness

**Date:** 2026-08-25
**Gate:** Fix weekend gaps + verify real-MT5 read-only adapter + 48h run readiness
**Verdict:** **BLOCKED** — real-MT5 read-only path cannot be exercised on this VPS (Linux, no MT5). Stub read-only live shadow is PASS.

---

## 1. Weekend gap fix — PASS

**Problem:** `LiveShadowRunner` counted normal Fri 20:00 → Sun 20:00 FX market closure (48h = 11–12×4h bars) as `missed_bars` (154 across 20 pairs in demo `logs/shadow_live` with `--history-bars 60 --iterations 30`).

**Fix:** `execution/shadow/live_runner.py:119` new `_is_weekend_gap(expected, actual)` — 40–60h gap spanning Sat/Sun is logged as `INFO market closure` with `NO_IMPACT`, not counted as `missed`. `validate_gaps(...,20.0)` already suppresses weekend gaps in `ShadowRunner` (`execution/shadow/runner.py:206`).

**Verification:**
```bash
rm -rf /tmp/gate_live && /root/venv/bin/python scripts/run_live_shadow.py --log-dir /tmp/gate_live --history-bars 60 --poll 0.02 --iterations 20
# before fix: missed 154, health DEGRADED (gaps 14)
# after fix:  missed 0, health HEALTHY, gaps 0
```
Evidence: `/tmp/gate_live` → `missed 0, health HEALTHY` (see gate checks below). Historical fidelity still 100% (`scripts/validate_shadow_fidelity.py`).

---

## 2. MT5ReadOnlyAdapter verification — BLOCKED (no MT5 on VPS)

**Probe (this VPS):**
```bash
/root/venv/bin/python -c "import importlib.util; print(importlib.util.find_spec('MetaTrader5'))"
# → None
/root/venv/bin/pip list | grep -i mt5  # → no package
ls /opt/mt5* /root/*.exe /mnt/c/Program\ Files/MetaTrader*  # → no files
ps aux | grep mt5  # → no process
uname -a  # → Linux vmi3529970 6.8.0 x86_64 Ubuntu 24.04
/root/venv/bin/python -c "import MetaTrader5"  # → ModuleNotFoundError
```

**Adapter implementation:** `execution/shadow/live_adapter.py:298` `MT5ReadOnlyAdapter`
* Allowlist `_ALLOWLIST = ("initialize","shutdown","terminal_info","account_info","symbol_info","symbol_info_tick","symbol_select","copy_rates_from_pos","copy_rates_range","copy_ticks_range","last_error")` — **only** `copy_rates_from_pos` (`live_adapter.py:391`) and `symbol_info_tick` (`live_adapter.py:369`) are actually called.
* Forbidden `FORBIDDEN_ORDER_NAMES = ("OrderSend","order_send", ...)` — `assert_adapter_source_is_readonly` checks source contains no call; `safety.py:30` lists blocked attrs.
* Smoke test on this VPS:
  ```python
  from nestquant.execution.shadow.live_adapter import MT5ReadOnlyAdapter
  a = MT5ReadOnlyAdapter()
  a._mt5 is None  # → True (no package)
  a.connect()  # → False
  a.get_quote("EUR/USD")  # → None (no crash)
  a.get_last_completed_bar("EUR/USD")  # → None
  ```
  Result: `is_connected() false`, all reads return `None`, **no OrderSend touched**, hard guard file stays `0/0`.

**Conclusion:** `MT5ReadOnlyAdapter` is correctly implemented as read-only (verified `rg -n "OrderSend\("` only in `safety.py` blocklist), but **cannot be exercised against a real broker** on this VPS because the MT5 Python package and terminal are not installed and are Windows-only.

---

## 3. Hard zero-order guard — PASS

* `execution/shadow/safety.py:50` `install_hard_guard(log_dir)` called before any adapter in `LiveShadowRunner.__init__` (`live_runner.py:68`). Writes `logs/shadow_live/orders_submitted_count.json` with `{"orders_submitted":0,"blocked_attempts":0}`, patches `MT5.OrderSend` to `OrderSubmissionBlocked` if MT5 present, and monkey-patches `BaseExecutionAdapter.execute` to terminate.
* Every live run verifies `verify_zero_orders()` (`live_runner.py:346`) — logs `CRITICAL` if `orders_submitted !=0`. Evidence after all runs:
  ```json
  { "orders_submitted": 0, "blocked_attempts": 0 }
  ```
  (`logs/shadow_live/orders_submitted_count.json`, `/tmp/gate_live/orders_submitted_count.json`).
* Source audit: `rg -n "OrderSend\(|order_send\("` across `execution/shadow/live_adapter.py` and `live_runner.py` → 0 hits (only `safety.py` blocklist).

---

## 4. Real-MT5 read-only connectivity smoke test — BLOCKED

**Executed:**
```bash
/root/venv/bin/python - <<'PY'
from nestquant.execution.shadow.live_adapter import MT5ReadOnlyAdapter
a = MT5ReadOnlyAdapter()
print(a.connect(), a.is_connected(), a._import_error)
PY
# → False False "No module named 'MetaTrader5'"
```

**Expected for PASS:** `connect() true`, `is_connected() true`, `get_quote("EUR/USD")` returns `Quote(bid,ask,spread,broker_timestamp,receipt_timestamp)`, `get_last_completed_bar` returns `CompletedBar` with 4h OHLC, `fetch_history` returns DataFrame with 500 bars, all with `receipt - broker <10s` for recent bar.

**Actual on this VPS:** All reads return `None` due to missing MT5 — **smoke test correctly fails open** (no crash, no order). This is the blocker.

---

## 5. Logging completeness — PASS (stub-verified)

Live runner logs per `live_runner.py:244`:
* `bars.jsonl` — `timestamp, symbol, open/high/low/close/volume/spread, atr_14, swing_high/low, broker_timestamp, receipt_timestamp, bid, ask`
* `signals.jsonl` — via `logger.py:145` `log_live_signal` — `signal_id, timestamp, symbol, direction, strategy_params{lookback5, atr14, sl2.0, rrr3.5}, swing_level, signal_bar_close, expected_entry, expected_sl, expected_tp, atr_at_signal, spread_at_signal, broker_timestamp, receipt_timestamp, bid, ask, live_spread, generation_latency_ms, policy_version s7-shadow-v1`
* `infrastructure.jsonl` — `STARTUP, RECONNECT, DUPLICATE, ERROR missed, WARNING clock mismatch, SHUTDOWN, HEALTH`
* `intended_orders.jsonl` — `SHADOW_MARKET` only, never sent
* `lifecycle.jsonl` — simulated exits (if enabled)
* Metrics in runner return: `bars_observed, bars_processed, signals_generated, duplicate_signals, missed_bars, spread_distribution{min,max,p50,p95,mean}, signal_latency_ms{p50,p95,p99,mean}, reconnects, crashes, health_failures, clock_mismatches, broker_discrepancies, zero_orders, health`

Verified in `logs/shadow_live/bars.jsonl` (420 lines, 38 signals, p50 5.6ms p95 17.0ms) and `/tmp/gate_live` (350 bars, 0 missed after weekend fix).

---

## 6. Tests — PASS

```bash
/root/venv/bin/python -m pytest tests/test_live_shadow.py tests/test_shadow.py -q
# → 34 passed in 23s

/root/venv/bin/python -m pytest tests/test_live_shadow.py::TestLiveShadowStaleFeed -v  # stale handling
/root/venv/bin/python -m pytest tests/test_live_shadow.py::TestLiveShadowClockMismatch -v  # skew
# All 8 scenarios covered:
# startup, reconnect, missing candle, duplicate candle, process restart, kill switch, stale feed, clock mismatch
```

Historical fidelity still `scripts/validate_shadow_fidelity.py` → **100.00% (22444/22444) PASS**.

---

## 7. What is required to start the 48-hour real-MT5 shadow

**Do NOT start until all are met:**

1. **Windows environment** — MT5 Python package (`MetaTrader5`) is Windows-only. Options:
   * Migrate to Windows VPS with MT5 terminal, or
   * Install Wine + MT5 terminal on this Ubuntu VPS (`apt install wine64`, download `mt5setup.exe`, install to `~/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe`, set `MT5_PATH`).
2. **MT5 Python package:** `/root/venv/bin/pip install MetaTrader5` (requires Python 3.10+ on Windows, or via Wine Python).
3. **Broker account:** MetaQuotes Demo `111308298` (GBP, 1:100, `MetaQuotes-Demo`) per `docs/S7_PROTOCOL.md:52` — credentials in `.env` (`MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH`); `config/settings.py:308` reads `MT5_PATH`.
4. **Network:** Outbound TCP 443 to `mt5.metaquotes.net` / demo server; firewall must allow.
5. **Symbol availability:** Verify 20 pairs (`EUR/USD … CAD/JPY`) via `MT5ReadOnlyAdapter.is_symbol_available()` for `4h`.
6. **Smoke test pass:** `/root/venv/bin/python scripts/run_live_shadow.py --use-mt5 --log-dir logs/shadow_live_mt5 --poll 60 --iterations 2` must return `is_connected true`, `bars_observed >=1`, `health HEALTHY`, `zero_orders 0/0`.
7. **Log infra:** Ensure `logs/shadow_live_mt5/` is on persistent disk, `state.json` and `KILL` handling via `KillSwitch` (`execution/shadow/kill_switch.py:14`).
8. **Service:** `systemd` unit with `Restart=always`, `Environment=NESTQUANT_SKIP_LIVE_CHECK=1`, `ExecStart=/root/venv/bin/python /root/nestquant/scripts/run_live_shadow.py --use-mt5 --log-dir logs/shadow_live --poll 60`.
9. **48h run command (only after 1–8 pass):**
   ```bash
   rm -rf logs/shadow_live && /root/venv/bin/python scripts/run_live_shadow.py --use-mt5 --log-dir logs/shadow_live --poll 60 --iterations 720  # 720 polls ×60s = 12h per 4h bar ×12 bars = 48h wall
   # Or continuous: /root/venv/bin/python scripts/run_live_shadow.py --use-mt5 --log-dir logs/shadow_live --poll 60 &
   /root/venv/bin/python scripts/check_shadow_health.py --log-dir logs/shadow_live --json
   ```

**Blockers on this VPS (today):**

* **BLOCKER 1 — No MT5 Python package:** `importlib.util.find_spec('MetaTrader5') is None` — install required (Windows/Wine only).
* **BLOCKER 2 — No MT5 terminal:** No `terminal64.exe` at `MT5_PATH`, no Wine — `MT5ReadOnlyAdapter.connect()` returns `False`, all reads `None`.
* **BLOCKER 3 — No broker connectivity to test:** Cannot verify `copy_rates_from_pos` / `symbol_info_tick` against real broker until 1–2 resolved.

**Not blockers (already PASS):** frozen Variant B strategy untouched, weekend gap fix verified, hard zero-order guard enforced, stub live shadow demonstrates all logging/health/kill/restart/duplicate/missing/reconnect/clock handling with `0/0` orders and `100%` historical fidelity.

---

## Final verdict

**BLOCKED**

*Reason:* Real-MT5 read-only gate cannot be completed on this Linux VPS as it lacks the Windows-only `MetaTrader5` package and terminal. The adapter is correctly implemented as read-only (allowlist `copy_rates_from_pos` + `symbol_info_tick` only, hard guard `orders_submitted 0`), and the stub live shadow proves the frozen Variant B pipeline is ready (420 bars, 38 signals, p50 5.6ms, 0 missed after weekend fix, 0 duplicates mishandled, 12/12 live-shadow tests pass, 100% fidelity). The 48-hour real-MT5 shadow must wait until a Windows/Wine MT5 environment is provisioned and the smoke test (`--use-mt5 --iterations 2`) returns `is_connected true` with `HEALTHY`.

**Next step when blockers cleared:** Re-run the smoke test, then launch the 48h real-MT5 read-only shadow (no order path, guard active), and regenerate this report with `S7_LIVE_SHADOW_REPORT.md` fields filled from `logs/shadow_live_mt5`.

