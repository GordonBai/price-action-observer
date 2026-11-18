# Price Action Lens: staged implementation design (research draft)
Date: 2026-11-18
Status: proposed engineering design, NOT product code and NOT evidence of a deployed system. User's latest priority is systematic public-material research before incremental implementation.

## User goal and known constraints
Extend the cloned AI Agent Lens into a real-time chart-analysis system emitting signals and understandable Chinese explanations, with broad Brooks Price Action coverage. Test the completed system on SOXL on November 17, 2026 and the preceding three months. Then publish to the user's GitHub with an English/Chinese README styled after GordonBai/robinhood-trading-infra. Parent resolves repository destination; no create/push now. No execution or brokerage-order capability.

Brooks coverage means a traceable, progressively expanding concept catalogue, not an assertion that all discretionary judgement is encoded. Publicly accessible does not mean redistributable. Store source metadata, original paraphrases and original algorithms; do not bundle complete courses or books.

## Evidence baseline
Read alongside [`source_audit.md`](source_audit.md) and `public-material-concept-cards.md` here. Much evidence is substantive indexed text while direct pages are blocked. Video titles/links have been catalogued but not watched; no completed audiovisual study is claimed. First implementation gate requires additional accessible literature cards, chart examples and precise definitions, or explicitly excludes still-understood-only-from-indexed-text concepts from authoritative coverage claims.

## Architecture choice proposed by the builder
Prefer Python engine alongside unchanged upstream Pine, rather than expanding everything in Pine. This supports event persistence, reproducible sequential replay, tests, richer pattern memory and flexible feeds. Pine remains an optional source of completed-bar observations, not sole source of truth. An all-Pine option simplifies TradingView installation but constrains state/replay/service robustness; an LLM-only chart reader is harder to audit and cannot enforce deterministic event timing. These are builder recommendations, not user-approved selections.

Pipeline:
source adapters -> normalized final bars -> durable journal -> incremental context and pattern engine -> signal/scenario lifecycle -> Chinese evidence explanations -> API/dashboard.
Replay feeds the same engine. Optional LLM prose is downstream, never the detector or source of numeric levels. No confidence percentage until empirically calibrated.

## Phase 0: research and acceptance catalogue
Deliver source manifest, concept cards and coverage matrix keyed by stable concept IDs. Every card includes source/review state, definition, context, positive/negative examples, engineer-supplied thresholds, ambiguity, available-time semantics and test names. Separate core rule, strict variant, heuristic candidate and unimplemented statuses. Inspect chart evidence rather than inferring full definitions from titles. Parent coordinates additional research.

Exit: initial implementable set has complete rule specifications; unresolved families are explicitly deferred rather than silently simplified.

## Phase 1: deterministic data and replay substrate
- Normalized Bar: source/feed, exchange-qualified symbol, interval, session, bar_open, bar_close, received_at, OHLCV, finality, adjustment policy, revision ID.
- UTC storage, exchange-local session calendar; SOXL default RTH, separately identified extended-hours configuration. Reject invalid OHLC, nonfinite prices, backwards timestamps and unsupported interval assumptions.
- SQLite or equivalent transactional bar/event journal with unique source/symbol/interval/time/revision identity. Duplicate identical bars are idempotent; revisions recorded and replayed prospectively with clear corrected-history mode.
- Distinguish session closures from unexpected gaps. Stale/gapped/warmup data yields DEGRADED/WAIT, never a fresh confident signal.
- Engine accepts one completed bar at a time; derive only completed higher-timeframe bars. Version and freeze configuration plus source hashes.
- Raw AI Agent Lens `time` is close time. Keep optional upstream indicator context separate from engine-owned calculations.

Exit: deterministic replay, restart equivalence, prefix invariance and time-zone/session tests pass with synthetic data. No profitability claims.

## Phase 2: lowest-ambiguity pattern primitives
Implement only approved concept cards: bar strength/reversal observations, inside/outside/ii/ioi, microchannel, confirmed swings, double top/bottom candidates and distinct neckline-break variant, frozen-range breakout/failure/retest, measured-move projections with explicit anchors. Candidate, confirmation, trigger and invalidation are separate lifecycle events.

Each event: immutable ID, family/scale, symbol/timeframe, source bars, occurrence_time, first_observed_at, confirmed_at, rule/version/config hash, evidence, opposing evidence, parent event IDs, status and optional trigger/stop/target scenarios. Pattern labels may overlap but shared evidence is not counted as independent votes.

MM event always specifies type and anchors; target touch never automatically means reversal. Signal bar close must precede later trigger. Five-right-bar pivot is not knowable at the pivot timestamp.

Exit: positive and negative fixtures for each family; exact confirmation timing assertions; replay includes failed patterns and never deletes them.

## Phase 3: context and advanced families
Market-cycle heuristic with UNKNOWN/TRANSITION states, trend/range location and signal quality; H1/H2/L1/L2 episode counters and documented reset rules; three-push/wedge variants; DB bull flags/DT bear flags. MTR/final flag/always-in remain qualified candidates until broader evidence and examples support explicit rules. Gap-MM is deferred until anchor definition is grounded.

Exit: context counterexamples and multi-scale conflicts tested. Coverage labels cannot show 'implemented' for an empty placeholder or generic candle detector.

## Phase 4: real-time service and explanation
Authenticated bounded ingress, per-stream sequencing, replay/recovery, health exposing last bar and last processing time, data-age and session state. Localhost default; no tokens in public logs. TradingView webhook integration and one verified market-data adapter; no credential invention or paid entitlements assumed. A webhook endpoint awaiting packets is integration-ready, not live.

Chinese panel: feed health/time, current market context, pattern list/lifecycle, evidence and counter-evidence, hypothetical trigger/invalidation/MM targets, and reasons to wait. Preserve original observations if scenarios change. Use bounded schemas/templates before optional LLM explanation.

Exit: real incoming completed bars verified, duplicates/reconnect tested, screenshots/UI checks and sustained-health evidence. Stable hosting and accessible route must be verified separately from code readiness.

## Phase 5: SOXL evaluation contract
### Dates and data
User's single day is 2026-11-17, New York time. Proposed prior-three-calendar-month window: 2026-08-17 through 2026-11-16 inclusive (actual exchange sessions only). Freeze this interpretation in report, not silently substitute last 90 bars or last quarter. Obtain enough pre-window warmup separately; warmup observations are never scored as evaluation trades.

Fetch provenance: provider, feed (SIP/IEX etc.), raw query timestamps, fetched_at, adjustments, session filters, splits, coverage/missing bars, checksum. Data access is not presumed. Keep actual gaps; don't fill fictional OHLC. Validate Nov 17 against independent daily summaries where available. Do not combine inconsistent feeds or adjustments without disclosure.

### Leakage policy
November 17 was already inspected in an earlier replay, so it is a **known-day case study**, not an untouched holdout. Use it to show bar-by-bar behavior, missed moves and false signals without tuning to it. Record this prominently. Prior three months use chronological development/validation/evaluation partitions; proposal Aug17–Sep30 development, Oct1–Oct23 validation, Oct26–Nov16 frozen evaluation, subject to actual data sufficiency. No random bar split. Purge overlapping trade horizons and handle open trades at boundaries. Once evaluation inspected, it cannot become a new pristine holdout after tuning. Save config before final run.

### Separate questions
A. Is the rule engine causal and reproducible? Exact event timing, prefix invariance and restart equivalence.
B. Does the rule align with curated source concepts? Independently annotated examples, disagreements and coverage, not shape counts alone.
C. Would an explicit hypothetical policy have useful economics? Only if entry, exit, overlapping-signal arbitration and position rules are preregistered. A pattern detector itself has no P&L.

### Paper policy, if evaluating returns
One position at a time; use clearly declared long-only baseline for SOXL and a separately reported hypothetical short variant if requested, never assume borrow availability. Signal must be available before any subsequent trigger. Gap through stop uses worse executable opening proxy; stop/target on same bar is ambiguous, apply conservative stop-first AND report count/sensitivity. Structural invalidation and time/session exit fixed ahead of test. No price hindsight or exact-close fills after a close-time signal.

Report spread/slippage grids with stated assumptions, e.g. 1/3/5 basis points per side plus relevant fees (illustrative scenarios, not measured costs); stress larger slippage on gap/fast bars. If historical quote data available, use it instead. Report order turnover and gross versus net results. Model notional exposure explicitly; no unbounded leverage.

### Output
Nov17 chronological event tape/chart with reveal-up-to-time controls; three-month coverage and split table; setup counts by family, conflicts, invalidation rate, trigger rate, target-touch conditional statistics with precise horizon definitions; economic metrics only for specified policy: expectancy, net return, drawdown, turnover, exposure, sample size, day-level distribution. Use session-cluster uncertainty where meaningful, no precision theater from dependent bars. Include simple benchmarks and ablations; do not select the best parameter retrospectively for headline performance.

Exit: reproducible commands and artifacts, checksums/config snapshots, no invented data, limitations prominently recorded.

## Phase 6: documentation and GitHub publication
After tests, root confirms destination and authorized publish scope. README English + Chinese: centered title/tagline, truthful badges, language toggle and anchors, overview, supported/partial/deferred coverage, quick start, Mermaid architecture, directory responsibility table, extension guide, evidence-based verification/current limitations table, contribution/license/unofficial relationship statement. Borrow structure only from Robinhood reference, not results or maturity claims.

Keep raw third-party market data private unless licensing permits redistribution. Publish code, synthetic fixtures, original docs and permitted aggregate results. Exclude credentials, private account identifiers, data caches and large logs. Scan diff and git history before push; verify remote commit and actual CI result. Do not claim production/live or all-pattern completeness from passing unit tests.

## Work slicing after research gate
1. Data contract + synthetic tests.
2. Causal replay/journal + invariance tests.
3. One concept family per tested change, beginning DB/DT and MM.
4. Context/advanced state machines.
5. Service + explanation panel + live integration verification.
6. Frozen historical evaluation.
7. Independent review, documentation and authorized publication.

No implementation has been performed in this draft. Open decisions are literature completeness, actual data availability, stable hosting and GitHub target; minor engineering choices remain delegated to the builder.

## Second-round concept-card alignment
Reviewed [`concept_cards.md`](concept_cards.md) after drafting. Additional explicit contracts: `probability=null` until calibrated; distinguish `heuristic_strength` from probability; lifecycle `candidate -> armed -> theoretical_trigger -> invalidated/expired`; never call a modeled trigger an actual fill. Merge overlapping labels into a shared-evidence cluster instead of duplicate alerts. Distinguish management of an existing position from a new opposite-direction setup (profit-taking is not short entry). Test 1-minute events with separate fully completed 5-minute context as an experiment, not an assumed equivalent of Brooks's teaching timeframe. Mechanical attempt counting and contextual H2 naming are separate fields. These contracts belong in Phase 1 schema and Phase 2 tests, not just disclaimers.
