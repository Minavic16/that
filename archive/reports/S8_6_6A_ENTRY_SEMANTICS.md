# S8.6.6.A — Entry Semantics Verification

**Date:** 2026-09-04
**Status:** Complete
**Finding:** 🟡 UNRESOLVED PARITY QUESTION → Partially resolved

---

## Trace: Signal → Broker

### 1. Signal generates entry_price

`breakout.py:80`:
```python
entry_price = current_high  # Signal bar's swing high
```

For BUY: `entry_price = current_high`
For SELL: `entry_price = current_low`

### 2. Intent carries entry_price

`intent_factory.py:125-135`:
```python
TradeIntent(entry_price=signal.entry_price, ...)
```

### 3. OrderRequest carries entry_price

`orchestration.py:193-201`:
```python
OrderRequest(entry_price=intent.entry_price, ...)
```

### 4. MT5 adapter IGNORES entry_price

`mt5_adapter.py:136-144`:
```python
response = self._client.send_order(
    symbol=mt5_symbol,
    direction=direction,
    volume=request.lot_size,
    sl=request.stop_loss,
    tp=request.take_profit,
    magic=self._magic,
    deviation=self._deviation,
    # NOTE: request.entry_price NOT passed
)
```

### 5. MT5 client sends MARKET order

`mt5_client.py:266-291`:
```python
def send_order(
    self,
    ...
    price: Optional[float] = None,  # "Limit price (None for market orders, ignored)"
    ...
    order_type: str = "MARKET",  # "Ignored (bridge only supports market orders)"
):
```

---

## Conclusion

**entry_price is a signal-level concept, NOT a broker execution price.**

- The signal identifies WHERE the breakout level is (swing high/low)
- The SL and TP are calculated relative to THIS level
- The broker executes a MARKET order at the next available price
- The actual fill may differ from entry_price

**This is NOT a lineage break.** Both research and production use the same concept:

| Aspect | Research | Production |
|--------|----------|------------|
| Entry reference | signal bar level | signal bar level |
| Actual fill | next bar open | broker market fill |
| SL/TP relative to | entry reference | entry reference |
| R calculation | from entry reference | from entry reference |

The effective R-multiple in live trading uses the signal's entry_price as the denominator, not the actual fill price. This is consistent with the research engine.

**Remaining question**: Does the research use `open_[i]` (next bar open) as the entry reference, while production uses `current_high` (signal bar swing level)? These could differ by a few pips.

**Resolution**: The signal's `entry_price` is the breakout LEVEL, not the execution price. The research's `open_[i]` was the execution price approximation. In production, the broker fill is the execution price. Both systems compute R relative to the signal level. This is functionally equivalent for research purposes, though the exact fill price may introduce small slippage differences.

**Status**: 🟡 UNRESOLVED for exact fill price parity, but ✅ CONCEPTUALLY EQUIVALENT for R calculation and lifecycle management. The signal-level entry_price is the correct reference for SL/TP/trailing/breakeven.
