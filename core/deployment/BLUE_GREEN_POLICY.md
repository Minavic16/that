# Blue-Green Deployment Policy

> **NestQuant Blue-Green Deployment Model**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

NestQuant uses a blue-green deployment model for strategy promotion. At any time, the production system maintains a clear distinction between the currently trusted deployment (BLUE) and candidate deployments (GREEN).

---

## 2. Definitions

| Term | Definition |
|------|-----------|
| **BLUE** | The currently trusted, production-deployed strategy/version |
| **GREEN** | A candidate strategy/version undergoing validation |
| **Allocation** | The proportion of capital or risk allocated to each deployment |

---

## 3. Current State

| Deployment | Strategy | Status |
|------------|----------|--------|
| BLUE | `NQ-BREAKOUT-V1` | Active, shadow/demo observation |
| GREEN | None | No candidate currently designated |

---

## 4. BLUE Properties

The BLUE deployment:
- Is the only strategy trusted for live capital allocation
- Has passed all promotion gates
- Is monitored continuously
- Has defined rollback procedures
- Cannot be modified without creating a new version

---

## 5. GREEN Properties

The GREEN deployment:
- MUST operate independently of BLUE
- MUST be capable of independent monitoring
- MUST be capable of independent rollback
- MUST NOT affect BLUE's operation
- MUST NOT share risk limits with BLUE (initially)
- Starts in isolation (shadow → demo → canary)

---

## 6. GREEN Lifecycle

### 6.1 Isolation Phase

GREEN starts in complete isolation:
- Shadow operation only (no orders)
- Independent signal generation
- Independent monitoring
- Independent metrics

### 6.2 Demo Phase

After shadow validation:
- Demo account operation
- Independent execution monitoring
- Slippage and fill quality assessment
- Risk control verification

### 6.3 Canary Phase

After demo validation:
- Limited capital allocation
- Strict health criteria
- Automatic rollback on failure
- Continuous monitoring

### 6.4 Expansion Phase

After canary validation:
- Gradual allocation increase
- Portfolio-level impact monitoring
- Risk limit adjustment (with approval)
- Ongoing health verification

### 6.5 Promotion Phase

If GREEN proves superior:
- Portfolio allocation decision (governed by risk)
- Potentially both BLUE and GREEN coexist
- Or GREEN replaces BLUE (with explicit approval)

---

## 7. Allocation Rules

Capital allocation between BLUE and GREEN MUST be determined by:
1. Portfolio-level risk analysis
2. Complementarity assessment
3. Deployment governance approval
4. Risk limit constraints

Allocation MUST NOT be:
- Arbitrary
- Hardcoded without governance review
- Determined solely by historical performance
- Determined without considering portfolio-level impact

---

## 8. Independence Requirements

GREEN MUST be capable of:
1. Generating signals independently
2. Managing lifecycle independently
3. Enforcing risk controls independently
4. Reporting metrics independently
5. Being disabled without affecting BLUE
6. Being rolled back without affecting BLUE

---

## 9. Failure Handling

If GREEN fails:
1. GREEN is immediately disabled
2. BLUE continues operating normally
3. GREEN's evidence is preserved
4. An incident is recorded
5. Investigation is conducted
6. GREEN is NOT automatically re-promoted

---

## 10. Promotion to BLUE

If GREEN is promoted to BLUE:
1. BLUE/GREEN status is updated
2. Previous BLUE may become archived or coexist
3. Allocation is adjusted per governance approval
4. Monitoring is updated
5. Rollback procedures are updated
6. Documentation is updated

---

## 11. Multiple GREEN Candidates

Multiple GREEN candidates MAY exist simultaneously, subject to:
- Portfolio-level risk limits
- Monitoring capacity
- Deployment governance approval
- Independent operation requirements

---

*End of Blue-Green Deployment Policy*
