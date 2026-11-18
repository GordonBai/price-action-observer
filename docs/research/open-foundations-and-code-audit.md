# Public foundations and open-code audit

Reviewed 2026-11-18. This is supplemental research, not Brooks doctrine. Publicly readable education is not necessarily open-licensed. No videos watched in this pass. Repository code was cloned/read, not installed or executed. This is a scoped audit, not a proof that every function is safe.

## 1. Foundation sources actually read

### Market structure and continuation
[CME technical analysis course](https://www.cmegroup.com/education/courses/technical-analysis) has eight lessons, including charts, moving averages, continuation/reversal patterns, support/resistance and oscillators. Course index read; not all eight lessons reviewed.
[CME continuation](https://www.cmegroup.com/education/courses/technical-analysis/trend-and-continuation-patterns) text/search excerpt identifies triangles, rectangles, pennants and flags as continuation candidates and discusses contracting price ranges. This is a vocabulary source, not evidence that a detected shape predicts SOXL returns. Full visual diagrams/video remain unchecked.

Engineering proposal: store context (direction, strength, overlap, range width), pattern geometry, and breakout event separately. A rectangle is a candidate range, not an unconditional continuation trade. Define geometry thresholds explicitly as our choices.

### Reversal structure
[CME reversals](https://www.cmegroup.com/education/courses/technical-analysis/technical-patterns-reversals) substantive page text read. Double/triple tops and bottoms require a subsequent break of the intervening extreme for conventional confirmation; head-and-shoulders uses its neckline. Shapes can evolve and are indications rather than deterministic predictions.

Engineering proposal: represent low–high–low or high–low–high as candidate pivots, freeze the intervening level at candidate creation, then record a later trigger. Tolerances, minimum separation and whether wick/close confirms are parameters, not supplied by this article. Brooks' broader double-bottom flag context must remain a separate definition namespace.

### Support/resistance
[CME support/resistance](https://www.cmegroup.com/education/courses/technical-analysis/support-and-resistance) full substantive text read. Discusses prior extrema, moving averages, price levels and trendlines; emphasizes zones rather than exact pennies and possible role reversal after a break.

Engineering proposal: each zone retains source, timestamp available, anchor observations, width and invalidation events. Never use a day's final high/low before that day ends. Historical extrema do not prove actual resting liquidity. A test, rejection, breakthrough and retest are separate events.

### Stops, sizing and exits
[CME proper position size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size) substantive text read through search. Stop location should express thesis failure, with size derived from risk budget and distance. Its example risk percentages are education, not a default recommendation for Gordon.

[SEC stop/stop-limit bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15) substantive search-returned text read. A stop trigger is not guaranteed fill price; stop-limit trades price control for non-execution risk. Trigger rules can differ by broker.

Engineering proposal: output invalidation price, target rationale and theoretical R separately from any simulated order. Model gaps, spread and latency. No position-size prescription without an explicit budget. A measured target is not evidence for opening an opposite position. Default system is research/signal-only.

### Real-time confirmation
[TradingView repainting documentation](https://www.tradingview.com/pine-script-docs/concepts/repainting/) substantial text read, including fluid intrabar data and higher-timeframe behavior. Closed-bar historical data cannot reproduce every intrabar change. Backplotting pivots and leaking future information are distinct from an honestly provisional live value.

Engineering proposal: three times per event: anchor time, first observed time, confirmed time. Alerts must label provisional versus confirmed. Higher-timeframe inputs use completed buckets. Replay each prefix and compare immutable confirmed events with the same prefix from a full-history run. Data revisions need versioning rather than silent overwrites.

## 2. Source code and licensing review

### TA-Lib: suitable optional low-level baseline, not PA engine
Repository: https://github.com/TA-Lib/ta-lib
Inspected commit: `543eb1694d4ca659ded434b1d02a681d353ae82d`.
License read: BSD-3-Clause-style terms, retaining copyright/license/disclaimer and no endorsement.
Source inspected: `src/ta_func/ta_CDLENGULFING.c`, batch and streaming sections. This implementation compares current and previous candle bodies; streaming state holds lagged open/close. Its ±80/±100 codes are categorical pattern outputs, not calibrated probabilities. For this inspected function, no future bar is needed once the current bar closes. This does NOT establish that every function or wrapper is causal in every use.

Use: candle primitives and reproducible baseline features. Do not mistake the CDL family for swing double bottoms, H2 or measured-move logic. Preserve the distinction between candle shape and market context. Pin a release/commit and test prefix invariance before adoption.

### TradingPatternScanner: do not vendor into MIT/commercial system
Repository: https://github.com/white07S/TradingPatternScanner
Inspected commit: `57e5396c4c5446c8222ed01ca8ebeefc679d611e`.
Actual LICENSE read: **CC BY-NC-SA 4.0**, not MIT. Noncommercial/share-alike restrictions are material; do not copy its implementation into a MIT project or assume commercial reuse is allowed.

Source findings:
- `tradingpatterns/tradingpatterns.py` lines 12–14 and 122–124 use `shift(-1)` in head/shoulders and double-top/bottom masks. Labels at row t depend on t+1.
- The double-bottom predicate is a short local geometric condition, not a full Brooks context/neckline state machine.
- `tradingpatterns_tech.py` filtered variant calls full-series Savitzky–Golay then negative shifts.
- `kalman_smooth` estimates parameters by EM on the passed whole series before filtering; full-history use leaks future fitting information even though a Kalman filtering step itself can be causal.
- Wavelet denoising acts on the whole passed series, including global coefficient statistics; cannot be assumed streaming-stable.

Use only as conceptual audit/negative examples unless licensing is separately resolved. A delayed output alone does not cure globally fitted/full-series transformations. No accuracy claims from its README were independently validated here.

### smart-money-concepts: MIT but retrospective annotations need redesign
Repository: https://github.com/joshyattridge/smart-money-concepts
Inspected commit: `1b62fd6c41e1f508e7ed76831a039fa4c82d42f6`.
LICENSE read: MIT. Source inspected: `smartmoneyconcepts/smc.py` FVG, swing extrema and associated scan sections.

- FVG compares previous and next bars via `shift(1)`/`shift(-1)` but annotates the middle bar. First knowable at the third bar's close, not middle bar time.
- `swing_highs_lows` documents and implements lookback AND look-forward of `swing_length`; confirmation must be delayed. Subsequent removal of consecutive extrema can revise earlier annotations further.
- FVG `MitigatedIndex` scans subsequent candles. That is an outcome label, not an input feature available at gap creation.
- `join_consecutive` merges and removes earlier gaps. Historical drawing identity is not an immutable live-event identity.

Use as separately named SMC research vocabulary, not Brooks. Causal online events need independent first-seen/confirmation timestamps and explicit updates. Do not feed future mitigation/break indices into signal decisions. MIT permission does not imply sound trading logic.

## 3. Recommended curriculum / implementation coverage matrix

| Layer | Topics | Source status | Engineering milestone |
|---|---|---|---|
| Bars | OHLC, bodies/wicks, inside/outside, doji, engulfing, gaps | CME index/text, one TA-Lib implementation reviewed | causal feature tests; no trade claim |
| Structure | swing extrema, HH/HL/LH/LL, trend/channel/range, support zones | CME articles read; Brooks handled separately | timestamped pivots and regime evidence |
| Continuation | pullback, flag, triangle, rectangle, breakout/retest | CME partial text plus Brooks cards | candidate/trigger/failure state machine |
| Reversal | double/triple top/bottom, H&S; Brooks MTR separately | CME text read | neckline confirmation and counterexamples |
| Targets | range projection, leg symmetry, gap projection | Brooks research primary | target provenance, no automatic reversal |
| Risk | logical invalidation, R, stops vs fills, non-execution | CME/SEC substantive text read | explicit fill/cost assumptions |
| Live behavior | provisional bars, HTF, pivot delay, revisions | TradingView docs read | prefix-invariance + append-only events |
| Evaluation | temporal splits, correlated examples, leakage, cost sensitivity | design recommendations | freeze rules, then evaluate untouched periods |

Missing/next: full chart visual audit; continuation lesson full-text verification; H&S and triple variants nuanced handling; broaden candle implementation audit; session/gap/auction microstructure; independent annotation sets. This is not a claim of comprehensive market knowledge or all patterns implemented.

## 4. Integration rule

Each concept must declare `tradition` (Brooks / classical TA / SMC / engineering), `source`, `read_status`, `rule_version`, `required_history`, `confirmation_delay`, `failure_cases`, and `license`. Textbook explanations, mechanical recognizers and empirical performance must live in distinct layers. No imported heuristic becomes a SOXL probability without evaluation.

## 5. Scope / safety

Only public read-only research and local source clones occurred. No third-party code was executed, no dependencies installed, no services launched, no credentials configured, no trades placed, no GitHub changes made. Vendor audit clones are research references and should not be committed wholesale into the user's product repository.
