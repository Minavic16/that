# Canary and Rollback Policy

> **NestQuant Canary Deployment and Rollback Procedures**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

Canary deployment provides controlled rollout of new strategies with automatic protection against failure. A failed candidate MUST be removable without affecting unrelated strategies.

---

## 2. Candidate Isolation

Before canary deployment, the candidate MUST demonstrate:

| Requirement | Verification |
|-------------|-------------|
| Independent signal generation | Shadow parity tests pass |
| Independent risk controls | Risk guard tests pass |
| Independent monitoring | Metrics reported correctly |
| Independent rollback | Rollback procedure tested |
| No dependency on BLUE | Import graph verified |

---

## 3. Canary Entry Criteria

A candidate MAY enter canary when:

1. Demo observation period is complete
2. Execution quality is acceptable
3. All risk controls function correctly
4. Canary deployment plan is documented
5. Health criteria are defined
6. Failure criteria are defined
7. Rollback procedure is tested
8. Deployment governance approves

---

## 4. Health Criteria

Canary health MUST be monitored continuously. Health criteria include:

| Category | Metrics |
|----------|---------|
| Signal quality | Signal frequency, signal fidelity, parity match |
| Execution quality | Fill rate, slippage, rejections |
| Risk compliance | Position limits, exposure limits, drawdown limits |
| Infrastructure | Connectivity, latency, error rates |
| Performance | Expectancy, win rate, profit factor |

Health criteria MUST be defined before canary entry and MUST include:
- Minimum acceptable values for each metric
- Maximum acceptable degradation from baseline
- Time window for evaluation

---

## 5. Failure Criteria

The candidate FAILS the canary if ANY of:

| Condition | Action |
|-----------|--------|
| Risk limit breach | Automatic rollback |
| Infrastructure failure | Automatic rollback |
| Signal fidelity drop below threshold | Automatic rollback |
| Execution quality below threshold | Automatic rollback |
| Health metric below minimum for sustained period | Automatic rollback |
| Manual rollback requested | Immediate rollback |

---

## 6. Automatic Protections

The canary deployment MUST include:

1. **Position limit:** Maximum position size for canary (separate from BLUE)
2. **Exposure limit:** Maximum total canary exposure
3. **Drawdown limit:** Maximum canary-specific drawdown
4. **Loss limit:** Maximum canary daily loss
5. **Trade limit:** Maximum canary trades per day

These limits MUST be stricter than production limits during the canary phase.

---

## 7. Manual Intervention

Operators MAY intervene at any time to:
- Reduce canary allocation
- Pause canary trading
- Roll back canary
- Adjust canary parameters (with approval)
- Investigate canary behaviour

Manual intervention MUST be recorded with:
- Timestamp
- Action taken
- Reason
- Operator identity

---

## 8. Rollback Procedure

### 8.1 Immediate Rollback

When rollback is triggered:
1. Disable candidate strategy immediately
2. Close or maintain existing candidate positions (per policy)
3. Preserve all candidate evidence
4. Notify operators
5. Record incident

### 8.2 Evidence Preservation

During rollback, the following MUST be preserved:
- All signal logs
- All trade logs
- All metrics
- All health data
- All configuration at time of failure
- All error logs

### 8.3 Incident Recording

Every rollback MUST produce an incident record containing:
- Trigger condition
- Timestamp
- Evidence summary
- Impact assessment
- Root cause (if known)
- Recommended next steps

### 8.4 Post-Rollback

After rollback:
1. BLUE continues operating normally
2. Investigation is conducted
3. Root cause is determined
4. Fix is proposed (if applicable)
5. Candidate may re-enter lifecycle after investigation

---

## 9. Re-Promotion Prevention

After a canary failure:
1. The candidate MUST NOT be automatically re-promoted
2. The failure MUST be investigated
3. The root cause MUST be determined
4. A fix MUST be implemented and tested
5. The candidate MUST re-enter the lifecycle at the appropriate stage
6. The fix MUST be validated before canary re-entry

---

## 10. Impact Isolation

Failure of one strategy MUST NOT:
- Take down unrelated strategies
- Affect BLUE deployment
- Corrupt shared infrastructure
- Disable monitoring for other strategies
- Breach portfolio-level risk limits

---

*End of Canary and Rollback Policy*
