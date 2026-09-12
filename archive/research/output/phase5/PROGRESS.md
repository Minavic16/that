# Phase 5 — Z-Score Exit Forensics Progress

## Status: COMPLETE

## Key Findings
1. **Exit architecture is the PRIMARY driver of negative expectancy**
2. **4-bar time exit produces PF=1.55** (+$58k improvement)
3. **SL is the dominant loss driver** (19.4% of trades, 100% of catastrophic losses)
4. **ZE exits too early** (57.6% of trades, captures only 45% of move)
5. **MR trades are break-even; CONT trades are catastrophic** (4.2% of trades)
6. **Bootstrap PF CI includes 1.0** — no statistically significant edge

## Analysis Completed
- [x] MAE/MFE analysis (wins vs losses, by Z/pair/exit/vol/session)
- [x] Trade-path analysis (Z trajectory, MR vs CONT classification)
- [x] Holding-time analysis (8 buckets)
- [x] Exit component attribution (A/B/C/D/E variants)
- [x] Counterfactual exits (time/MFE/trailing/MAE)
- [x] MR vs continuation hypothesis (Mann-Whitney test)
- [x] Robustness checks (period/pair/bootstrap/outlier)

## Data Files
- `research_data/phase5/exit_forensics.json`
- `research_data/phase5/EXIT_FORENSICS_REPORT.md`

## Next Steps
1. Implement 4-bar time exit and re-evaluate
2. Tighten Z-exit to Z > -1.0
3. Reduce SL to 2x ATR
4. Re-run backtest with new exits
5. If PF > 1.2 after costs, proceed to paper trading
