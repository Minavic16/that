# NQTS Post-9 Shadow Replay Audit — Retrospective Hypothetical Execution

**Status:** analysis complete — STOPPED for user review (no implementation changes made)
**Classification:** read-only investigation; descriptive results only
**Generated:** 2026-09-25 (local), from evidence captured 2026-09-24T19:11:28Z

---

## 1. Objective

Answer one question, descriptively and without optimization:

> If each NQTS live-engine signal **after the first nine** had been actually
> executed according to the **current NQTS execution / backtesting rules**,
> what would have happened?

Constraints honored throughout:

- No MT5 orders, no changes to `SHADOW_ONLY`, config, signal generation, risk,
  execution, runner, dashboard, or Telegram.
- No look-ahead, no parameter tuning, no cherry-picking, no changes to frozen
  trees (`research/shared/*`, `research/experiments/strategy2/*`,
  `production/*`, `core/*`).
- Analysis-only tooling lives outside frozen architecture
  (`scripts/nqts_shadow_replay/`), clearly identified as such.
- Populations A and B are reported separately and never ranked against
  each other.
- Results are descriptive: **no claims of robustness, profitability, or
  deployment readiness** (small sample, §11).
- Stops after this report.

---

## 2. Environment

| Item | Value |
|---|---|
| Repository | `/root/that` (branch worktree; `/root/nestquant` same tree) |
| Branch | `research/strategy-2` |
| HEAD | `008b846a93006d716f0b6c1d87ea56f9658bd229` ("fix(research): reconcile phase3 evaluation contracts") |
| Python | 3.12.3 |
| Live system | S7 read-only live shadow, `production/deployment/run_live_shadow.py` via `nestquant-shadow.service`, `--use-wine-flask --log-dir /root/nestquant/logs/shadow_live --poll 60`, `enable_execution=False` |
| VPS | `169.58.230.92` (read-only `ssh`/`scp` used for evidence; no commands that modify state) |
| Executor config | `initial_balance=200.0`, `risk_per_trade=CONSTITUTION.risk_per_trade_pct=0.0015` (`live_executor.py:72-73`) |
| Observation window (population B signals) | 2026-09-16T21:00:22Z → 2026-09-24T19:11:24Z |
| Market data available | bar labels 2026-08-28T16:00 → 2026-09-24T16:00 (20 pairs, 74–75 bars each, 1481 records) |
| Last market close covered | 2026-09-24T17:00:00Z (true UTC) |
| Runner state updated | 2026-09-24T19:11:28.548091Z; counters `{bars_processed: 1481, signals_emitted: 21}` |
| Health at capture | `metrics.json`: `health_status GREEN`, `execution_mode SHADOW`, `mt5_connected true`, account metrics 0.0 (fail-closed: real balance unknown) |

---

## 3. Population definition

Source of truth: chronological record order in `signals.jsonl` (identical to
intended-order wall-clock order — verified monotonic for all 21 records).

| Population | Signals | Range (wall clock UTC) | Use |
|---|---|---|---|
| **A — first nine** | #1–#9 (n=9) | 2026-09-08T21:00:34 → 2026-09-13T21:01:18 | Excluded from the audit question; replayed only as a clearly-labelled reference with identical method |
| **B — post-first-nine** | #10–#21 (n=12) | 2026-09-16T21:00:22 → 2026-09-24T19:11:24 | **The analyzed population** |

- First excluded signal: **#9 `EUR/JPY SELL`, id
  `230335a9-2b94-42b9-ad3f-ffa41d441b84`, 2026-09-13T21:01:18.107315Z**.
- First included signal: **#10 `EUR/CAD SELL`, id `c1b3690d-1bd1-4d56-bdab-7b09b084783a`, 2026-09-16T21:00:22.100018Z**, signal bar `2026-09-17T00:00`.
- Last included signal: **#21 `EUR/NZD BUY`, id `980d2388-cb6b-45a9-b4e5-eab545ebf450`, 2026-09-24T19:11:24.964336Z**, signal bar `2026-09-24T20:00`.
- Exclusions: exactly 9 (the first nine), reason = designated population boundary.
- Population B composition: 12 signals, 11 unique pairs (EUR/AUD appears
  twice: #13, #16), directions **BUY=4, SELL=8**.
- No same-(pair, bar) duplicate signals in either population; all 21
  `signal_id`s unique.
- Signal bar labels for B: `09-17T00, 09-17T04, 09-18T00, 09-22T00, 09-22T20,
  09-23T00, 09-23T00, 09-23T00, 09-24T00, 09-24T00, 09-24T20, 09-24T20`.

Per-signal status vocabulary used everywhere below:
`signal generated` → `hypothetical executable` → `blocked by rule
(reason)` / `suppressed (pair occupied)` → `outcome (TP | SL | open at
observation end | insufficient data)`.

---

## 4. Data sources (evidence)

Copied read-only from `/root/nestquant/logs/shadow_live/` into
`scripts/nqts_shadow_replay/evidence/` (sha256 recorded):

| File | sha256 (first 16) | Content |
|---|---|---|
| `signals.jsonl` | `f01a3e5e01284be3…` | 21 signal records (all fields incl. `expected_entry/sl/tp`, `atr_at_signal`, partial `bar_open/high/low`) |
| `intended_orders.jsonl` | `8c65e59c2e952e43…` | 21 intended orders (`SHADOW_MARKET`, volume 0.01, requested price = `expected_entry`, submission spread) |
| `bars.jsonl` | `10b797fd39c5bbc0…` | 1481 4H bars ×20 pairs: OHLC, bid, ask, spread, receipt time, swing levels (`atr_14` null at cycles) |
| `state.json` | `7bd2b75cea1f9eb9…` | run_id, last_bar map, counters |
| `metrics.json` | `024dda0f94b1f946…` | health, SHADOW mode, risk params echo |
| `orders_submitted_count.json` | `92b68251f507bf2f…` | `{"orders_submitted": 0, "blocked_attempts": 0}` |

Not copied (not needed): `infrastructure.jsonl` (91 MB health stream),
`api_access.log` (read-only GETs; inspected remotely: **0 POST entries**),
`runner.log` (empty), `validation/` (empty).
**No `lifecycle.jsonl` exists** → the live system holds no prior exit/outcome
records for any signal (shadow exits were never executed or logged).

Frozen components imported unchanged by the analysis script:

- `nestquant.research.shared.execution.{ExecutionSimulator, BacktestConfig,
  SignalIntent, Trade}` — canonical fill/exit/P&L math.
- `nestquant.production.execution.risk_guard.{RiskGuard, RiskGuardConfig}` —
  constitution gates as in production.
- `nestquant.core.contracts.execution_contracts.{Direction, TradeIntent}`,
  `nestquant.core.tooling.indicators.session.is_active_session`.
- Rules mirrored (not imported): `live_executor` one-position-per-pair,
  TP→SL→MAX_HOLD→BE ordering (analyzed as sensitivity), `MAX_HOLD_DAYS=7`,
  `BREAKEVEN_RATIO=0.8`.

---

## 5. Execution semantics applied

**Signal bar resolution (fail-closed, proof recorded per signal):**

- Labels are broker-server time mis-tagged `+00:00`: `label = true_open+3h`,
  `true_close = label+1h`, receipt ≈ true close + runner delay.
- Signals fire on the **forming** bar B; `sig_ohlc` is a partial snapshot;
  entry occurs at intended-order wall time (≈ B's true open + ~30 s, except
  late cycles, below).
- Signals #1–#11 carry a valid record timestamp (= B's label, verified in
  bars with open-equality dev=0). Signals **#12–#21 have
  `"timestamp": "NaT"`** (generator index bug). Resolution: find the same-pair
  processed cycle bar whose receipt is within 3 s of the intended order,
  B = cycle label + 4 h grid, then prove it — **open-equality proof** vs the
  completed bar (dev ≤ 1e-5, one quote digit; observed max dev 1e-5) or, for
  #20/#21 (B not yet completed), **continuity proof** `signal.bar_open ==
  cycle.close`. Weekend-crossing grids rejected (none occurred).

**Fills (primary):** frozen `ExecutionSimulator` —
`fill = expected_entry ± spread/2 ± slippage` (half-spread and 0.1 pip
slippage both applied adversely), commission $6/lot on exit, sizing
`balance×0.15% / (|fill−SL|×100000)` floored to **0.01 lot** (asserted equal
to the intended order volume for every opened trade).

**Spread policy:** the cycle tick's `spread = ask−bid` is used when ≤ 5 pips;
15 of 21 cycles recorded 12–50 pips (same-pair median is 0.2 pips; the
artifact appears exactly at receipt moments and disappears in later cycles)
→ those fall back to the frozen default **1.0 pip** and are flagged in the
ledger. Alternative tick-based pricing is reported as S7.

**Exit checks:** on every bar of the pair with `label ≥ B` (entry bar B
included — entry is at B's true open), evaluated at `true_close = label+1h`
in a globally chronological event stream (exit checks processed before
entries at identical times). **SL is checked before TP** (frozen `elif`
ordering; live executor checks TP first → analyzed as S5).

**Entry gates (primary):** production `RiskGuard(RiskGuardConfig(
account_balance=200, max_concurrent_positions=3))`, fully fed
(`update_positions` with replayed positions before each evaluation,
`record_trade_result(pnl, equity=200+cum, slippage=0.1)` on each exit,
`reset_daily()` on UTC date change) — i.e. the constitution limits operating
as designed: 4 trades/day, circuit breakers (WinRateBreaker needs ≥20 trades;
slippage breaker needs 3×>4.8 pip events — neither can trigger in ≤12
trades), 3 concurrent, 3% daily loss, 8% drawdown, sizing, 0.10 lots/pair,
3.0 lots total; plus **`live_executor`'s one-position-per-pair rule**
(evaluated before RiskGuard, as in `live_executor`).

**No session gate** in the live path (session filter exists only in the
research backtest engine) → reported as sensitivity S1.

**USD valuation (derived, clearly labelled):** the frozen core computes P&L
in the pair's **quote currency** with no FX conversion (accepted frozen
behaviour). Quote-unit figures are shown as the canonical frozen output, and
every aggregate is additionally converted to USD using the same `bars.jsonl`
closing rates at exit time (`EUR/USD, GBP/USD, AUD/USD, NZD/USD, USD/CHF,
USD/CAD, USD/JPY`; last bar ≤ exit label). R-multiples are unit-consistent
within each trade (both P&L and risk in quote currency).

**Sensitivities (all on population B unless noted):**

| Id | Variant |
|---|---|
| S1 | Research-engine session gate (`is_active_session` on label hour 7–21, Fri≥17 blocked, weekends) applied to entries **and** exit checks |
| S2 | `max_open_trades = 1` (frozen `BacktestConfig` default) |
| S3 | Entry bar B excluded from exit checks (frozen index-order convention) |
| S4 | Passive flags only: live MAX_HOLD (42×4 h label bars) and breakeven armament (0.8×ATR); P&L effect not quantified (order-modification path not replayed) |
| S5 | TP-before-SL recount on first-touch bars where both levels sit inside one bar (live vs frozen ordering) |
| S6 | A+B interleave (budget interaction between populations) |
| S7 | Live market-order fill at cycle tick (BUY=ask, SELL=bid), zero modeled cost |
| S8 | Fill at requested `expected_entry`, zero modeled cost |
| S9 | RiskGuard **as currently wired in the live runner** (stateful feeds never called → those gates inert; only one-per-pair and sizing remain) |

---

## 6. Trade ledger (primary replay, all 21 signals)

Net P&L shown as `quote / USD-est`. R = P&L ÷ initial risk (quote units).
Entry = frozen fill; "—" = never opened. Durations in hours (true UTC).

| # | Pop | Signal time UTC | Pair | Dir | Entry | SL | TP | Lot | Exit time UTC | Reason | Net P&L (quote/USD) | R | Dur | Status / data quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 2026-09-08T21:00:34 | EUR/GBP | SELL | 0.85814 | 0.85989 | 0.85229 | 0.01 | 2026-09-10T17:00 | sl | −1.7982 / −2.43 | −1.03 | 44.0 | CLOSED · COMPLETE |
| 2 | A | 2026-09-08T21:00:34 | EUR/CHF | SELL | 0.93940 | 0.94243 | 0.92906 | 0.01 | 2026-09-09T17:00 | sl | −3.0827 / −3.81 | −1.02 | 20.0 | CLOSED · COMPLETE |
| 3 | A | 2026-09-08T21:00:34 | EUR/CAD | SELL | 1.60054 | 1.60481 | 1.58585 | 0.01 | 2026-09-09T17:00 | sl | −4.3235 / −3.13 | −1.01 | 20.0 | CLOSED · COMPLETE |
| 4 | A | 2026-09-08T21:00:35 | EUR/AUD | SELL | — | 1.61370 | 1.59182 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 5 | A | 2026-09-09T21:00:45 | NZD/USD | SELL | — | 0.58739 | 0.57024 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: daily loss 3.70% ≥ 3.00% |
| 6 | A | 2026-09-09T21:00:46 | EUR/CHF | SELL | — | 0.94222 | 0.92669 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: daily loss 3.70% ≥ 3.00% |
| 7 | A | 2026-09-09T21:00:47 | GBP/AUD | SELL | — | 1.87869 | 1.85331 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: daily loss 3.70% ≥ 3.00% |
| 8 | A | 2026-09-13T21:00:14 | EUR/GBP | SELL | 0.85726 | 0.85917 | 0.85086 | 0.01 | 2026-09-17T13:00 | sl | −1.9566 / −2.62 | −1.03 | 88.0 | CLOSED · COMPLETE |
| 9 | A | 2026-09-13T21:01:18 | EUR/JPY | SELL | 178.07094 | 179.10186 | 174.46300 | 0.01 | 2026-09-15T17:00 | sl | −1030.97 / −6.65 | −1.00 | 44.0 | CLOSED · COMPLETE (quote=JPY) |
| **10** | **B** | 2026-09-16T21:00:22 | EUR/CAD | SELL | 1.60295 | 1.60804 | 1.58541 | 0.01 | 2026-09-18T09:00 | sl | **−5.1389 / −3.67** | −1.01 | 36.0 | CLOSED · COMPLETE |
| **11** | **B** | 2026-09-17T01:00:28 | CAD/JPY | BUY | 111.66305 | 111.02867 | 113.88317 | 0.01 | — | — | unreal. ind. +704.89¥ / **+4.44 USD** | — | — | **OPEN AT OBSERVATION END** · 34 check bars, BE armed 09-18T04 |
| **12** | **B** | 2026-09-17T21:00:25 | GBP/CHF | SELL | 1.10038 | 1.10482 | 1.08510 | 0.01 | — | — | unreal. ind. +5.37 / **+6.49 USD** | — | — | **OPEN AT OBSERVATION END** · 29 bars, BE armed 09-21T16 |
| **13** | **B** | 2026-09-21T21:00:15 | EUR/AUD | SELL | 1.60857 | 1.61343 | 1.59182 | 0.01 | 2026-09-22T05:00 | sl | **−4.9120 / −3.50** | −1.01 | 8.0 | CLOSED · COMPLETE |
| **14** | **B** | 2026-09-22T17:00:20 | CHF/JPY | BUY | 191.68905 | 190.64968 | 195.32663 | 0.01 | — | — | unreal. ind. +171.90¥ / **+1.08 USD** | — | — | **OPEN AT OBSERVATION END** · 12 bars, BE armed 09-24T08 |
| 15 | B | 2026-09-22T21:00:46 | USD/CHF | SELL | — | 0.82455 | 0.80647 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 16 | B | 2026-09-22T21:00:58 | EUR/AUD | SELL | — | 1.61317 | 1.59095 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 17 | B | 2026-09-22T21:01:00 | GBP/AUD | SELL | — | 1.87983 | 1.85073 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 18 | B | 2026-09-23T21:00:44 | EUR/CHF | SELL | — | 0.94082 | 0.92678 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 19 | B | 2026-09-23T21:00:45 | GBP/JPY | SELL | — | 210.47573 | 206.15695 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 20 | B | 2026-09-24T19:11:21 | EUR/GBP | BUY | — | 0.85885 | 0.86704 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |
| 21 | B | 2026-09-24T19:11:24 | EUR/NZD | BUY | — | 2.00068 | 2.04157 | 0.01 | — | — | — | — | — | NOT OPENED · risk gate: max concurrent 3/3 |

Open-trade marks are indicative only (last available bar close) and are
**never counted** as wins/losses. Full machine-readable ledger:
`scripts/nqts_shadow_replay/post9_ledger.jsonl` (sha256
`b5f078d2c880029b…`, byte-stable across runs).

**Population B hypothetical trades (primary): 5 opened — 2 completed (both
SL), 3 open at observation end, 7 never opened (constitution concurrent
cap), 0 suppressed by the pair-occupancy rule, 0 session-blocked.**

---

## 7. Aggregate results

### Population B (the audit population), primary rules

| Metric | Value |
|---|---|
| Signals analyzed | 12 |
| Hypothetical trades opened | 5 (2 closed + 3 open) |
| **Summary P&L (realized)** | **−10.05 quote-units = −7.17 USD (−3.58% on $200)** |
| Final balance (realized) | 192.83 USD |
| **Max drawdown** | **7.17 USD = 3.584%** (200 → 192.83; trough 2026-09-22T05:00Z) |
| **Win rate** (closed trades) | **0.0% (0/2)** |
| **Profit factor** | **0.0** (no winning closed trades) |
| Expectancy per closed trade | −3.58 USD (−5.03 quote) |
| Average R | −1.01 (R distribution: −1.01, −1.01) |
| Average hold | 21.99 h; longest 36.0 h |
| Exit reasons | SL 2, TP 0; same-bar SL+TP touches: 0 |
| Loss streak | 2 (win streak 0) |
| Largest loss | −5.14 CAD-units (−3.67 USD) |
| Open trades (indicative, not counted) | +12.01 USD net unrealized |
| Max simultaneous positions / exposure | 3 (cap) / 0.03 lots (limit 3.0) |
| Trades gated off by concurrent cap | 7 of 12 |
| Trades gated off by daily loss / DD / breakers | 0 |

### Population A reference (identical method, fresh state, separate)

| Metric | Value |
|---|---|
| Signals | 9 → 5 opened, 5 closed (all SL), 4 not opened (1 concurrent, 3 daily-loss) |
| Summary P&L | −18.64 USD (−9.32%); by quote: JPY −1030.97, CAD −4.32, CHF −3.08, GBP −3.75 |
| Max drawdown | 9.319% (trough 2026-09-17T13:00Z) |
| Win rate / PF | 0.0% (0/5) / 0.0 |
| Average R | −1.017 |
| Open at end | 0 |

Population A reference is computed only to answer "how would the excluded
signals have looked under the same rules" — the two populations are **not**
compared as better/worse (different periods, different samples; §11).

---

## 8. Equity curve and drawdown (primary, USD-converted)

| Time (true UTC) | Event | Pair | P&L quote | P&L USD | Balance USD | Open |
|---|---|---|---|---|---|---|
| 2026-09-16T21:00:22 | entry | EUR/CAD | — | — | 200.00 | 1 |
| 2026-09-17T01:00:28 | entry | CAD/JPY | — | — | 200.00 | 2 |
| 2026-09-17T21:00:25 | entry | GBP/CHF | — | — | 200.00 | 3 |
| 2026-09-18T09:00:00 | exit_sl | EUR/CAD | −5.14 | −3.67 | 196.33 | 2 |
| 2026-09-21T21:00:15 | entry | EUR/AUD | — | — | 196.33 | 3 |
| 2026-09-22T05:00:00 | exit_sl | EUR/AUD | −4.91 | −3.50 | **192.83** | 2 |
| 2026-09-22T17:00:20 | entry | CHF/JPY | — | — | 192.83 | 3 |

- Max DD = 7.17 USD (3.584%); single monotonic drawdown from the start peak
  of 200 to the 09-22 trough; no recovery within the observation window
  (no realized wins occurred).
- Open positions at observation end carry +12.01 USD indicative unrealized
  P&L (CAD/JPY +4.44, GBP/CHF +6.49, CHF/JPY +1.08) — not part of realized
  equity or DD.
- Realized equity never approached constitution stop levels (daily 3%,
  drawdown 8%): worst day −3.58 USD (1.79%).

---

## 9. Payoff distribution / concentration (primary, closed trades)

| Statistic | Value | Note |
|---|---|---|
| Closed sample | 2 | both losses |
| Winners / losers | 0 / 2 (losing share 100%) | |
| Payoff ratio, median winner/loser | **undefined** | no winners exist |
| Top-1 / top-2 / top-3 share of net profit | **undefined** (no positive net) | |
| Top-1 share of gross profit | undefined (gross profit = 0) | |
| Mean / median trade (USD) | −3.58 / −3.58 USD | |
| Win/loss streaks | 0 / 2 | |
| R-multiples | −1.01, −1.01 (all ≈ one unit of initial risk + commission) | |

Interpretation constraint: with 2 closed trades and zero take-profit exits,
**no payoff concentration or distribution statistics exist to report** — this
is a structural small-sample fact (§11), not a zero-risk finding. The three
open trades have not produced outcomes. Across every pass of the replay
(23 closed trades total across 9 passes, heavily overlapping samples) **every
closed trade exited at its stop loss** — a descriptive observation about this
sample and cost model only.

---

## 10. Overlaps, concurrency, exposure

Primary overlap timeline (constitution cap 3 concurrent):

| Time | New | Open set |
|---|---|---|
| 2026-09-17T01:00:28 | CAD/JPY BUY | EUR/CAD SELL, CAD/JPY BUY |
| 2026-09-17T21:00:25 | GBP/CHF SELL | + GBP/CHF SELL (3 = cap) |
| 2026-09-21T21:00:15 | EUR/AUD SELL | CAD/JPY BUY, GBP/CHF SELL, EUR/AUD SELL (EUR/CAD had closed) |
| 2026-09-22T17:00:20 | CHF/JPY BUY | CAD/JPY BUY, GBP/CHF SELL, CHF/JPY BUY |

- Same-pair overlap: none possible (one-position-per-pair rule; #13/#16 are
  the same pair EUR/AUD but sequential, #16 blocked while #13 held the slot).
- Shared-currency clustering (descriptive): the first three positions were
  long-CAD via two legs (EUR/CAD SELL + CAD/JPY BUY) plus short-GBP
  (GBP/CHF SELL) — no correlation filter exists in RiskGuard or the live
  path (observation only; no filter was simulated).
- Exposure never exceeded 0.03 of the 3.0-lot total limit; per-pair never
  exceeded 0.01 of 0.10. **The binding constraint was the 3-position cap**,
  which suppressed 7 of 12 signals.
- Population A overlapped the start of B (#8 EUR/GBP SELL was open until
  2026-09-17T13:00Z); in the interleave pass (S6) this changed no gate
  outcome for B — B results under interleaving are identical to the
  B-only primary.

---

## 11. Data quality and limitations

**Evidence defects found (flagged per signal in the ledger):**

1. **`"timestamp": "NaT"` on signals #12–#21 (10 of 21).** Resolved by
   receipt-matching + 4-hour grid + open-equality/continuity proofs (max
   deviation 1e-5 = one quote digit). All 21 resolutions verified.
2. **Implausible cycle spread ticks (15 of 21 signals: 12–50 pips vs pair
   median 0.2 pips)** — a quote artifact at receipt moments (bid/ask from
   different quote generations); primary uses frozen 1.0-pip default with a
   ledger flag; S7 prices at the recorded tick instead. Intended-order
   `spread_at_submission` shows the identical artifact (same measurement).
3. **`atr_14` null on every cycle bar in `bars.jsonl`** — signals' own
   `atr_at_signal` used instead (present on all 21).
4. **Late processing cycles:** #8/#9 processed 49 h after their bar closed
   (weekend restart); **#20/#21 processed 2 h 11 min after bar open** (entry
   131 min into B; their signal bar was still incomplete → continuity
   proof; in S1/S9 they are opened seconds before the observation ends, so
   no post-entry market data exists for them).
5. **Bar labels are broker-server time tagged `+00:00`** (true open = label
   −3 h). All event ordering uses true UTC derived from labels/receipts.
6. **No prior outcome data exists** (`lifecycle.jsonl` absent; runner never
   executed trades) — Population A's outcomes here are computed by the same
   replay, not recovered from the system.
7. **Frozen-core accounting:** P&L in quote currency without FX conversion
   (JPY-denominated numbers are ~150× their USD value); USD figures in this
   report are derived valuations using bars' closing FX rates. Daily-loss /
   drawdown gates in the replay therefore also see quote-mixed sums (same as
   frozen backtests would). The one time a loss gate fired (A: 3.70% ≥ 3%)
   it also exceeds 3% after USD conversion (≈4.4%) — outcome robust to units.
8. **Real account balance unknown** (metrics show 0.0, fail-closed) →
   runner-configured $200 used for gates, sizing, and equity.
9. **Observation truncation:** market data ends 2026-09-24T17:00Z; 3 trades
   (B) and up to 6 (S9) are open; exit check bars seen per open trade are in
   the ledger (34 / 26 / 12 in primary). Outcomes beyond the window are
   unknowable and excluded from all statistics.
10. **System observations (facts, not proposals):** (a) the live runner never
    calls `RiskGuard.update_positions / reset_daily / record_trade_result`,
    so under today's wiring the stateful gates are inert — captured as S9;
    (b) live exit monitoring parses `signal.timestamp` as position open time,
    which would raise `ValueError("Invalid isoformat string: 'NaT'")` for
    #12–#21; (c) MFE/MAE include the full entry-bar range (intra-bar split
    unavailable); (d) breakeven/MAX_HOLD are reported as flags only (S4) —
    their order-modification path is not replayed, so no P&L claim is made.
11. **Sample size:** 12 signals, 5 trades, 2 outcomes in the audit
    population. Everything in this report is **descriptive**: it establishes
    what would have happened to these specific signals under these specific
    rules, nothing more.

---

## 12. Population A vs B — descriptive comparison (not a ranking)

| Dimension | A reference (first 9) | B analyzed (post-9) |
|---|---|---|
| Window | Sep 8–13 (signals) | Sep 16–24 (signals) |
| Opened / closed | 5 / 5 (all SL) | 5 / 2 closed + 3 open |
| Gated off | 4 (1 concurrent, 3 daily-loss) | 7 (all concurrent cap) |
| Realized P&L | −18.64 USD | −7.17 USD (+12.01 USD open indicative) |
| Max DD | 9.319% | 3.584% |
| Win rate / PF (closed) | 0% / 0.0 | 0% / 0.0 |
| Avg R | −1.017 | −1.01 |
| Distinctive gates that fired | daily-loss cap (3 consecutive rejections) | 3-concurrent cap (7 consecutive rejections) |

Both populations are reported as-is; different periods and samples make any
"better/worse" statement unsupportable (§11).

---

## 13. Sensitivity analysis (population B unless stated)

| Pass | Closed | Open | Not opened | Realized net (USD) | Max DD % (USD) | vs primary |
|---|---|---|---|---|---|---|
| **primary** (constitution, as-designed wiring) | 2 | 3 | 7 | **−7.17** | 3.584 | — |
| S1 session gate (research engine rule) | 0 | 3 | 0 (+9 session-blocked) | 0.00 | 0.0 | only labels in 7–21 h enter (#14, #20, #21); 9 of 12 blocked; no exits realized |
| S2 `max_open_trades=1` | 2 | 1 | 9 | −7.17 | 3.584 | same realized trades; 2 fewer opened |
| S3 entry bar excluded | 2 | 3 | 7 | −7.17 | 3.584 | **identical outcomes** (no exit falls on entry bar) |
| S4 BE / max-hold flags | — | — | — | not quantified | — | BE armed on all 3 open trades; MAX_HOLD(42 bars) reached by #11 (45 bars held); no closed trade reached 42 |
| S5 TP-first vs SL-first | 0 both-touch bars | | | delta = 0 | | live and frozen orderings never diverge in this sample |
| S6 A+B interleave | 7 | 3 | 11 | −25.81 | 12.903 | = A(−18.64) + B(−7.17); no gate interaction |
| S7 tick fill (ask/bid at cycle) | 2 | 3 | 7 | −7.84 | 3.919 | 0.67 USD worse than primary |
| S8 zero-cost fill | 2 | 3 | 7 | −7.10 | 3.548 | 0.07 USD better than primary |
| S9 RiskGuard as currently wired | 6 | 6 | **0** | **−24.26** | **12.128** | all 12 opened (stateful gates inert); 6 closed all SL; worst realized outcome of all passes |
| A reference (separate) | 5 | 0 | 4 | −18.64 | 9.319 | — |

Descriptive reading: outcome range across fill/cost/convention sensitivities
is narrow (−7.10 … −7.84 USD); the two variables that dominate results are
**(i) whether constitution risk limits are actually enforced** (primary −7.17
vs as-wired −24.26) and **(ii) the session filter**, which suppresses 9 of 12
entries under the research-engine rule.

---

## 14. Validation and test results

| Check | Result |
|---|---|
| Determinism (`--verify`: every pass re-run in-process) | **OK** — all 9 passes identical on rerun |
| Determinism (external double-run) | **OK** — `post9_ledger.jsonl` byte-identical (`cmp`), stdout identical |
| Manual hand-checks vs raw bars (≥3 required) | **5 trades verified**: #10 (first-touch SL on 09-18T08 bar, high 1.60805 ≥ SL 1.6080389; earlier 8 bars no touch; MFE 8.9p/MAE 51.0p recomputed), #13 (first-touch SL 09-22T04; MFE 3.4p/MAE 63.1p), #11 (34 bars: no SL/TP touch; BE arm bar 09-18T04 high 112.426 ≥ 111.917 ✓), #12 (0 touches; BE 09-21T16 low 1.09744 ≤ 1.09869 ✓), #14 (no touch; BE 09-24T08 high 192.485 ≥ 192.105 ✓) |
| No look-ahead | exit checks only on bars `label ≥ signal bar`; entry processed at true order time; equal-time events run checks first; MFE/MAE windows start at signal bar |
| Position sizing consistency | every opened trade asserted `lot == 0.01 == intended_order.volume` (also matches `compute_position_size` and `live_executor._compute_lot_size` floor behavior) |
| Signal-parameter fidelity | ledger stores `entry/sl/tp/atr` copied verbatim from `signals.jsonl`; fills derived only from them + documented cost model |
| Risk-block notifications | `send_risk_block_alert` patched to a capture function — 104 captures (52 rejections × 2 verify runs), **0 messages sent** |
| Analysis script I/O audit | imports only stdlib/pandas/nestquant read modules; **no** `requests/urllib/socket/paramiko/ssh/order_send/mt5/POST` usage (grep clean) |
| Frozen trees | `git diff HEAD` on `research/shared`, `research/experiments/strategy2`, `production`, `core` → **empty** |
| Evidence immutability | evidence files re-read from VPS at audit time: unchanged (21 signals, same md5) |
| Script syntax / run | `ast.parse` OK; runs exit 0 with `PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1` |

---

## 15. Confirmation — no live orders, no state changes

- `orders_submitted_count.json` (local evidence copy): `{"orders_submitted":
  0, "blocked_attempts": 0}`; **fresh re-read from the VPS during this
  audit: still 0/0**.
- VPS `api_access.log`: **0 POST requests** (bridge touched read-only).
- `signals.jsonl` on VPS: still 21 lines; `runner.log` empty; `validation/`
  empty; `metrics.execution_mode = "SHADOW"`.
- The analysis script performs no network I/O and was never able to send
  orders (imports audited, §14); risk-block Telegram notifications were
  neutralized via capture patch.
- No config, runner, signal-generator, risk, execution, dashboard, or
  Telegram file was modified (git status shows no tracked-file changes).
- Local Termux notification/clipboard operations (§ end of report) touch only
  this device.

---

## 16. Files changed / created

Created (all new; nothing pre-existing modified):

```
scripts/nqts_shadow_replay/replay_audit.py       # analysis-only replay engine
scripts/nqts_shadow_replay/README.md             # classification + run instructions
scripts/nqts_shadow_replay/evidence/             # 6 read-only evidence copies (sha256 above)
scripts/nqts_shadow_replay/post9_ledger.jsonl    # 21-row machine ledger (populations A+B)
scripts/nqts_shadow_replay/post9_summary.json    # all passes, stats, outcomes, S4/S5, equity
archive/reports/NQTS_POST9_SHADOW_REPLAY_AUDIT.md  # this report
```

`scripts/` was already an untracked workspace directory; no file inside any
frozen tree was created, edited, or deleted.

---

## 17. Git status

- Branch `research/strategy-2`, HEAD `008b846a93006d716f0b6c1d87ea56f9658bd229`.
- `git diff HEAD` (tracked files): **empty** — zero tracked files modified.
- Untracked additions from this audit: `scripts/nqts_shadow_replay/*`,
  `archive/reports/NQTS_POST9_SHADOW_REPLAY_AUDIT.md` (plus the pre-existing
  untracked Phase-4 artifacts: `research/shared/reporting/`,
  `research/handoff/phase4_*`, `tests/research/…`, etc., untouched here).
- Nothing staged, nothing committed (audit is uncommitted by design).

---

## 18. Conclusion — descriptive only

Under the current NQTS execution/backtesting rules as applied here
(constitution risk limits as designed + one-position-per-pair + frozen
execution core, no session filter):

- **12 post-first-9 signals produced 5 hypothetical trades**; 7 were never
  opened because the 3-position cap was continuously occupied.
- **2 trades completed inside the observation window — both stopped out**
  (realized −7.17 USD on a 200 USD account, max drawdown 3.58%, win rate 0%,
  profit factor 0); **3 remain open** with +12.01 USD indicative unrealized
  P&L that is deliberately excluded from all statistics.
- Payoff concentration cannot be computed (no winning closed trades).
- Fill/cost/convention sensitivities move the result by under ±0.8 USD;
  the as-wired RiskGuard variant (stateful gates inert) and the research
  session filter are the only variants that materially change the outcome —
  −24.26 USD and 0.00 USD respectively.
- Data quality defects (NaT timestamps, artifact spread ticks, missing
  cycle ATR, late cycles, quote-currency accounting, observation truncation)
  are all enumerated, flagged per signal, and bounded by the sensitivities.

**These are descriptive facts about 12 signals over 8 days with 2 realized
outcomes. The sample is far too small and too short to support any claim of
statistical robustness, profitability, or readiness for real capital, and no
such claim is made.** No strategy, configuration, or implementation changes
are proposed or made; analysis stops here for review.

---

## Completion checklist (audit requirements)

| Requirement | Result |
|---|---|
| Branch | `research/strategy-2` |
| HEAD | `008b846a93006d716f0b6c1d87ea56f9658bd229` |
| Observation period | signals 2026-09-16T21:00:22Z → 2026-09-24T19:11:24Z; market data through 2026-09-24T17:00Z true UTC; runner state 2026-09-24T19:11:28Z |
| Signals analyzed | 21 resolved (12 in population B, 9 reference A); 0 unresolvable |
| Hypothetical trades (primary) | 5 opened; 2 closed; 3 open; 7 gated off; 0 suppressed; 0 session-blocked |
| Summary P&L | −10.05 quote-units = **−7.17 USD** (−3.58%); open indicative +12.01 USD (excluded) |
| Max drawdown | 7.17 USD = **3.584%** (realized, USD-converted) |
| Win rate | **0.0%** (0 of 2 closed) |
| Profit factor | **0.0** |
| Payoff concentration | undefined (zero winning closed trades) — stated explicitly |
| Data-quality limitations | §11 items 1–11, flagged per signal in ledger |
| Files created | §16 (6 + report); nothing pre-existing modified |
| Tests/validation | §14: determinism ×2, 5 hand-checks, sizing assert, I/O audit, frozen diff empty |
| No live orders confirmed | §15: orders 0/0 local+VPS, 0 POSTs, script network-free |
| Git diff status | §17: tracked diff empty; audit files untracked |
| Populations A/B | reported separately, never ranked |
| Small-sample limits | stated in §11 and §18; no robustness/profitability/deployment claims |
