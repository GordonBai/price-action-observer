# Public-material concept cards — actual text review
2026-11-18. These notes paraphrase official indexed article text retrieved with web search. Direct page opens remain blocked (403). This is real review of the returned substantive text, not merely titles, but not a claim of complete page/chart/video review. No audiovisual samples or subtitles were retrieved in this pass. Algorithmic implications below are our proposed engineering interpretation, not Brooks-prescribed numerical rules.

## 1. Setup is not a candle label
Source: https://www.brookstradingcourse.com/how-to-trade-manual/candlestick-charts/
Review: substantive indexed extract.
Meaning: a setup combines a signal with context; merely identifying a candlestick shape is insufficient.
Engineering implication: output separate context, structural pattern, signal bar, trigger and invalidation. Suppress standalone “buy” from a shape classifier. Explain opposing evidence and state uncertainty.
Uncovered: all illustrated examples and full text, plus any deeper course explanations.

## 2. Double bottom/top are flexible tests, not exact equality
Sources:
- https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
- https://www.brookstradingcourse.com/trading-strategies/5-steps-to-finding-todays-trades/
Review: glossary definitions and specific double-top/bottom section of article read through indexed text.
Meaning: two lows/highs around an earlier swing level may be separated by one bar or many bars; they need not be the day's extreme. Double-bottom bull flags and double-top bear flags occur within trends. The five-steps discussion explicitly accepts imperfect tests and looks left for context; a wedge and a double top can coexist. Its example uses a bear signal bar near its low, rather than equality alone.
Engineering implication: support micro and swing-scale candidates, directional flag versus reversal context, nested/overlapping labels. A tolerance in ticks or ATR must be documented as an approximation. Preserve the time each swing became knowable; a later-confirmed pivot cannot create an earlier live signal. Do not mandate textbook neckline break for every Brooks-style pattern without distinguishing that stricter variant.
Uncovered: comprehensive variations, tolerance, maximum spacing, objective swing algorithm, all charts.

## 3. Double bottom is not automatically a major trend reversal
Source: https://www.brookstradingcourse.com/ask-al/always-in-major-trend-reversal-analysis/
Review: substantive transcript sections on major/minor reversals and wider left-side context.
Meaning: Al distinguishes a higher-low double-bottom major-reversal attempt from a minor reversal or simply a lower high in an existing broad bear channel. The label depends on prior structure and scale, not two matching extrema alone.
Engineering implication: retain “possible reversal” until additional evidence; do not rename a continuation channel setup as MTR solely because the short window resembles a W.
Uncovered: underlying chart inspection and full session, quantitative major/minor threshold.

## 4. Market cycle is the first layer
Source: https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/
Review: long indexed text spanning cycle, range behavior, failures, tight ranges.
Meaning: breakout begins trend, pullbacks lead to channel behavior, growing two-sided trade evolves toward range, then another breakout. In a range, apparent strong directional legs can be failed breakout attempts. Avoiding the middle and sometimes declining to trade a tight range are part of the method. The article's probabilities are teaching heuristics, not SOXL-specific measured accuracy.
Engineering implication: use explicit states with uncertain/transition state, not forced binary direction. Record overlaps, pullback depth, follow-through and location in the range. “No setup / wait” must be a normal output. Never substitute the quoted 80% heuristic for backtested confidence.
Uncovered: complete Market Cycle video, calibrated thresholds, stochastic state transitions.

## 5. Measured move is a projection family
Source: https://www.brookstradingcourse.com/ask-al/china-futures-daily-interview-part-1/
Review: substantive MM discussion and market probing/breakout explanation.
Meaning: MM can be anchored to breakout height, preceding trading-range height, equivalent legs, or gaps. Brooks uses a broad gap definition, not exclusively a session gap.
Engineering implication: label projection type and all anchors, freeze when generated, show candidate targets rather than quietly selecting the one hit afterwards. Formula proposals (not verbatim source): range upward target H+(H-L); equal-leg upward target C+(B-A). Gap projection needs separate source-grounded definition before implementation.
Uncovered: every MM construction, anchor selection hierarchy, gap formulas and chart demonstrations. No claim that one formula captures all Brooks MM.

## 6. Target touch is not a reversal signal
Source: https://www.brookstradingcourse.com/ask-al/trading-range-days-price-action/
Review: substantive “Fading measured move targets” text.
Meaning: MM is treated similarly to other support/resistance; contextual conditions govern whether fading it makes sense. Buying merely because a strong bear trend reaches a downward MM can be a mistake. Progressive bar-by-bar replay reveals many tempting reversal shapes before a trend ends.
Engineering implication: MM target-reached event must be distinct from countertrend-entry event. Replay acceptance tests must hide future bars, retaining failed and invalidated patterns rather than only successful examples.
Uncovered: full underlying chart and complete discussion.

## 7. Range gaps versus trend gaps
Source: https://www.brookstradingcourse.com/ask-al/missing-swing-trades-measured-moves-spikes/
Review: Q2 MM/gaps and range-day discussion read.
Meaning: the day's context can make anticipated measuring gaps close rather than launch a durable move. A strong trend can extend beyond an earlier projection. The article contrasts scalping/range behavior with swing continuation; it does not guarantee entering late is profitable.
Engineering implication: never infer “MM completed, therefore reverse”; allow extension targets and revise scenario prospectively. Log the original scenario, invalidation and revision without rewriting history.
Uncovered: video and charts; gap measurement cannot be reconstructed reliably from isolated bar references alone.

## 8. Breakout failure can itself fail
Source: https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
Review: “failed failure” definition.
Meaning: an initial breakout, reversal attempt, then resumption of the initial direction may turn into a breakout pullback. A failed pattern is a new context, not simply deleted information.
Engineering implication: event chain should distinguish attempted breakout → possible failure → resumed breakout. “Failure” needs its own observed trigger and horizon; avoid evaluating success from hindsight. Keep original event ID and link subsequent revisions.
Uncovered: objective maximum time window, universal entry/stop definitions.

## 9. Signal bar, entry bar and order are distinct
Source: https://www.brookstradingcourse.com/how-to-trade-manual/stop-orders/
Review: extensive indexed article text, including signal and entry definitions and order examples.
Meaning: the signal bar precedes the entry; one illustrative long entry is above its high, while a protective stop can be beyond its other side. ii/ioi may be signals but their context matters. High probability can come with greater risk and poorer reward-to-risk, so probability alone is inadequate.
Engineering implication: emit a candidate only after the signal bar is known; trigger on subsequent data. Account for gaps, spreads, ambiguous OHLC intrabar order and cancellation. Protective stops need structural alternatives rather than always using a candle-size stop. No claim that generic article probability numbers are validated system win rates.
Uncovered: complete charts, instrument-specific tick economics, full trade-management course.

## 10. Overlapping pattern taxonomy
Source: https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
Review: substantive indexed sections: introduction, MTR, final flags, breakouts, H2/L2.
Meaning: one situation can simultaneously be a failed channel breakout, triangle/final-flag reversal and an MM test. H2/L2 express two countertrend attempts within continuation structure, sometimes nested. Major-reversal and final-flag categories include preceding trend and reversal development, not a stand-alone candle geometry.
Engineering implication: use multi-label detection with shared evidence, not an exclusive pattern classifier or additive score counting correlated labels as independent votes. Keep pattern-family relationships and scale.
Uncovered: remaining article sections, all examples, complete bar-counting course; no exhaustive pattern coverage claim.

# Research gate before coding
- Build complete public-source metadata manifest with access/review states; catalogue alone is insufficient.
- Add inspected charts and authorized audiovisual timecodes or transcripts, especially 12A and MM sample.
- For each family record positive and negative examples, incompatible contexts and first-observable timestamp.
- Explicitly label each numerical threshold as source-prescribed, engineering approximation, or empirically fitted.
- Estimate SOXL and other instrument performance out of sample, including costs; source teaching heuristics are not calibrated probabilities.
