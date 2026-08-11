You are working on the NestQuant Z-Score Research 
Engine. Before making any changes, read and obey 
AGENTS.md and the existing repository 
documentation. Create/update the project's root 
AGENTS.md with the following standing rules:
# NestQuant Engineering & Research Constitution
## 1. Mission
NestQuant is a quantitative research and trading 
system. The purpose of this project is not to 
manufacture profitable backtests. The purpose is 
to determine, as honestly as possible, whether a 
trading hypothesis has a robust, causal, 
reproducible and economically viable edge. A 
negative result is a valid and valuable research 
result. Never modify methodology merely to make 
performance metrics look better. ---
## 2. Research Integrity Comes First
Every research result must be causally valid. At 
timestamp t, a trading decision may only use 
information that would genuinely have been 
available at timestamp t. Never use: - future 
candles - future closes - future highs/lows - 
future volatility - future news - future regime 
labels - future-derived normalization statistics - 
future trade outcomes - information from the 
completed trading day when the decision occurred 
before that day ended - data that was revised 
after the decision timestamp unless the historical 
availability of that revision is explicitly 
modelled Any feature, indicator, regime 
classifier, normalization method, signal or filter 
that could potentially introduce look-ahead must 
have an explicit causality test. When uncertain 
whether something is causal, assume it is unsafe 
until verified. ---
## 3. No Silent Methodology Changes
Never silently change: - trading logic - data 
source - timeframe - timezone - spread assumptions 
- commission - slippage - position sizing - 
leverage - risk model - session definitions - 
regime definitions - entry/exit rules - execution 
assumptions - historical date range If a change 
affects research validity, document it. A change 
that materially alters the experiment must produce 
a new experiment/version rather than overwriting 
the previous result. ---
## 4. Reproducibility
Every meaningful research run must be 
reproducible. Record, where applicable: - Git 
commit - configuration - dataset/version - data 
source - date range - instruments - timeframe - 
timezone - commission assumptions - spread 
assumptions - slippage assumptions - strategy 
parameters - random seeds - software/environment 
versions Never rely on undocumented manual 
settings. Research configuration belongs in 
version-controlled configuration files rather than 
being scattered through source code. ---
## 5. Software Engineering
Use proper software engineering practices 
throughout the project. Prefer: - modular 
architecture - single responsibility - explicit 
interfaces - type hints - meaningful names - small 
functions - dependency injection where appropriate 
- deterministic behavior - structured logging - 
configuration-driven experiments - clear error 
handling - unit tests - integration tests - 
regression tests - smoke tests Do not create giant 
files or monolithic functions when the 
functionality can be separated cleanly. Do not 
duplicate logic unnecessarily. Do not add 
abstractions merely for theoretical elegance; 
abstractions should solve an actual architectural 
problem. ---
## 6. Test Before Trust
New functionality should normally be accompanied 
by tests. Tests should exist at multiple levels:
### Unit tests
Verify individual calculations and components.
### Integration tests
Verify that components work correctly together.
### Causality tests
Verify that changing future data does not change 
past decisions.
### Regression tests
Prevent previously fixed bugs from returning.
### Smoke tests
Verify that the complete pipeline can execute 
successfully end-to-end. A successful program 
execution is NOT proof that the research is 
correct. ---
## 7. Causality Tests Are First-Class Tests
For any feature calculated at timestamp t: 1. 
Calculate the feature using the original dataset. 
2. Modify data strictly after t. 3. Recalculate 
the feature at t. 4. Assert that the result at t 
is unchanged. Apply this principle to: - rolling 
statistics - Z-scores - volatility - regime 
classification - news features - signals - 
position sizing where relevant - portfolio 
decisions Any causality violation is a blocking 
defect. ---
## 8. Separate Research From Execution
Maintain clear separation between: 1. Data 
ingestion 2. Data validation 3. Feature 
engineering 4. Regime classification 5. 
Statistical calculations 6. Signal generation 7. 
Portfolio construction 8. Execution simulation 9. 
Accounting 10. Reporting Do not mix 
broker/execution logic into statistical 
calculations. Do not allow live trading 
infrastructure to contaminate research 
calculations. The same research logic should be 
testable without connecting to a broker. ---
## 9. Z-Score Engine
The Z-Score engine must initially be treated as a 
statistical research component, not as a proven 
trading strategy. A Z-score must be calculated 
using only information available at the decision 
timestamp. The initial engine should support 
investigation of: - rolling mean - rolling 
standard deviation - Z-score - lookback 
sensitivity - distribution of Z-scores - forward 
returns - mean-reversion behavior - spread 
behavior - pair relationships where applicable Do 
not optimize parameters merely to maximize 
historical P&L. ---
## 10. Market Regime Research
The research system must investigate behavior 
across: - ranging markets - trending markets - 
transition regimes - low volatility - high 
volatility Regime classification used for analysis 
must be distinguished from regime classification 
available to the strategy at decision time. Do not 
accidentally use future information to label 
historical observations. Where useful, analyze the 
interaction between market structure and 
volatility: - low-volatility range - 
high-volatility range - low-volatility trend - 
high-volatility trend - low-volatility transition 
- high-volatility transition ---
## 11. News Data
News data is a first-class research dataset. The 
system should collect and normalize available 
historical news information, including where 
available: - timestamp - source - headline - 
currency - instrument - category - importance - 
actual - forecast - previous News must be 
timestamped according to when the information 
became publicly available, not merely the date 
associated with the event. Do not initially assume 
news should be used as a trading feature. First 
use it to investigate questions such as: - Does 
Z-score behavior change around news? - Does mean 
reversion weaken around major releases? - Does 
spread widen around news? - Does slippage increase 
around news? - Does strategy expectancy differ 
during news windows? Only introduce news as a 
trading feature after a separate research 
hypothesis justifies it. ---
## 12. Execution Reality
Backtests must explicitly model, where 
appropriate: - bid/ask spread - commission - 
slippage - execution delay - market/session 
liquidity - news-related execution degradation Do 
not assume zero transaction costs. Do not hide 
costs inside unexplained adjustments. The research 
system should determine how much execution 
friction the strategy can survive. Important 
outputs include: - break-even spread - break-even 
commission - break-even slippage - expectancy 
after costs - PF after costs - maximum tolerable 
cost before expectancy becomes non-positive Where 
useful, perform cost-sensitivity analysis rather 
than testing only one cost assumption. ---
## 13. Never Confuse Signals With Trades
Clearly distinguish: - raw statistical 
observations - candidate signals - filtered 
signals - executable entries - executed trades - 
portfolio positions A large number of signals does 
not imply a large number of trades. A large number 
of trades does not imply profitability. Always 
report these quantities separately. ---
## 14. No Premature Optimization
Do not optimize parameters until the causal 
baseline is established. Do not repeatedly modify 
parameters until the backtest becomes profitable. 
If a strategy fails, first determine WHY it fails. 
Potential failure categories include: - no 
statistical edge - regime dependence - excessive 
transaction costs - poor execution assumptions - 
unstable relationship - insufficient signal 
strength - adverse selection - parameter 
instability - data quality problems - structural 
market changes A failed strategy should be 
documented and preserved rather than silently 
altered. ---
## 15. Preserve Failed Experiments
Never delete failed research merely because it is 
unprofitable. Record: - hypothesis - methodology - 
configuration - data - results - failure reason - 
causality status - conclusions Failed experiments 
prevent repeated mistakes and are part of the 
project's research history. ---
## 16. Git Discipline
Use Git throughout development. Work in feature 
branches for substantial changes. Prefer small, 
focused commits. Commit messages should describe 
the actual change, for example: feat(zscore): 
implement causal rolling statistics test(zscore): 
verify future-data invariance feat(data): add 
normalized market data contract test(execution): 
validate slippage accounting Never rewrite or 
discard useful research history without a strong 
reason. Before substantial changes, inspect Git 
status and understand the current state of the 
repository. ---
## 17. VPS Safety
The VPS may contain active trading infrastructure. 
Before deleting, stopping, migrating or modifying 
anything: 1. Inspect it. 2. Determine what it 
does. 3. Determine whether it is active. 4. 
Determine whether it is safe to change. 5. Prefer 
archival over deletion when uncertain. Never 
blindly run destructive commands. Do not kill 
processes, delete directories, remove 
environments, uninstall packages, alter firewall 
rules or modify services without first determining 
their purpose and impact. Never expose secrets in 
logs, commits, source code or reports. ---
## 18. Dependency Discipline
Before adding a dependency: - determine whether an 
existing dependency already provides the 
functionality - consider maintenance and security 
- keep the dependency narrowly justified - pin or 
constrain versions where appropriate - document 
meaningful additions Do not add libraries simply 
because they are convenient. ---
## 19. Data Integrity
Validate incoming data before research begins. 
Check for: - missing timestamps - duplicate 
timestamps - unordered timestamps - missing bars - 
abnormal gaps - timezone inconsistencies - 
duplicate records - impossible OHLC relationships 
- stale data - corrupted records Do not silently 
repair suspicious data. Log and document 
corrections. ---
## 20. Experiment IDs
Meaningful experiments should have unique 
identifiers. Example: ZS-2026-001 Store experiment 
configuration and results separately from source 
code. Never overwrite previous experiment results. 
---
## 21. Reporting
Reports should show enough information to 
understand how the result was obtained. At 
minimum, where relevant: - date range - 
instruments - timeframe - trades - win rate - 
profit factor - expectancy - P&L - drawdown - 
Sharpe/other risk metrics - transaction costs - 
spread assumptions - slippage assumptions - regime 
breakdown - yearly breakdown - session breakdown - 
causality status Do not report a headline metric 
without its assumptions. ---
## 22. Agent Behavior
Before implementing substantial functionality: 1. 
Inspect the repository. 2. Understand existing 
architecture. 3. Identify reusable components. 4. 
Check existing tests. 5. Propose the smallest safe 
implementation. 6. Implement incrementally. 7. 
Test after each meaningful change. 8. Report what 
changed and why. Do not rewrite working components 
merely because you prefer a different 
architecture. Do not create unnecessary files. Do 
not claim a feature works unless it has actually 
been tested. If a test fails, investigate the root 
cause rather than hiding or weakening the test. If 
research results look unexpectedly good, treat 
that as a reason for MORE scrutiny, not less. ---
## 23. Current Research Principle
The previous MR strategy demonstrated why these 
rules exist. A strategy that appeared highly 
profitable became unprofitable when daily-candle 
look-ahead was removed. Therefore: CAUSALITY > 
PROFITABILITY REPRODUCIBILITY > CONVENIENCE 
ROBUSTNESS > OPTIMIZATION EVIDENCE > ASSUMPTION 
FALSIFICATION > CONFIRMATION The goal is not to 
prove that Z-score trading works. The goal is to 
discover whether it works. If it does not work, 
the system must tell us clearly. ---
## 24. Current Development Sequence
Do not jump directly into optimization or live 
trading. Follow this general sequence: 1. 
Repository/VPS inspection 2. Safe cleanup 3. 
Architecture and data contracts 4. Small data 
acquisition 5. Data validation 6. Smoke-test 
pipeline 7. Unit tests 8. Causality tests 9. 
Z-score statistical analysis 10. Regime analysis 
11. News-event analysis 12. Cost/slippage 
sensitivity 13. Baseline backtest 14. 
Out-of-sample validation 15. Walk-forward testing 
16. Robustness/stress testing 17. Only then 
consider paper/live deployment At each stage, stop 
and verify the evidence before moving to the next 
stage.
# End of Constitution
