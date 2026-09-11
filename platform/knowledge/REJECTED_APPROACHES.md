# Rejected Approaches

> **NestQuant Historical Research Rejections**
> **Status:** Active reference
> **Last Updated:** 2026-09-11

---

## 1. Mean Reversion (MR) Approaches

### R-001: Z-Score Mean Reversion (Original)
- **What was tested:** Z-score based mean reversion on FX pairs
- **Why rejected:** Gross edge was below realistic transaction costs after comprehensive forensic analysis
- **Evidence:** MR_BASELINE_FORENSIC_REPORT, MR_PHASE2-5 forensic reports
- **Reconsiderable:** Yes — if transaction costs decrease or edge is found in different instruments/timeframes

### R-002: Probability-Gated MR
- **What was tested:** Logistic regression gating for mean reversion entries
- **Why rejected:** Gating did not produce sufficient economic edge after costs
- **Evidence:** Phase 9 probability-gated MR validation
- **Reconsiderable:** Yes — with different gating methodology or instruments

### R-003: Session-Gated MR
- **What was tested:** Mean reversion filtered by trading session
- **Why rejected:** Session filtering did not improve risk-adjusted performance sufficiently
- **Evidence:** Phase 11 filter ablation
- **Reconsiderable:** Yes — with different session definitions

---

## 2. Filter Approaches

### R-004: Currency Strength Filter
- **What was tested:** Filter signals based on currency strength ranking
- **Why rejected:** Did not produce sufficient improvement to justify complexity
- **Evidence:** Phase 10 currency strength validation, Phase 11 filter ablation
- **Reconsiderable:** Yes — if combined with other filters in a validated way

### R-005: Correlation Filter
- **What was tested:** Filter based on pair correlation
- **Why rejected:** Historical correlation logic belonged to MR+TF research, not applicable to breakout strategy
- **Evidence:** S10_3 correlation audit
- **Reconsiderable:** Yes — if a new correlation hypothesis is validated for breakout

### R-006: Regime Filter (Ad-Hoc)
- **What was tested:** Simple regime-based filtering
- **Why rejected:** Regime classification requires careful validation; ad-hoc regime filtering introduced complexity without sufficient edge
- **Evidence:** Phase 12 regime validation
- **Reconsiderable:** Yes — with validated regime classification methodology

---

## 3. Legacy Strategy Approaches

### R-007: GFT Dynamic Risk Config
- **What was tested:** GFT-specific risk parameters and session times
- **Why rejected:** Broker-specific, superseded by constitution-based risk model
- **Evidence:** `archive/legacy/config.py` — archived
- **Reconsiderable:** No — superseded by production architecture

### R-008: EMA200 Pullback Structured Entry
- **What was tested:** EMA200 pullback signal with ADX/ATR filters
- **Why rejected:** Did not survive validation; superseded by current signal architecture
- **Evidence:** `archive/legacy/structured_entry.py` — archived
- **Reconsiderable:** No — superseded by production architecture

---

## 4. Deployment Approaches

### R-009: Direct MT5 SDK Import
- **What was tested:** Direct Python import of MetaTrader5 package
- **Why rejected:** Platform dependency, difficult to test, coupling issues
- **Evidence:** HTTP bridge approach validated as superior
- **Reconsiderable:** No — HTTP bridge is the established pattern

### R-010: Automatic Strategy Promotion
- **What was tested:** Automatic promotion when backtest passes thresholds
- **Why rejected:** No single metric is sufficient evidence for live deployment
- **Evidence:** Strategy lifecycle design rationale
- **Reconsiderable:** No — explicit human approval required at critical gates

---

## 5. Research Methodology

### R-011: Optimizing Parameters for Historical P&L
- **What was tested:** Parameter optimization to maximize backtest performance
- **Why rejected:** Produces overfit strategies that fail out-of-sample
- **Evidence:** Multiple phase validations showed degradation OOS
- **Reconsiderable:** No — optimization for P&L is fundamentally flawed

### R-012: Adding Filters Without Independent Validation
- **What was tested:** Adding "useful-sounding" filters without rigorous validation
- **Why rejected:** Filters can reduce trade count without improving risk-adjusted performance
- **Evidence:** Phase 11 filter ablation showed many filters don't help
- **Reconsiderable:** Yes — but each filter requires independent validation

---

*End of Rejected Approaches*
