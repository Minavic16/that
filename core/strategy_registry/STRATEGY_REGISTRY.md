# Strategy Registry

> **NestQuant Strategy Identity Registry**
> **Status:** Active reference
> **Last Updated:** 2026-09-11

---

## 1. Registry Purpose

The Strategy Registry maintains the authoritative record of all strategy identities, their current status, and their lifecycle history.

---

## 2. Registered Strategies

### NQ-BREAKOUT-V1

| Field | Value |
|-------|-------|
| **Strategy ID** | `NQ-BREAKOUT-V1` |
| **Version** | `V1` |
| **Family** | `BREAKOUT` |
| **Timeframe** | `4H` |
| **Status** | `CANONICAL` |
| **Deployment** | `SHADOW` / `DEMO_OBSERVATION` |
| **Frozen** | `YES` |
| **Source Commit** | `e706995` |
| **Identity Document** | `platform/strategy_registry/NQ-BREAKOUT-V1.md` |

**Lifecycle Status:**
- Shadow trading: ACTIVE
- Demo observation: ACTIVE (14-day observation)
- Live trading: DISABLED
- Blue/Green role: BLUE (current trusted)

**Parameters:**
- Signal: LOOKBACK=5, ATR=14, SL_MULT=2.0, RRR=3.5
- Lifecycle: BE=0.8R, MAX_HOLD=42 bars, TRAILING=swing-based
- Risk: 0.15%/trade, 3 positions, 0.10 lots, 3.0 total, 3% daily, 8% DD, 4 trades/day

**Validation Status:**
- Parity validated: YES
- Shadow validated: YES (ongoing)
- Demo validated: IN PROGRESS
- Live validated: NO (not yet attempted)

---

## 3. Registry Rules

1. Only strategies that have completed at least the Strategy Identity lifecycle stage are registered
2. Each registered strategy has a unique identity document in `platform/strategy_registry/`
3. Registered strategies may be: PROPOSED, IMPLEMENTED, SHADOW, DEMO, CANARY, PRODUCTION, FROZEN, or ARCHIVED
4. New strategies are added only after passing the appropriate lifecycle gates
5. Archived strategies are moved to `archive/strategies/` with a reference in this registry

---

## 4. Future Strategies

Future strategies will be registered here after completing the strategy lifecycle. No strategy may skip the lifecycle to appear in this registry.

---

*End of Strategy Registry*
