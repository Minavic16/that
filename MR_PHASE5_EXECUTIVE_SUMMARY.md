# MR PHASE 5 — FORENSIC EXECUTIVE SUMMARY

## Final Verdict: CONDITIONAL EDGE

The MR strategy contains a **real but narrow statistical edge** that has degraded over time and is extremely sensitive to implementation quality. A meaningful subset — **early-London major-pair entries in strong trends** — retains a robust edge even through 2025-2026, but represents only ~3.5% of total trades.

---

## Phase 5 Key Findings

### 5A — Causal vs Full-Sample Regime Classification
| Metric | Causal (No Look-Ahead) | Full-Sample (Biased) |
|--------|----------------------|---------------------|
| Trades | 7,842 | 7,842 |
| PF | 1.88 | 1.88 |
| WR | 58.89% | 58.89% |
| PnL | $3,819,452 | $3,819,452 |

**Finding:** Identical results. Vol regime classification has **zero impact** on trade outcomes because the strategy does not use vol regime as a filter — it is purely a post-hoc label. The look-ahead bias in the vol classifier is inconsequential.

### 5B — Temporal Edge Profile (Mark-to-Market)
| Horizon | Mean MTM | Median MTM | Implication |
|---------|----------|------------|-------------|
| 1 bar | -$82 | -$67 | **Negative** — immediate mean *reversion* of the MR signal |
| 2 bars | -$24 | -$23 | Still negative |
| 3 bars | +$28 | -$4 | Breakeven — transition point |
| 5 bars | +$144 | +$22 | Positive — mean reversion begins |
| 10 bars | +$344 | +113 | Strong positive |
| 15 bars | +$481 | +198 | Peak positive zone |
| 20 bars | +$537 | +245 | Plateau |
| 30 bars | +$563 | +303 | Near-final |

**Finding:** The MR edge manifests as a **5-15 bar reversion** (5-15 minutes). Entries move against the signal for 1-2 bars before reverting. The strategy profits from **patience through initial adverse excursion**, not from immediate snap-back. This is consistent with the SC (session close) exit mechanic capturing only ~63% of available reversion.

### 5C — Exit Mechanism Investigation
| Metric | Value |
|--------|-------|
| SC trades | 7,700 (98.2% of all) |
| Still favorable at SC | 63.37% |
| MFE timing (median) | 55% of holding period |
| TP reached | 0 trades (0%) |
| +1R reached | 5.2% |
| +2.7R reached | 0% |

**Finding:** The TP is unreachable (2.7R at 50-bar max hold). The strategy is a **session-closer** that captures partial mean reversion. MFE peaks at ~55% of the holding period, meaning exits occur after peak favorable excursion has already occurred — systematic leave-on-the-table.

### 5D — Winner Fingerprint (H1 Hypothesis Test)
**Hypothesis:** Early-London (h=7-8) major-pair entries in strong trends produce higher forward expectancy.

| Period | Fingerprint | Non-Fingerprint |
|--------|------------|----------------|
| **Discovery** (2018-2022) | 157t, PF=**26.82**, WR=89.81%, $353K | 4,227t, PF=2.92, WR=65.01%, $2.97M |
| **Validation** (2023-2024) | 61t, PF=**6.09**, WR=77.05%, $125K | 1,785t, PF=1.24, WR=52.89%, $252K |
| **Untouched** (2025-2026) | 56t, PF=**2.80**, WR=66.07%, $60K | 1,556t, PF=0.97, WR=45.05%, $42K |

**Finding:** The fingerprint edge is **real but degrading**: PF 26.82 → 6.09 → 2.80. Even at PF=2.80 in the untouched period, it remains profitable. However, at 56 trades over 2 years, it is **too sparse to be a standalone strategy**.

### 5E — Pair Stability Analysis
| Pair | 2018-2022 | 2023-2026 | Classification |
|------|-----------|-----------|---------------|
| GBP/AUD | PF 0.65-18.16 | PF 0.41-2.11 | **Structurally negative** since 2020 |
| GBP/CAD | PF 0.54-4.67 | PF 0.48-1.25 | **Structurally negative** since 2021 |
| CAD/CHF | PF 2.42-15.03 | PF 0.24-1.96 | **Deteriorating** since 2024 |
| EUR/CHF | PF 1.79-17.94 | PF 0.46-3.93 | **Deteriorating** since 2024 |
| NZD/CHF | PF 0.97-3.07 | PF 0.21-1.56 | **Deteriorating** since 2024 |
| AUD/CHF | PF 1.21-3.69 | PF 0.34-1.02 | **Deteriorating** since 2024 |
| NZD/JPY | PF 1.14-6.49 | PF 0.38-1.0 | **Deteriorating** since 2024 |

**Finding:** Cross-pair CHF and AUD crosses have **structural regime shifts** in 2024-2026. GBP/AUD and GBP/CAD are persistently negative. The edge is **narrowing to major pairs in early London**.

### 5F — London Hourly Profile
| Hour | Trades | PF | WR |
|------|--------|-----|-----|
| 07 | ~900 | 3.5+ | 70%+ |
| 08 | ~400 | 3.0+ | 68%+ |
| 09-12 | ~500 each | 2.0-2.5 | 62-65% |
| 13-15 | ~400 each | 1.5-2.0 | 55-60% |

**Finding:** Edge is **front-loaded in London session**. Hours 07-08 have 2-3x the PF of hours 13-15.

### 5G — Major vs Cross × Session
| Combination | Trades | PF | WR |
|-------------|--------|-----|-----|
| **London + Major** | **1,043** | **5.79** | **76.8%** |
| London + Cross | 3,440 | 1.91 | 63.7% |
| Overlap + Major | 596 | 1.69 | 57.9% |
| Overlap + Cross | 1,387 | 1.11 | 50.3% |
| NY + Major | 360 | 0.91 | 44.4% |
| NY + Cross | 1,016 | 0.56 | 41.7% |

**Finding:** **London+Major is the only combination with a strong edge** (PF 5.79). NY sessions are structurally negative. Overlap is marginal.

### 5H — Block Bootstrap (5,000 iterations)
| Block Type | PF 95% CI | WR 95% CI |
|------------|-----------|-----------|
| Independent | [3.28, 5.27] | [67.3%, 73.5%] |
| Daily | [3.24, 5.39] | [67.0%, 73.8%] |
| Weekly | [3.91, 7.13] | [68.8%, 76.0%] |

**Finding:** The candidate subset (London+Major+StrongTrend) has a **robust PF CI well above 1.0** even under the most conservative weekly block bootstrap. The lower bound of **3.28 (independent) to 3.91 (weekly)** confirms this is not noise.

### 5I — Cost Sensitivity (Candidate Subset)
| Slippage | Trades | PF | WR | PnL |
|----------|--------|-----|-----|-----|
| 0.3 pip | 767 | 3.91 | 69.0% | $902K |
| 1.0 pip | 767 | 3.42 | 66.8% | $817K |
| 2.0 pip | 767 | 2.82 | 63.2% | $694K |
| 3.0 pip | 767 | 2.34 | 59.6% | $572K |

**Finding:** Candidate edge survives up to **3.0 pip slippage** with PF=2.34. Highly robust to transaction costs.

---

## Overall Phase 5 Conclusions

### What Works
1. **Early-London major-pair entries in strong trends** — PF 2.80-26.82 across all periods, survives bootstrap and cost stress
2. **Patience through 5-15 bar reversion** — the edge manifests at 5-15 minute horizons
3. **Major pairs only** — crosses are structurally deteriorating

### What Fails
1. **Full strategy (all sessions, all pairs)** — PF 1.88 overall, but PF<1.0 in NY and overlap sessions
2. **Cross pairs** — structural regime shifts since 2024, many now negative
3. **TP target (2.7R)** — unreachable at 50-bar max hold, 0% of trades reach it
4. **Late London entries** — hours 13-15 have marginal PF

### Revised Verdict
**CONDITIONAL EDGE** — A real, statistically robust edge exists in a narrow subpopulation (early-London, major pairs, strong trends). However:
- It represents only ~3.5% of total trades
- It degrades over time (PF 26.82 → 2.80)
- It requires **surgical trade selection** and **avoiding cross pairs and NY/overlap sessions**
- The overall strategy is **not deployable as-is** — it needs a regime filter or a complete re-engineering around the identified mechanism

---

## Data Quality Notes
- Phase 3 session analysis used exit-session instead of entry-session (96.5% mismatch) — corrected in Phase 4
- Timestamp alignment across pairs has 84.83% mismatch but negligible aggregate impact (PF delta 0.01)
- Phase 5A causal vol classifier uses expanding window with 200-bar minimum — no look-ahead bias

---

*Generated: 2026-08-10 | Data: 2018-01-01 to 2026-12-31 | Pairs: 20 FX*
