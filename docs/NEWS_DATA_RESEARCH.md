# Z-Score Research Engine — News Data Research

## Source Evaluation

### Primary Candidate: ForexFactory Calendar

| Property | Value |
|----------|-------|
| **Source** | ForexFactory (forexfactory.com) |
| **Format** | HTML scraping or cached JSON |
| **Historical coverage** | ~2007 to present |
| **Timestamp semantics** | Event time (when the data release occurs), NOT when information becomes public |
| **Timezone** | Reported in exchange timezone, convertible to UTC |
| **Fields** | timestamp, currency, event name, impact level, actual, forecast, previous |
| **Instruments** | Currency-based (USD, EUR, GBP, JPY, etc.) — maps to FX pairs |
| **Event importance** | Low / Medium / High / Red (4 levels) |
| **Actual/Forecast/Previous** | Available for most economic releases |
| **Licensing** | Web scraping — no official API. Terms of service may prohibit automated access |
| **Limitations** | Timestamp is event time, not information availability time. Some events have delayed releases |

### Secondary Candidate: Myfxbook Economic Calendar

| Property | Value |
|----------|-------|
| **Source** | Myfxbook (myfxbook.com/economic-calendar) |
| **Historical coverage** | ~2012 to present |
| **Timestamp semantics** | Event time |
| **Fields** | Similar to ForexFactory |
| **Licensing** | Web scraping |

### Tertiary Candidate: Investing.com Economic Calendar

| Property | Value |
|----------|-------|
| **Source** | Investing.com |
| **Historical coverage** | ~2000 to present |
| **Timestamp semantics** | Event time |
| **Fields** | Extended (revision history available for some events) |
| **Licensing** | Web scraping, more aggressive anti-bot measures |

---

## Timestamp Semantics — Critical Distinction

**Event time** = when the economic data was scheduled for release
**Information time** = when the information actually became publicly available

For most high-impact releases (NFP, CPI, FOMC), information time ≈ event time (released on schedule).

For some releases, actual publication can be delayed by minutes to hours.
For FOMC statements, the exact release time is known to the second.

**For this research:**
- Use event time as a lower bound on information availability
- For high-impact events, assume information time = event time
- For low-impact events, the distinction is less critical
- Document this assumption explicitly

---

## Currency-to-Pair Mapping

News events are tagged by currency (e.g., "USD"). They affect all pairs containing that currency:

```
USD event → EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, USD/CAD
EUR event → EUR/USD, EUR/GBP, EUR/JPY, EUR/CHF, EUR/AUD, EUR/CAD, EUR/NZD
GBP event → GBP/USD, GBP/JPY, GBP/CHF, GBP/AUD, GBP/CAD, GBP/NZD
JPY event → USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, CAD/JPY
```

A single news event can affect multiple pairs simultaneously.
Cross-pair correlation during news windows is expected.

---

## Research Questions (Phase 2+)

Before using news as a trading feature, investigate:

1. Does Z-score behavior change around news releases?
2. Does mean reversion weaken around major releases?
3. Does spread widen around news? (requires tick data or bid/ask)
4. Does slippage increase around news?
5. Does strategy expectancy differ during news windows?
6. Can news timing improve entry/exit decisions?

---

## Implementation Plan

**Phase 1:** Document the source and contract. Do NOT download data yet.
**Phase 2:** Acquire a small sample (1 month) for validation.
**Phase 3:** Full historical acquisition if research questions are promising.

**Data contract for news events:**

```python
@dataclass
class NewsEvent:
    timestamp: pd.Timestamp       # event time (UTC)
    currency: str                 # "USD", "EUR", etc.
    event_name: str               # e.g., "Non-Farm Employment Change"
    importance: str               # "low" | "medium" | "high" | "red"
    actual: float | None          # actual value (None if not yet released)
    forecast: float | None        # consensus forecast
    previous: float | None        # previous period value
    source: str                   # "forexfactory" | "myfxbook" | etc.
```

---

## Licensing Notes

- ForexFactory: No official API. Scraping may violate ToS. Use cached/ archived data where possible.
- Myfxbook: Similar situation.
- For research purposes, a small sample can be manually collected.
- Full historical acquisition should use a paid data provider if available.
- Interactive Brokers and other brokers provide news data via their APIs — check if cTrader provides this.
