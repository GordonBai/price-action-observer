# Structured context development / 结构发展观察

`pa_lens/structures.py`, `structures/0.1`. The 44-card research registry supplies conceptual distinctions. All numeric thresholds below are this project's conservative operational choices, **not** rules prescribed by Brooks, learned probabilities or a complete representation of discretionary patterns. No orders, stop/target policy or profitability estimates are added.

## What the formerly unimplemented cards become

| Knowledge concept | Current operational subset | Still not claimed |
|---|---|---|
| tight-channel | 8 bars; at least 6 directional close steps; net >=2 current ATR; close adverse excursion <=1 ATR and full-range adverse excursion <=2 ATR | Full discretionary channel geometry, actual profitable countertrend space, costs |
| trend-channel-lines | Two strict 2-left/2-right confirmed higher lows in `trend_up`, or lower highs in `trend_down`; separation <=40 bars; freeze each line version | Full channel envelope, best-fit lines, discretionary alternative anchors |
| major-trend-reversal | Frozen line broken → later line test → later close beyond that test bar's opposite edge; all MTR development labels remain **candidates** | Complete MTR, high/low retest taxonomy, proof that prior trend ended |
| failed-failure | Freeze 10-bar overlapping range; initial close outside, subsequent close back inside, later close back outside same edge; 15-bar lifetime | General multi-leg failed failures or prescribed trade entry |
| measuring-vs-exhaustion | Directional three-bar microgap; subsequent two-bar full-gap survival, later far-edge touch, 15-bar expiry | Classifying a gap definitively as measuring or exhaustion |
| opening-breakout-mode | Only with 09:30 New York opening coverage, fixed first 5-minute range and first 120-minute window; new running high and low tests close back inside on different bars | Using final daily extremes, inferred intrabar ordering, all opening modes |
| opening-reversal | First 5-minute direction then close beyond the opposite opening-range edge; one invalidation if original direction recovers | Forecast of daily close, gap-based reversal without previous session input |
| multi-timeframe | Five complete, contiguous RTH-aligned one-minute bars form a 5-minute OHLCV observation only at final close | General cross-timeframe interpretation, incomplete higher bars, overnight aggregates |
| final-flag | 10-bar directional phase (>=2 ATR, efficiency>=0.7), then 5-bar overlapping consolidation (width<=2 ATR); candidate → same-direction breakout → failure hypothesis | Knowing in advance that this really is the final flag, all variants |
| second-leg-trap | Remains unimplemented | Unambiguous general leg segmentation needs further evidence/annotation |
| parabolic-wedge | Remains unimplemented | Three pushes alone do not establish accelerating geometry |
| always-in | Remains unimplemented | Do not silently rename `trend_up/down` as Always In |
| actual-risk | Research explanation only | Ambiguous author endpoint; final MAE cannot become ex-ante risk |
| confirmation-risk-tradeoff | Research explanation only | Entry-policy comparison is not requested as a new trading strategy |
| instrument-transfer-boundary | Research explanation only | ES conventions/probabilities cannot be transferred to SOXL |
| session-and-liquidity-context | Existing timestamp/source/RTH safeguards, plus explicit opening and aggregation scope | Exchange holiday/auction/early-close calendar, spread/LULD/quotes inference |
| scale-in-and-exit-policy | Research explanation only | No scale-in/position-management policy or execution permission |

The ten-bar maturity proxy cannot prove that a trend is truly late in its life. These are **9 conceptual subsets**, not completion of all 17 cards. A single `higher_timeframe_bar` is a completed data product, not a higher-timeframe directional signal. Low-quality/unknown contexts are allowed.

## Event contract

Class: `StructureDetector(config=None)`, `update(bar, context, atr)` returns a list compatible with the existing event envelope: stable internal ID, family, status, direction, observation time, anchors, Chinese evidence/explanation, `knowledge_ids`, explicit uncertainty, and `probability=None`.

Families: `gap_development`, `failed_failure`, `tight_channel`, `opening_breakout_mode`, `opening_reversal`, `higher_timeframe_bar`, `trend_line`, `trend_line_retest`, `mtr_development`, `final_flag_development`.

`confirmed` for failed failure means only the specifically defined sequence of closes occurred. It does **not** confirm a future trend. MTR and final-flag stages deliberately remain candidates even after local reversal evidence appears. Gap role updates are observations, not confirmed measuring/exhaustion predictions.

Parent chains require the integration layer to preserve internal-ID → public-ID mappings beyond the first child:
- failed-failure initial candidate → confirmed/expired;
- opening-reversal candidate → one invalidated event;
- MTR broken-line candidate → line-retest observation → local-evidence candidate or invalidated/expired (all reference the initial candidate);
- final-flag initial candidate → continuation candidate → failure candidate or invalidated/expired (all reference the initial candidate).

## Causal and bounded state

Pivot occurrence and confirmation timestamps remain separate. Trend-line anchors freeze at the time both anchors are confirmed; subsequent line versions never rewrite old event objects. Line-test tolerance is 0.25 current ATR and the MTR episode lasts at most 20 bars; reclaiming the original side by more than 1 current ATR invalidates the episode. There is no retrospective move of a candidate to the earlier pivot.

Opening logic accepts only a first bar whose close corresponds to a full bar from 09:30 ET; starting later produces no opening claim. Two-sided rejection in one outside bar does not establish test ordering. Five-minute aggregation rejects partial initial windows and second/microsecond-offset inputs and emits no incomplete aggregate. Opening observations likewise require exact minute-aligned timestamps. UTC timestamps are translated through the New York timezone, not hard-coded DST offsets. The nominal RTH cap is 16:00; absent bars do not permit an early-close-calendar claim.

Caller resets on date changes and input discontinuities. Retained source bars <=90; open gaps <=8; swing anchors <=2 per side; each lifecycle type has at most one episode; partial aggregate <=5 bars. Final-flag terminal events have a five-bar rearm pause to avoid immediate identical recreation. Duplicate final bars are idempotent; revisions, out-of-order bars and mixed streams are rejected.

## Verification limits

Synthetic tests cover strict positives, same-bar ambiguity, nested/large-wick negative cases, mirrored failed failure, expiry, closed-bar alignment, prefixes, historical object immutability and bounded state. These validate these engineered definitions, not interpretation accuracy on independent real charts. Human truth labels are still required before accuracy/recall claims.
