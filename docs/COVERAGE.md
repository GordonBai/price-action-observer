# Observation coverage and timing contract

44 curated knowledge cards are not 44 completed detectors. These are original, deterministic engineering approximations, not official Brooks algorithms or empirically calibrated probabilities. Source-reading provenance and limits remain in `knowledge/concepts.json`. No full-course/video mastery is claimed.

| Family | Operational subset | Important limit |
|---|---|---|
| DB / DT | Strict 2-left/2-right pivots; 0.6 ATR similarity; 1 ATR rebound; candidate, neckline close, invalidation, expiry | Not all Brooks double-bottom/top variants; first knowledge time is delayed |
| H1/H2/L1/L2 | Rearmed high/low attempts, episode expiry, context labels | Outside bars excluded, equal extremes not attempts; not complete H1–H4 rules |
| Three-push wedge | Alternating confirmed pivots; third need not exceed second; later local counter-swing break / invalidation / expiry | Local structural confirmation is NOT complete MTR or proof of reversal |
| ii / ioi | Strict nested inside/outside sequence | Neutral candidate; equal-edge variants excluded |
| Candle observations | Doji, trend bar, reversal-bar candidate using explicit body/range/close thresholds | Shape is not setup quality or a buy/sell instruction |
| Microchannel | Four or more bars with both bounds advancing and non-opposing closes | Not all tight channels; emits evolving run observations |
| Gap taxonomy | Adjacent open gap, nonoverlapping bodies, three-bar microgap with directional middle bar | No automatic measuring/exhaustion classification |
| EMA gap / first return | EMA20 recursive close seed; starts after 20 bars; 10 separated bars before first-return observation | Local diagnostic only, excluded from primary groups. Intraday resets at NY session/gaps; daily continuity follows expected XNYS sessions. Not broker EMA; moving reference, not fixed target |
| Tight range / barbwire | 8 bars, adjacent overlap >=85%, total width <=2.5 ATR; barbwire additionally has small-body bar | Heuristic subset, not synonyms; not all range variants |
| Surprise / climax | Range >=2x preceding ten-bar average, large body; directional context makes climax candidate | No trend-maturity test; expansion could be continuation; no calibrated forecast |
| Breakout / follow-through / failure / test | Frozen preceding 10-bar overlapping range, next-bar continuation check, close back inside, touch/reclaim or space-preserving test | Independent observational window from legacy 20-bar range/MM; labels may overlap and are not independent evidence |
| MM | Range/DB height projections; manual AB=CD helper | Target touch != reversal, no automatic equal-leg anchor selection |
| Context | 20-bar directional efficiency heuristic | Not complete market-cycle/Always-In model |
| Source grounding | IDs, summaries, counterexamples, source links, knowledge hash on events | Citation identifies conceptual basis, not endorsement of thresholds |
| Audit | Known-case replay, frozen weekly calendar sample, event anchors and separately marked posthoc paths | Human labels initially blank; precision/recall/insight accuracy unknown |

## Added structured subsets
See [all nine mappings and ten event families](STRUCTURES.md): tight-channel proxy, frozen pivot trend lines, candidate MTR development, failed-failure close sequence, gap development, opening two-sided mode, opening reversal candidate, completed 5-minute data product and candidate final-flag development. These are not nine new proven trading setups.

## Explicitly incomplete
Complete discretionary MTR/final flags, generalized failed failures, second-leg traps, parabolic acceleration geometry, full opening-reversal regimes, broad channels, automatic support/resistance selection, multi-timeframe directional confirmation and all higher-order variants are not claimed. Risk/position-management, execution and product-boundary cards remain explanations or methodology, not auto-trading policies.

## Causality and versioning
Each event has `observed_at`, status, anchors, code/config version, knowledge hash, source references and uncertainty. Right-confirmed pivots retain their occurrence times but are published only after confirmation. Future bars cannot rewrite an earlier emitted event. OHLC ambiguity cannot be resolved by assuming intrabar order. A local structural confirmation proves only the specified closed-bar condition.

Intraday session-date changes (America/New_York) and missing same-session intervals reset structures. Daily bars instead remain continuous across expected XNYS sessions, including weekends/holidays; a missing expected trading session resets the structures. Robinhood daily bars and native points are timestamped at the actual XNYS session close, typically 16:00 ET or 13:00 ET on scheduled early closes. Daily freshness follows the calendar and a two-hour post-close grace period. Canonical offline input accepts legacy next-UTC-midnight times. Live/replay share one engine. Journals pin code, configuration and knowledge hashes; changed inputs or definitions require a new database. No silent history rewriting. Detector state and recent event retention are bounded; current-session bar history and on-disk journals still require resource planning. A 24-hour non-US feed does not have US-equity session semantics merely because input validation accepts its symbol.

## Evaluation purpose
The primary deliverable is chart observation and explanation correctness. `replay` no longer automatically evaluates a trading strategy. `evaluate` retains an explicitly separate legacy hypothetical-policy experiment; its returns are not pattern accuracy. Actual direction afterwards is a diagnostic, not proof that a neutral shape or candidate was correctly identified. Precision and recall require a predefined independent annotation rubric, both event and no-event windows, and inter-rater checks.

## Display priority is not prediction confidence
The receiver defaults to priority 3 (key structural lifecycle changes), a 15-minute cooldown per family/status/direction, and one combined display group per closed bar. Priority 3 includes structural candidates and key lifecycle transitions. `--display-min-priority 2` includes additional candidate observations; `0` and `--display-cooldown-minutes 0` reduce filtering, but do not expose every raw event in primary groups: local `ema_gap` and `ema_first_return` remain `LOCAL_DIAGNOSTIC` and are always excluded there. Inspect the original/raw event tape for those diagnostics. None of these options changes raw detector events or raises identification accuracy. A newly distinct pattern with the same editorial key can be hidden during cooldown, so the raw tape remains necessary for detailed review.

Display state is incremental, bounded and rebuilt from the complete journal, not recalculated from a sliding 200-event tail. Its settings are pinned in the journal identity. The panel distinguishes cumulative filtering totals from retained recent groups, and provides an original-event mode. Range/warmup contexts say observation-first, not buy/sell advice. This is visual noise control, not a permission to send unsolicited alerts.

## Current terminal workflows

`poll-robinhood` displays intraday context, active structures and reference
levels. Eligible Robinhood bars with an omitted interpolation marker preserve
that provenance. `--strict-interpolation` excludes omissions. The native
intraday pack is EMA20, VWAP, ATR14, RSI14 and classic pivots. The regular daily
pack is EMA20, ATR14, RSI14 and MACD.

`swing` scans closed daily bars from Robinhood or canonical offline JSONL/CSV.
It warms on the full input and highlights structures in the requested recent
focus window. Recent resolutions cover the latest five bars at most. When an
older target is reached or invalidated in that window, the report retains the
original setup identity and reference levels, including after a journal restart.
Intraday PDH and PDL require complete regular-session coverage of the preceding
XNYS session. A 300-bar display window cannot cover all 390 one-minute bars of
a normal session. The wizard offers monitor and swing modes. Structural coordinates
are research references with `probability=None`. Browser canvas level overlays
and Phase 2 `--htf` linkage remain future work.
